"""
Phase 2 — OCR + Structured Output
=================================
Integrates Google Cloud Vision API to extract word-level data with 
spatial coordinates and confidence scores.
"""

import os
import time
import logging
import base64
import hashlib
from collections import OrderedDict
from typing import List, Dict, Any, Optional
from google.cloud import vision
from google.api_core import exceptions, retry
import easyocr
from config import settings

_OCR_CACHE_MAX_SIZE = 50  # Max cached OCR results to prevent memory leaks


logger = logging.getLogger(__name__)

class OCREngine:
    """Implements Phase 2: Google Cloud Vision OCR integration."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GOOGLE_API_KEY
        self._cache = OrderedDict() # Replaced dict with OrderedDict for LRU caching
        if not self.api_key:
            logger.warning("[Phase 2] No GOOGLE_API_KEY found in config or environment.")
        
        # Initialise client with API key if provided
        client_options = {"api_key": self.api_key} if self.api_key else {}
        try:
            self.client = vision.ImageAnnotatorClient(client_options=client_options)
            logger.info("[Phase 2] Google Cloud Vision client initialised.")
        except Exception as e:
            logger.error(f"[Phase 2] Failed to initialise Vision client: {e}")
            self.client = None

        # Phase 2 Fallback: EasyOCR
        self.local_reader = None
        try:
            self.local_reader = easyocr.Reader(['en'], gpu=False)
            logger.info("[Phase 2] Local EasyOCR engine ready.")
        except Exception as e:
            logger.error(f"[Phase 2] Failed to initialise local OCR: {e}")


    @retry.Retry(predicate=retry.if_exception_type(exceptions.ServiceUnavailable, exceptions.DeadlineExceeded))
    def execute_ocr(self, img_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Executes Google Cloud Vision OCR with in-memory caching.
        """
        img_hash = hashlib.md5(img_bytes).hexdigest()
        
        if img_hash in self._cache:
            logger.info("[Phase 14] Serving OCR from cache.")
            # Move to end to mark as recently used
            result = self._cache.pop(img_hash)
            self._cache[img_hash] = result
            return result

        try:
            if not self.client:
                raise RuntimeError("Vision client not initialised.")
            
            image = vision.Image(content=img_bytes)
            response = self.client.document_text_detection(image=image)
            
            if response.error.message:
                raise RuntimeError(f"Vision API Error: {response.error.message}")
            
            result = self._parse_response(response)
            self._cache[img_hash] = result
            if len(self._cache) > _OCR_CACHE_MAX_SIZE:
                self._cache.popitem(last=False)
            return result
            
        except Exception as e:
            logger.warning(f"[Phase 2] Google OCR failed: {e}. Attempting local fallback...")
            if not self.local_reader:
                logger.error("[Phase 2] No local OCR engine available.")
                raise e
            
            # Execute local OCR
            local_result = self.local_reader.readtext(img_bytes)
            result = self._parse_local_response(local_result)
            self._cache[img_hash] = result
            if len(self._cache) > _OCR_CACHE_MAX_SIZE:
                self._cache.popitem(last=False)
            return result


    def execute_ocr_batch(self, image_list: List[bytes]) -> List[List[Dict[str, Any]]]:
        """
        Phase 14: Implements GCV batching for higher throughput.
        """
        requests = []
        for img_bytes in image_list:
            image = vision.Image(content=img_bytes)
            requests.append({"image": image, "features": [{"type_": vision.Feature.Type.DOCUMENT_TEXT_DETECTION}]})
        
        try:
            batch_response = self.client.batch_annotate_images(requests=requests)
            results = []
            for resp in batch_response.responses:
                if resp.error.message:
                    logger.error(f"Batch item error: {resp.error.message}")
                    results.append([])
                else:
                    results.append(self._parse_response(resp))
            return results
        except Exception as e:
            logger.error(f"[Phase 14] Batch OCR failed: {e}")
            raise

    def _parse_local_response(self, results: List[Any]) -> List[Dict[str, Any]]:
        """Standardises EasyOCR output to pipeline format."""
        words_out = []
        for (bbox, text, conf) in results:
            # bbox is [[x,y], [x,y], [x,y], [x,y]]
            words_out.append({
                "text": text,
                "confidence": round(float(conf), 4),
                "bbox": [[float(v[0]), float(v[1])] for v in bbox]
            })
        logger.info(f"[Phase 2] Local OCR extracted {len(words_out)} words.")
        return words_out

    def _parse_response(self, response) -> List[Dict[str, Any]]:

        """
        Parses Vision API response into a standardised word-level list.
        Each word includes: text, confidence, and normalized bounding box.
        """
        words_out = []
        full_text_obj = response.full_text_annotation

        for page in full_text_obj.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    for word in paragraph.words:
                        word_text = "".join([symbol.text for symbol in word.symbols])
                        
                        # Get bounding box corners
                        vertices = word.bounding_box.vertices
                        if len(vertices) < 4:
                            continue
                            
                        # Standardise bbox to Polygon format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        bbox = [[v.x, v.y] for v in vertices]
                        
                        words_out.append({
                            "text": word_text,
                            "confidence": round(float(word.confidence), 4),
                            "bbox": bbox
                        })

        logger.info(f"[Phase 2] Extracted {len(words_out)} words.")
        return words_out

def get_ocr_engine() -> OCREngine:
    return OCREngine()
