import cv2
import numpy as np
import base64
import logging
from PIL import Image as PILImage
from img2table.document import Image as TableImage
from img2table.ocr import EasyOCR
import pandas as pd
import io

class SurveyProcessor:
    def __init__(self):
        # Auto-detect GPU for production performance
        use_gpu = False
        try:
            import torch
            use_gpu = torch.cuda.is_available()
            if use_gpu:
                logging.info("[PROCESSOR] NVIDIA GPU Detected. Enabling CUDA acceleration.")
        except ImportError:
            logging.info("[PROCESSOR] Torch not found or CUDA unavailable. Falling back to CPU.")

        # Initialize EasyOCR
        self.ocr_engine = EasyOCR(lang=["en"], kw={"gpu": use_gpu})

    def process(self, pil_image: PILImage.Image):
        # Convert PIL to OpenCV format
        open_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        # 0. Quality Check
        quality_report = self._check_quality(open_cv_image)
        
        # 1. Enhance Lighting (CLAHE)
        open_cv_image = self._enhance_image(open_cv_image)
        
        # 2. Correct Alignment (Deskew)
        open_cv_image = self._deskew(open_cv_image)

        
        # Save to temporary buffer for img2table
        # Convert back to PIL for img2table input
        pil_ready = PILImage.fromarray(cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2RGB))
        img_byte_arr = io.BytesIO()
        pil_ready.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()

        # 3. Extract Tables using img2table
        doc = TableImage(src=img_bytes)
        try:
            extracted_tables = doc.extract_tables(ocr=self.ocr_engine, implicit_rows=True, borderless_tables=True)
        except:
            extracted_tables = []

        # Logic for Mode Selection
        if extracted_tables:
            main_table = max(extracted_tables, key=lambda t: (t.bbox.x2 - t.bbox.x1) * (t.bbox.y2 - t.bbox.y1))
            result = self._parse_table_structure(main_table, open_cv_image)
            mode = "TABLE"
        else:
            # Phase 2: MCQ Fallback
            result = self._process_non_tabular(open_cv_image)
            mode = "MCQ_FALLBACK"

        # Generate Debug Image if requested
        debug_b64 = None
        if getattr(self, 'debug_mode', False):
            debug_b64 = self._generate_debug_image(open_cv_image, result["questions"])

        result["diagnostics"]["quality"] = quality_report
        result["diagnostics"]["mode"] = mode
        result["diagnostics"]["debug_image"] = debug_b64
        
        return result

    def _check_quality(self, img):
        """Analyze image for blur, lighting, and tilt."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Blur check (Laplacian Variance)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Brightness/Contrast
        mean, std_dev = cv2.meanStdDev(gray)
        
        warnings = []
        if laplacian_var < 100: warnings.append("LOW_RESOLUTION_OR_BLURRY")
        if mean[0][0] < 40: warnings.append("LOW_LIGHTING")
        if std_dev[0][0] < 20: warnings.append("LOW_CONTRAST")
        
        return {
            "status": "POOR" if warnings else "GOOD",
            "blur_score": round(float(laplacian_var), 2),
            "brightness": round(float(mean[0][0]), 2),
            "warnings": warnings
        }

    def _generate_debug_image(self, img, questions):
        """Draw bounding boxes and scores for visual debugging."""
        display_img = img.copy()
        try:
            # We don't have all coordinates exported easily in the current result structure.
            # In a full impl, we'd pass boxes. For now, simple label summary.
            cv2.putText(display_img, "DEBUG MODE: Extracted Questions Below", (50, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # Encode to base64
            _, buffer = cv2.imencode('.jpg', display_img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return base64.b64encode(buffer).decode('utf-8')
        except:
            return None


    def _enhance_image(self, img):
        """Improve contrast and lighting consistency."""
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
            return enhanced
        except:
            return img

    def _deskew(self, img):
        """Automatically straighten the document."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.bitwise_not(gray)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            
            coords = np.column_stack(np.where(thresh > 0))
            angle = cv2.minAreaRect(coords)[-1]
            
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
                
            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return rotated
        except:
            return img


    def _process_non_tabular(self, img):
        """Fallback for MCQ style forms without borders."""
        try:
            results = self.ocr_engine.readtext(img)
            # data structure: [([tl, tr, br, bl], text, prob), ...]
            
            # 1. Group by vertical alignment (lines)
            data = []
            for (bbox, text, prob) in results:
                center_y = (bbox[0][1] + bbox[2][1]) / 2
                data.append({"text": text, "y": center_y, "x": bbox[0][0], "bbox": bbox})
            
            # Sort by Y then X
            data.sort(key=lambda d: (d["y"], d["x"]))
            
            lines = []
            if data:
                current_line = [data[0]]
                for item in data[1:]:
                    if abs(item["y"] - current_line[-1]["y"]) < 15:
                        current_line.append(item)
                    else:
                        lines.append(current_line)
                        current_line = [item]
                lines.append(current_line)

            # 2. Identify Questions & Options
            questions = []
            for line in lines:
                text = " ".join([d["text"] for d in line])
                # Simple MCQ Marker check
                if len(text) > 10:
                    questions.append({
                        "question": text,
                        "options": ["Marked"], # Fallback for free-form
                        "selected": None,
                        "confidence": 0.5,
                        "status": "NOT_DETECTED"
                    })
            
            return {
                "questions": questions,
                "diagnostics": {"logic": "MCQ_SPATIAL"}
            }
        except Exception as e:
            return {"questions": [], "diagnostics": {"error": str(e)}}

    def _parse_table_structure(self, table, cv_image):
        import time
        start_time = time.time()
        questions = []
        score_logs = {}
        
        stats = {
            "rows_processed": len(table.content) if hasattr(table, 'content') else 0,
            "merges_performed": 0,
            "failed_rows": 0
        }

        last_question = None
        rows = table.content.values() if hasattr(table, 'content') else []
        for row_idx, row in enumerate(rows):
            try:
                cell_texts = [cell.value.strip() if cell.value else "" for cell in row]
                if len(cell_texts) < 2: continue

                q_text = ""
                o_cells = []
                
                if len(cell_texts[0]) > 5:
                    q_text = cell_texts[0]
                    o_cells = row[1:]
                elif len(cell_texts) > 1 and len(cell_texts[1]) > 5:
                    q_text = cell_texts[1]
                    o_cells = row[2:]
                
                # Merge logic
                if not q_text and o_cells and last_question:
                    stats["merges_performed"] += 1
                    s_data = self._detect_mark(o_cells, cv_image)
                    if s_data["selected"]:
                        last_question["selected"] = s_data["selected"]
                        last_question["confidence"] = s_data["confidence"]
                        last_question["status"] = s_data["status"]
                    continue

                if not q_text:
                    stats["failed_rows"] += 1
                    continue

                # Detect mark
                s_data = self._detect_mark(o_cells, cv_image)
                
                # Log scores for diagnostics
                q_id = f"q{len(questions) + 1}"
                score_logs[q_id] = {
                    "scores": s_data["all_scores"],
                    "status": s_data["status"],
                    "winner": s_data["selected"]
                }

                new_q = {
                    "id": q_id,
                    "question": q_text,
                    "options": [c.value if c.value else f"Option {i+1}" for i, c in enumerate(o_cells)],
                    "selected": s_data["selected"],
                    "confidence": s_data["confidence"],
                    "status": s_data["status"],
                    "suggestions": s_data["suggestions"]
                }
                questions.append(new_q)
                last_question = new_q
            except:
                stats["failed_rows"] += 1

        stats["processing_time_ms"] = int((time.time() - start_time) * 1000)
        stats["score_map"] = score_logs # Detailed accuracy logging
        return {"questions": questions, "diagnostics": stats}

    def _detect_mark(self, cells, cv_image):
        scores = []
        
        for cell in cells:
            try:
                # ROI Resolution-Independent Normalization
                x1, y1, x2, y2 = cell.bbox.x1, cell.bbox.y1, cell.bbox.x2, cell.bbox.y2
                h, w = y2 - y1, x2 - x1
                py, px = int(h * 0.1), int(w * 0.1)
                
                crop = cv_image[y1+py:y2-py, x1+px:x2-px]
                if crop.size == 0:
                    scores.append(0)
                    continue
                    
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                
                # Metric 0: Statistical Adaptive Threshold
                mean, std = cv2.meanStdDev(gray)
                mean_val, std_val = float(mean[0][0]), float(std[0][0])
                
                # Local threshold based on mean and intensity spread
                # factor 0.8 is tuned for standard ink on paper
                t_val = mean_val - (std_val * 0.8)
                _, thresh = cv2.threshold(gray, t_val, 255, cv2.THRESH_BINARY_INV)

                # Metric 1: Dark Pixel Ratio (DPR) - 50% Weight
                dpr = cv2.countNonZero(thresh) / thresh.size
                
                # Metric 2: Edge Density (ED) - 30% Weight
                edges = cv2.Canny(gray, 50, 150)
                ed = cv2.countNonZero(edges) / edges.size
                
                # Metric 3: Continuity (Connected Components) - 20% Weight
                # Intentional marks have 1-2 main components. Noise has many small specks.
                num_labels, labels = cv2.connectedComponents(thresh)
                # Normalize continuity: perfect = 1.0, noisy = low
                # (excluding background label 0)
                continuity = 1.0 / max(1, num_labels - 1) 
                
                # Weighted Final Score
                score = (dpr * 0.5) + (ed * 0.3) + (continuity * 0.2)
                scores.append(round(score, 4))
            except:
                scores.append(0)

        if not scores:
            return {"selected": None, "confidence": 0, "status": "NOT_DETECTED", "all_scores": [], "suggestions": []}

        # Build ranked candidates list
        indexed = [(s, i) for i, s in enumerate(scores)]
        ranked = sorted(indexed, key=lambda x: x[0], reverse=True)
        
        # Build suggestions (top 2 candidates always)
        suggestions = []
        for score_val, idx in ranked[:2]:
            cell = cells[idx]
            label = cell.value if cell.value else f"Option {idx + 1}"
            suggestions.append({"value": label, "score": round(score_val, 4)})

        max_score = ranked[0][0]
        
        # Accuracy Floor: If the best score is too noisy or faint, reject.
        if max_score < 0.04:
            return {
                "selected": None, 
                "confidence": max_score, 
                "status": "NOT_DETECTED", 
                "all_scores": scores,
                "suggestions": suggestions
            }
            
        status = "OK"
        selected_val = None
        
        # Ambiguity Check: Ensure a clear winner
        if len(ranked) > 1:
            second_max = ranked[1][0]
            if (max_score - second_max) < (max_score * 0.15):
                status = "LOW_CONFIDENCE"
                selected_val = None 
            else:
                winner_cell = cells[ranked[0][1]]
                selected_val = winner_cell.value if winner_cell.value else f"Option {ranked[0][1] + 1}"
        else:
            winner_cell = cells[ranked[0][1]]
            selected_val = winner_cell.value if winner_cell.value else f"Option {ranked[0][1] + 1}"

        return {
            "selected": selected_val,
            "confidence": max_score,
            "status": status,
            "all_scores": scores,
            "suggestions": suggestions
        }



