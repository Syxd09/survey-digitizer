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
        # Detect best available device
        import torch
        # Note: EasyOCR 1.7+ supports MPS, but we need to ensure torch is ready
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"[PROCESSOR] Initializing local OCR with device: {self.device}")
        
        # V7.0: Multi-language support (English + Portuguese for "Plugues" and similar terminology)
        try:
            self.raw_reader = easyocr.Reader(['en', 'pt'], gpu=(self.device == "mps" or torch.cuda.is_available()))
        except Exception as e:
            logger.warning(f"[PROCESSOR] EasyOCR GPU initialization failed, falling back to CPU: {e}")
            self.raw_reader = easyocr.Reader(['en', 'pt'], gpu=False)
            
        self.troc_model = None
        self.troc_processor = None
        
        # V10.0: Load Active Learning Memory
        self.memory_path = "feedback_loop/memory.json"
        self._load_memory()
        
        # Lazy-load TrOCR specifically for handwriting refinement
        if self.troc_model is None:
            try:
                import torch
                from transformers import TrOCRProcessor, VisionEncoderDecoderModel
                logger.info("[PROCESSOR] Loading TrOCR model (microsoft/trocr-base-handwritten)...")
                self.troc_processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
                self.troc_model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
                self.troc_model.to(self.device)
                logger.info(f"[PROCESSOR] TrOCR model loaded successfully on {self.device}")
            except Exception as e:
                logger.warning(f"[PROCESSOR] TrOCR initialization failed: {e}")
                self.troc_model = False

    def _load_memory(self):
        """Load user-corrected patterns from the feedback loop memory."""
        try:
            import json
            import os
            if os.path.exists(self.memory_path):
                with open(self.memory_path, 'r') as f:
                    self.memory = json.load(f)
            else:
                self.memory = {}
        except:
            self.memory = {}

    def _save_memory(self):
        """Persist learned patterns to the memory vault."""
        try:
            import json
            with open(self.memory_path, 'w') as f:
                json.dump(self.memory, f, indent=4)
        except Exception as e:
            logger.warning(f"[MEMORY] Save failed: {e}")

    def register_feedback(self, image_hash: str, text: str) -> bool:
        """Hydra learns a new pattern from user correction."""
        self.memory[image_hash] = text
        self._save_memory()
        logger.info(f"[MEMORY] Hydra learned pattern {image_hash} -> {text}")
        return True

    def _get_image_hash(self, img_crop):
        """Generate a difference hash (dhash) for visual pattern recognition."""
        try:
            if img_crop is None or img_crop.size == 0: return "0"
            gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY) if len(img_crop.shape) == 3 else img_crop
            resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
            diff = resized[:, 1:] > resized[:, :-1]
            return hex(int("".join(diff.flatten().astype(int).astype(str)), 2))[2:]
        except:
            return "0"

    def _skeletonize(self, img):
        """Thin out messy ink strokes to improve character clarity."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # Use Zhang-Suen or morphological skeletonization
            element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3,3))
            done = False
            size = np.size(binary)
            skel = np.zeros(binary.shape, np.uint8)
            
            temp_img = binary.copy()
            while not done:
                eroded = cv2.erode(temp_img, element)
                temp = cv2.dilate(eroded, element)
                temp = cv2.subtract(temp_img, temp)
                skel = cv2.bitwise_or(skel, temp)
                temp_img = eroded.copy()
                if cv2.countNonZero(temp_img) == 0:
                    done = True
            
            # Invert back to black-on-white
            return cv2.bitwise_not(skel)
        except:
            return img

    def _detect_signature(self, img_crop):
        """Identify dense, interconnected clusters as potential signatures."""
        try:
            if img_crop is None or img_crop.size == 0: return False
            gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY) if len(img_crop.shape) == 3 else img_crop
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # 1. Density Check
            density = cv2.countNonZero(binary) / binary.size
            
            # 2. Connectivity Check (Signatures have few, very large components)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
            if num_labels < 2: return False
            
            # Take internal components (skip background at 0)
            comp_areas = stats[1:, cv2.CC_STAT_AREA]
            max_comp_ratio = np.max(comp_areas) / binary.size
            
            # A signature is usually a high-density, high-connectivity mass
            if density > 0.15 and max_comp_ratio > 0.05:
                return True
            return False
        except:
            return False

    def _deblur_image(self, img):
        """Advanced Edge Boosting for extremely blurry (score < 10) scans."""
        try:
            # 1. Laplacian Sharpening Mask
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(img, -1, kernel)
            
            # 2. Unsharp Masking (Boost high-frequency edge details)
            gaussian_3 = cv2.GaussianBlur(sharpened, (0, 0), 2.0)
            unsharp = cv2.addWeighted(sharpened, 1.5, gaussian_3, -0.5, 0)
            
            return unsharp
        except Exception as e:
            logger.warning(f"[PROCESSOR] Deblur failed: {e}")
            return img

    def _enhance_for_handwriting(self, img):
        """Preprocess image specifically to help OCR read handwriting."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 1. Denoise (V7.0: Use even lower strength for blurry images to avoid artifacts)
            denoised = cv2.fastNlMeansDenoising(gray, None, 3, 7, 21)
            
            # 2. CLAHE for better contrast
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(denoised)
            
            # 3. Convert back to BGR
            result = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
            return result
        except Exception as e:
            logger.warning(f"[PROCESSOR] Enhancement failed: {e}")
            return img

    def process(self, pil_image: PILImage.Image):
        import time
        start_time = time.time()
        
        # Convert PIL to OpenCV
        open_cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        quality_report = self._check_quality(open_cv_image)

        logger.info(f"[PROCESSOR] Starting image enhancement (Device: {self.device})...")
        t0 = time.time()
        open_cv_image = self._enhance_image(open_cv_image)
        
        # V9.2: Auto-Lighting Recovery for dark scans (Brightness < 50)
        if quality_report["brightness"] < 50:
            logger.info(f"[PROCESSOR] Low lighting detected ({quality_report['brightness']}). Applying recovery boost...")
            open_cv_image = self._normalize_lighting(open_cv_image)
            
        logger.info(f"[PROCESSOR] Base enhancement took {time.time()-t0:.2f}s")
        
        t1 = time.time()
        open_cv_image = self._enhance_for_handwriting(open_cv_image) 
        logger.info(f"[PROCESSOR] Handwriting enhancement took {time.time()-t1:.2f}s")
        
        t2 = time.time()
        open_cv_image = self._deskew(open_cv_image)
        logger.info(f"[PROCESSOR] Deskew took {time.time()-t2:.2f}s")

        # 1. Structural Scan (Find all boxes/cells)
        logger.info("[PROCESSOR] Running structural scan...")
        _, structural_boxes = self._detect_table_cells(open_cv_image)
        
        # 2. Textual Scan (Find all text everywhere)
        logger.info("[PROCESSOR] Running textual scan...")
        text_regions = self._get_full_text_scan(open_cv_image)
        
        # 3. Unified Reconstruction
        logger.info(f"[PROCESSOR] Unifying structural ({len(structural_boxes)}) and textual ({len(text_regions)}) results...")
        result = self._reconstruct_universal(structural_boxes, text_regions, open_cv_image)
        mode = "UNIVERSAL_MAPPING"

        debug_b64 = None
        if getattr(self, 'debug_mode', False):
            debug_b64 = self._generate_debug_image(open_cv_image, result["questions"])

        result["diagnostics"]["quality"] = quality_report
        result["diagnostics"]["mode"] = mode
        result["diagnostics"]["debug_image"] = debug_b64
        
        return result

    def _detect_table_cells(self, img):
        """Detect potential table cells or MCQ boxes using contour analysis with V8 Pruning."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            cells = []
            img_area = img.shape[0] * img.shape[1]
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                # Ignore tiny noise boxes
                if area < (img_area * 0.0005): continue
                
                # Flexible filtering for both small checkboxes and larger table cells
                if 15 < w < img.shape[1] * 0.8 and 15 < h < img.shape[0] * 0.8:
                    aspect_ratio = w / float(h)
                    if 0.5 < aspect_ratio < 10:
                        cells.append({'x': x, 'y': y, 'w': w, 'h': h, 'bbox': (x, y, x+w, y+h)})
            
                # V8.1: Deduplicate and then prune singletons
            if len(cells) > 0:
                # Convert to format for groupRectangles
                rects = [[c['x'], c['y'], c['w'], c['h']] for c in cells]
                # Multiply to allow groupRectangles to work (it needs at least 1 overlap or eps)
                # But here we just want to merge very close boxes
                rects, weights = cv2.groupRectangles(rects, 1, 0.2)
                
                dedup_cells = []
                for r in rects:
                    dedup_cells.append({'x': r[0], 'y': r[1], 'w': r[2], 'h': r[3], 'bbox': (r[0], r[1], r[0]+r[2], r[1]+r[3])})
                
                # Now prune singletons from deduped list
                pruned_cells = []
                for i, c1 in enumerate(dedup_cells):
                    # V9.0 GRID RECOVERY: If it's a very large box (table border), keep it regardless
                    if c1['w'] > (img.shape[1] * 0.4):
                        pruned_cells.append(c1)
                        continue

                    has_sibling = False
                    for j, c2 in enumerate(dedup_cells):
                        if i == j: continue
                        dist = np.sqrt((c1['x']-c2['x'])**2 + (c1['y']-c2['y'])**2)
                        if dist < 250: # Increased sibling threshold
                            has_sibling = True
                            break
                    if has_sibling:
                        pruned_cells.append(c1)
                
                logger.info(f"[PROCESSOR] Structural cleanup: Total={len(cells)} -> Dedup={len(dedup_cells)} -> Pruned={len(pruned_cells)}")
                return (len(pruned_cells) > 0), pruned_cells
        except Exception as e:
            logger.warning(f"[PROCESSOR] Structural scan failed: {e}")
            return False, []

    def _get_full_text_scan(self, img):
        """Unified text detection with Auto-Scaling fallback for low-res scans."""
        try:
            # Stage 1: Standard Scale Detection with High Sensitivity
            params = {
                'text_threshold': 0.3, # Catch faint ink
                'low_text': 0.2,       # Catch small fragments
                'link_threshold': 0.4, # Better word connectivity
                'canvas_size': 2560,   # High-res internal rendering
                'mag_ratio': 1.0,
            }
            
            results = self.raw_reader.readtext(img, **params)
            
            # Stage 2: 2x Upscaling Fallback
            if len(results) < 15:
                logger.info("[PROCESSOR] Low text count at 1x. Retrying with 2x Upscaling...")
                h, w = img.shape[:2]
                img_2x = cv2.resize(img, (int(w*2), int(h*2)), interpolation=cv2.INTER_CUBIC)
                results_2x = self.raw_reader.readtext(img_2x, **params)
                
                if len(results_2x) > len(results):
                    logger.info(f"[PROCESSOR] 2x Upscaling helpful. Found {len(results_2x)} regions.")
                    # Map back
                    results = [([[pt[0]/2.0, pt[1]/2.0] for pt in b], t, p) for b, t, p in results_2x]

            # Stage 3: 3x NUCLEAR Upscaling Fallback (For blur_score < 10)
            if len(results) < 15:
                logger.info("[PROCESSOR] Still low text count. Retrying with 3x Lanczos scaling...")
                h, w = img.shape[:2]
                # Lanczos is superior for extracting detail from blurry sources
                img_3x = cv2.resize(img, (int(w*3), int(h*3)), interpolation=cv2.INTER_LANCZOS4)
                results_3x = self.raw_reader.readtext(img_3x, **params)
                
                if len(results_3x) > len(results):
                    logger.info(f"[PROCESSOR] 3x Scaling success! Found {len(results_3x)} regions.")
                    results = [([[pt[0]/3.0, pt[1]/3.0] for pt in b], t, p) for b, t, p in results_3x]

            text_regions = []
            for (bbox, text, prob) in results:
                x1, y1 = int(bbox[0][0]), int(bbox[0][1])
                x2, y2 = int(bbox[2][0]), int(bbox[2][1])
                text_regions.append({
                    'text': text,
                    'bbox': (x1, y1, x2, y2),
                    'conf': prob,
                    'center': ((x1 + x2) / 2, (y1 + y2) / 2)
                })
            return text_regions
        except Exception as e:
            logger.warning(f"[PROCESSOR] Text scan failed: {e}")
            return []

    def _reconstruct_universal(self, boxes, text_regions, img):
        """V9.0: Semantic Alignment Reconstruction. Handles MCQs and Key-Value Lists."""
        questions = []
        
        if not text_regions:
            return {"questions": [], "diagnostics": {"logic": "EMPTY_PAGE", "logic_version": "Hydra-v9.2-STABLE"}}

        # V9.2: Signal Filter (Remove IDE noise/ghost artifacts)
        filtered_regions = []
        noise_patterns = ["Pylance", "reportUndefinedVariable", "Ln ", "Col ", "Keyword arguments", "\"df\""]
        for t in text_regions:
            low_t = t['text'].lower()
            # 1. Pattern Matching (IDE/Terminal noise)
            if any(p.lower() in low_t for p in noise_patterns):
                continue
            # 2. Length Filter (Suppress tiny ghost tokens < 3 chars unless high confidence)
            if len(t['text'].strip()) < 3 and t['conf'] < 0.9:
                continue
            filtered_regions.append(t)
        
        text_regions = filtered_regions

        # 1. Column Detection (Finding Gutters)
        columns = self._detect_vertical_gutters(text_regions, img.shape[1])
        
        # 2. Sort text by Y then X for logical reading order
        text_regions.sort(key=lambda t: (t['bbox'][1], t['bbox'][0]))
        
        claimed_boxes = set()
        claimed_text = set()

        # Step A: Primary Checkbox Mapping (MCQ Pattern)
        for i, t in enumerate(text_regions):
            if t['conf'] < 0.1: continue
            t_x, t_y = t['center']
            
            nearby_boxes = []
            for j, b in enumerate(boxes):
                if j in claimed_boxes: continue
                b_center = (b['x'] + b['w']/2, b['y'] + b['h']/2)
                dist = np.sqrt((t_x - b_center[0])**2 + (t_y - b_center[1])**2)
                if dist < 350: 
                    nearby_boxes.append((dist, j, b))
            
            if nearby_boxes:
                valid_boxes = [nb for nb in nearby_boxes if abs(nb[2]['y'] - t['bbox'][1]) < 60]
                if valid_boxes:
                    claimed_text.add(i)
                    valid_boxes.sort(key=lambda x: x[0])
                    selected_val = None
                    max_dark = 0
                    for dist, idx, b in valid_boxes:
                        claimed_boxes.add(idx)
                        crop = img[b['bbox'][1]:b['bbox'][3], b['bbox'][0]:b['bbox'][2]]
                        if crop.size > 0:
                            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                            thresh = cv2.adaptiveThreshold(gray_crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                                         cv2.THRESH_BINARY_INV, 11, 2)
                            dark_ratio = cv2.countNonZero(thresh) / thresh.size
                            if dark_ratio > max_dark and dark_ratio > 0.1:
                                max_dark = dark_ratio
                                selected_val = t['text']

                    full_text = self._semantic_correction(t['text'])
                    questions.append({
                        "question": full_text,
                        "options": [f"Option {i+1}" for i in range(len(valid_boxes))],
                        "selected": selected_val,
                        "confidence": t['conf'],
                        "status": "OK" if selected_val else "UNSELECTED"
                    })

        # Step B: Alignment Pairing (List Pattern for remaining text)
        unclaimed_idx = [i for i in range(len(text_regions)) if i not in claimed_text and text_regions[i]['conf'] > 0.1]
        
        # Group unclaimed text into rows using Rolling Center Logic
        rows = []
        if unclaimed_idx:
            # First, sort all unclaimed text by Y for row grouping
            unclaimed_idx.sort(key=lambda idx: text_regions[idx]['bbox'][1])
            
            current_row = [unclaimed_idx[0]]
            row_y_sum = text_regions[unclaimed_idx[0]]['bbox'][1]
            
            for idx in unclaimed_idx[1:]:
                avg_y = row_y_sum / len(current_row)
                # V9.1: Increased threshold and rolling center
                if abs(text_regions[idx]['bbox'][1] - avg_y) < 55:
                    current_row.append(idx)
                    row_y_sum += text_regions[idx]['bbox'][1]
                else:
                    rows.append(current_row)
                    current_row = [idx]
                    row_y_sum = text_regions[idx]['bbox'][1]
            if current_row: rows.append(current_row)

        for row_indices in rows:
            if len(row_indices) >= 2:
                # Potential Key-Value pair (Role / Permission)
                # Sort by X to see columns
                row_indices.sort(key=lambda idx: text_regions[idx]['bbox'][0])
                key_idx = row_indices[0]
                val_idx = row_indices[-1] # Usually the right-most is the value
                
                key_text = self._semantic_correction(text_regions[key_idx]['text'])
                val_text = self._semantic_correction(text_regions[val_idx]['text'])
                
                # V10.0: Check Memory Vault for previously corrected patterns
                crop_v = img[max(0, text_regions[val_idx]['bbox'][1]-5):min(img.shape[0], text_regions[val_idx]['bbox'][3]+5), 
                             max(0, text_regions[val_idx]['bbox'][0]-5):min(img.shape[1], text_regions[val_idx]['bbox'][2]+5)]
                
                v_hash = self._get_image_hash(crop_v)
                if v_hash in self.memory:
                    val_text = self.memory[v_hash]
                    status = "LEARNED_MATCH"
                    conf = 1.0
                else:
                    # Check for Signature Pattern
                    if self._detect_signature(crop_v):
                        val_text = "[SIGNATURE_DETECTED]"
                        status = "SIGNATURE"
                        conf = 0.95
                    else:
                        # Proceed with OCR
                        if text_regions[val_idx]['conf'] < 0.7:
                            # Apply Skeletonization for messy cursive recovery
                            skel_crop = self._skeletonize(crop_v)
                            refined = self._extract_text_with_troc(skel_crop, high_precision=True)
                            if refined: val_text = self._semantic_correction(refined)
                        status = "LIST_PAIR"
                        conf = (text_regions[key_idx]['conf'] + text_regions[val_idx]['conf']) / 2

                questions.append({
                    "question": key_text,
                    "selected": val_text,
                    "options": [],
                    "confidence": conf,
                    "status": status,
                    "imageHash": v_hash
                })
            else:
                # Standalone note
                idx = row_indices[0]
                t = text_regions[idx]
                
                v_hash = self._get_image_hash(img[t['bbox'][1]:t['bbox'][3], t['bbox'][0]:t['bbox'][2]])
                full_text = self._semantic_correction(t['text'])
                
                if v_hash in self.memory:
                    full_text = self.memory[v_hash]
                    status = "LEARNED_MATCH"
                    conf = 1.0
                else:
                    status = "HANDWRITTEN_NOTE"
                    conf = t['conf']

                questions.append({
                    "question": full_text,
                    "selected": full_text,
                    "options": [],
                    "confidence": conf,
                    "status": status,
                    "imageHash": v_hash
                })

        return {
            "questions": questions, 
            "diagnostics": {
                "logic": "SEMANTIC_LIST_V9.2",
                "col_count": len(columns),
                "text_count": len(text_regions),
                "box_count": len(boxes),
                "image_lightness": self._check_quality(img)['brightness'],
                "logic_version": "Hydra-v10.0-AUTHORITY"
            }
        }

    def _detect_vertical_gutters(self, text_regions, img_width):
        """Analyze X-coordinates to find logical columns."""
        if not text_regions: return []
        xs = [t['center'][0] for t in text_regions]
        # Simple clustering (can be improved with Gaussian Mixtue but this is faster)
        xs.sort()
        columns = []
        if xs:
            curr_col = [xs[0]]
            for x in xs[1:]:
                if x - curr_col[-1] < 250: # Increased Column span for stability
                    curr_col.append(x)
                else:
                    columns.append(sum(curr_col)/len(curr_col))
                    curr_col = [x]
            columns.append(sum(curr_col)/len(curr_col))
        return columns

    def _get_merged_crop(self, objects, img):
        if not objects: return np.array([])
        x1 = min(o['data']['bbox'][0] for o in objects)
        y1 = min(o['data']['bbox'][1] for o in objects)
        x2 = max(o['data']['bbox'][2] for o in objects)
        y2 = max(o['data']['bbox'][3] for o in objects)
        return img[max(0, y1-5):min(img.shape[0], y2+5), max(0, x1-5):min(img.shape[1], x2+5)]


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

    def _normalize_lighting(self, img):
        """Recover details from dark images using CLAHE on L-channel."""
        try:
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            # Apply CLAHE to the lightness channel specifically
            clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(12, 12))
            cl = clahe.apply(l)
            limg = cv2.merge((cl, a, b))
            return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        except:
            return img

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

    def _extract_text_with_troc(self, img_crop: np.ndarray, high_precision: bool = False) -> str:
        """Use TrOCR for better handwriting recognition with optional high-precision beam search."""
        model = self._get_troc_model()
        if not model:
            return ""
        
        try:
            # V8.1: Protection against empty or invalid crops
            if img_crop is None or img_crop.size == 0 or img_crop.shape[0] < 2 or img_crop.shape[1] < 2:
                return ""

            import torch
            # 1. UPSCALING: If crop is small, use bi-cubic interpolation to sharpen for TrOCR
            h, w = img_crop.shape[:2]
            if h < 60 or w < 100:
                scale = 2.0
                img_crop = cv2.resize(img_crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                logger.info(f"[PROCESSOR] Upscaled small crop {h}x{w} to {int(h*scale)}x{int(w*scale)}")

            # 2. STROKE DILATION: Thicken faint handwriting to improve connectivity
            if high_precision:
                gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY) if len(img_crop.shape) == 3 else img_crop
                # Use a small kernel to avoid blurring characters together
                kernel = np.ones((2,2), np.uint8)
                # Dilation on inverted image thickens the dark strokes
                inv = cv2.bitwise_not(gray)
                dilated = cv2.dilate(inv, kernel, iterations=1)
                img_crop = cv2.bitwise_not(dilated)
                if len(img_crop.shape) == 2:
                    img_crop = cv2.cvtColor(img_crop, cv2.COLOR_GRAY2RGB)
            
            pil_img = PILImage.fromarray(img_crop)
            pixel_values = self.troc_processor(pil_img, return_tensors="pt").pixel_values
            pixel_values = pixel_values.to(self.device)
            
            # 2. BEAM SEARCH: Use more beams for critical handwritten fields
            gen_kwargs = {
                "max_length": 64,
                "num_beams": 10 if high_precision else 5,
                "early_stopping": True,
                "repetition_penalty": 1.2
            }
            
            generated_ids = model.generate(pixel_values, **gen_kwargs)
            text = self.troc_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            
            return text.strip()
        except Exception as e:
            logger.warning(f"[PROCESSOR] TrOCR extraction failed: {e}")
            return ""

    def _semantic_correction(self, text):
        """V9.0 Technical Lexicon Mapping. Corrects common handwriting/OCR artifacts."""
        if not text: return ""
        
        mapping = {
            "twirted": "(Write)",
            "cfuid": "(Full)",
            "fvii": "(Full)",
            "fvll": "(Full)",
            "fvill": "(Full)",
            "read-onlyy": "(Read-Only)",
            "vieww": "View",
            "insert": "Insert",
            "update": "(Update)",
            "delete": "Delete",
            "exemptt": "Exempt"
        }
        
        low_text = text.lower().strip()
        # Direct word mapping
        for k, v in mapping.items():
            if k in low_text:
                return v

        # Pattern-based healing for Technical Terms
        tech_words = ["analyst", "engineer", "admin", "manager", "read-only", "write", "full", "view", "select"]
        for word in tech_words:
            # If word is largely similar (80%+ characters)
            if word in low_text or (len(low_text) > 3 and word[:len(low_text)] == low_text):
                # Capitalize nicely or keep pattern
                if word == "full": return "(Full)"
                if word == "write": return "(Write)"
                if word == "read-only": return "(Read-Only)"
                return word.capitalize()

        # Specific patterns for (Fvll) or (Full) style errors
        if "fv" in low_text or "fl" in low_text and "(" in text:
            return "(Full)"

        return text


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



