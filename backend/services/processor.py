import cv2
import numpy as np
import base64
from PIL import Image as PILImage
import easyocr
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

class SurveyProcessor:
    def __init__(self):
        # Use raw easyocr for text extraction (fallback/handwriting)
        self.raw_reader = easyocr.Reader(['en'], gpu=False)
        self.troc_model = None

    def _get_troc_model(self):
        """Lazy-load TrOCR model for better handwriting recognition."""
        if self.troc_model is None:
            try:
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel
                logger.info("[PROCESSOR] Loading TrOCR model for handwriting...")
                self.troc_processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
                self.troc_model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
                logger.info("[PROCESSOR] TrOCR model loaded successfully")
            except Exception as e:
                logger.warning(f"[PROCESSOR] TrOCR not available: {e}")
                self.troc_model = False
        return self.troc_model

    def _enhance_for_handwriting(self, img):
        """Preprocess image specifically to help OCR read handwriting."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 1. Denoise
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            
            # 2. CLAHE for better contrast
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enhanced = clahe.apply(denoised)
            
            # 3. Morphological operations to strengthen handwritten strokes
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            morph = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)
            
            # 4. Convert back to BGR
            result = cv2.cvtColor(morph, cv2.COLOR_GRAY2BGR)
            return result
        except Exception as e:
            logger.warning(f"[PROCESSOR] Enhancement failed: {e}")
            return img

    def process(self, pil_image: PILImage.Image):
        open_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        quality_report = self._check_quality(open_cv_image)
        
        open_cv_image = self._enhance_image(open_cv_image)
        open_cv_image = self._deskew(open_cv_image)

        # Try table detection using contours
        has_table, table_cells = self._detect_table_cells(open_cv_image)
        
        if has_table and table_cells:
            result = self._parse_table_cells(table_cells, open_cv_image)
            mode = "TABLE"
        else:
            result = self._process_non_tabular(open_cv_image)
            mode = "MCQ_FALLBACK"

        debug_b64 = None
        if getattr(self, 'debug_mode', False):
            debug_b64 = self._generate_debug_image(open_cv_image, result["questions"])

        result["diagnostics"]["quality"] = quality_report
        result["diagnostics"]["mode"] = mode
        result["diagnostics"]["debug_image"] = debug_b64
        
        return result

    def _detect_table_cells(self, img):
        """Detect table cells using contour analysis."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Threshold
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Find contours
            contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                return False, []
            
            # Filter to get cell-like rectangles
            cells = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                # Filter by size (cells should be smallish but not too small)
                if 20 < w < img.shape[1] * 0.9 and 15 < h < img.shape[0] * 0.9 and w > 20 and h > 10:
                    cells.append({'x': x, 'y': y, 'w': w, 'h': h, 'bbox': (x, y, x+w, y+h)})
            
            if len(cells) < 4:  # Not enough for a table
                return False, []
            
            return True, cells
        except Exception as e:
            logger.warning(f"[PROCESSOR] Table detection failed: {e}")
            return False, []

    def _parse_table_cells(self, cells, img):
        """Parse table cells into structured rows/columns."""
        try:
            # Sort cells by position
            # First sort by Y (rows), then by X (columns)
            sorted_cells = sorted(cells, key=lambda c: (c['y'] // 30, c['x']))
            
            # Group into rows (cells with similar Y values)
            rows = []
            current_row = []
            row_threshold = 25
            
            for cell in sorted_cells:
                if not current_row:
                    current_row.append(cell)
                else:
                    last_y = current_row[-1]['y']
                    if abs(cell['y'] - last_y) < row_threshold:
                        current_row.append(cell)
                    else:
                        # Sort current row by X
                        current_row.sort(key=lambda c: c['x'])
                        rows.append(current_row)
                        current_row = [cell]
            
            if current_row:
                current_row.sort(key=lambda c: c['x'])
                rows.append(current_row)
            
            # Extract text from each cell using EasyOCR
            questions = []
            for row_idx, row in enumerate(rows):
                if len(row) < 2:
                    continue
                    
                # OCR the first cell as question
                q_text = ""
                first_cell = row[0]
                try:
                    x1, y1, x2, y2 = first_cell['bbox']
                    crop = img[y1:min(y2, img.shape[0]), x1:min(x2, img.shape[1])]
                    if crop.size > 0:
                        results = self.raw_reader.readtext(crop)
                        if results:
                            q_text = " ".join([r[1] for r in results])
                except Exception as e:
                    logger.warning(f"[PROCESSOR] Cell OCR failed: {e}")
                
                if not q_text or len(q_text) < 2:
                    continue
                
                # Try to find selected option (other cells)
                selected = None
                max_score = 0
                
                for cell_idx, cell in enumerate(row[1:], 1):
                    try:
                        x1, y1, x2, y2 = cell['bbox']
                        crop = img[y1:min(y2, img.shape[0]), x1:min(x2, img.shape[1])]
                        if crop.size > 0:
                            # Check for marks
                            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else gray
                            _, thresh = cv2.threshold(gray_crop, 128, 255, cv2.THRESH_BINARY_INV)
                            dark_ratio = cv2.countNonZero(thresh) / thresh.size
                            
                            if dark_ratio > max_score:
                                max_score = dark_ratio
                                # Get text
                                results = self.raw_reader.readtext(crop)
                                if results:
                                    selected = " ".join([r[1] for r in results])
                    except:
                        pass
                
                questions.append({
                    "question": q_text,
                    "options": [f"Option {i+1}" for i in range(len(row)-1)],
                    "selected": selected,
                    "confidence": 0.7 if selected else 0.3,
                    "status": "OK" if selected else "NOT_DETECTED"
                })
            
            return {"questions": questions, "diagnostics": {"logic": "TABLE_CELLS"}}
        except Exception as e:
            logger.error(f"[PROCESSOR] Table parse failed: {e}")
            return {"questions": [], "diagnostics": {"error": str(e)}}

    def _check_quality(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
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
        display_img = img.copy()
        try:
            cv2.putText(display_img, "DEBUG MODE: Extracted Questions Below", (50, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            _, buffer = cv2.imencode('.jpg', display_img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return base64.b64encode(buffer).decode('utf-8')
        except:
            return None

    def _enhance_image(self, img):
        """Improve contrast and lighting."""
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
        """Skip deskew unless there's significant tilt (outside reasonable range)."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.bitwise_not(gray)
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            
            coords = np.column_stack(np.where(thresh > 0))
            angle = cv2.minAreaRect(coords)[-1]
            
            # Only correct if angle is significant (not near 0 or 90)
            if -3 < angle < 3 or 87 < angle < 93:
                return img  # Skip small rotations
            
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

    def _extract_text_with_troc(self, img_crop: np.ndarray) -> str:
        """Use TrOCR for better handwriting recognition on individual regions."""
        model = self._get_troc_model()
        if not model:
            return ""
        
        try:
            # Preprocess crop for TrOCR
            gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            pil_img = PILImage.fromarray(binary).convert('RGB')
            
            pixel_values = self.troc_processor(pil_img, return_tensors="pt").pixel_values
            generated_ids = model.generate(pixel_values)
            text = self.troc_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            return text.strip()
        except Exception as e:
            logger.warning(f"[PROCESSOR] TrOCR extraction failed: {e}")
            return ""

    def _process_non_tabular(self, img):
        """Process image text - both handwritten and printed."""
        try:
            import easyocr
            temp_reader = easyocr.Reader(['en'], gpu=False)
            results = temp_reader.readtext(img, paragraph=False)
            
            data = []
            for (bbox, text, prob) in results:
                center_y = (bbox[0][1] + bbox[2][1]) / 2
                center_x = (bbox[0][0] + bbox[2][0]) / 2
                # Lower threshold to capture more text (including low-confidence handwritten)
                if prob > 0.25 and len(text.strip()) > 0:
                    data.append({
                        "text": text.strip(), 
                        "y": center_y, 
                        "x": center_x,
                        "conf": prob
                    })
            
            if not data:
                return {"questions": [], "diagnostics": {"logic": "NO_TEXT"}}
            
            # Sort by Y (top to bottom), then X (left to right)
            data.sort(key=lambda d: (d["y"], d["x"]))
            
            # Group into lines (items with similar Y values within threshold)
            lines = []
            threshold = 20
            current_line = [data[0]]
            
            for item in data[1:]:
                if abs(item["y"] - current_line[-1]["y"]) < threshold:
                    current_line.append(item)
                else:
                    current_line.sort(key=lambda d: d["x"])
                    lines.append(current_line)
                    current_line = [item]
            
            if current_line:
                current_line.sort(key=lambda d: d["x"])
                lines.append(current_line)
            
            questions = []
            for line in lines:
                line_text = " ".join([d["text"] for d in line])
                avg_conf = sum(d["conf"] for d in line) / len(line)
                
                # Include all text lines (both short and long)
                if len(line_text) > 0:
                    questions.append({
                        "question": line_text,
                        "options": [],
                        "selected": line_text,
                        "confidence": min(avg_conf, 0.95),
                        "status": "OK" if avg_conf > 0.4 else "LOW_CONFIDENCE"
                    })
            
            return {
                "questions": questions,
                "diagnostics": {"logic": "TEXT_LINES", "text_count": len(questions)}
            }
        except Exception as e:
            logger.error(f"[PROCESSOR] Non-tabular failed: {e}")
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



