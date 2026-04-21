import os
import json
import base64
import logging
import asyncio
import io
import cv2
import numpy as np
from typing import Dict, Any, List, Optional
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image as PILImage
from services.processor import SurveyProcessor

load_dotenv()
logger = logging.getLogger(__name__)

PRECISION_PROMPT = """
You are an expert at reading handwritten survey forms. Analyze the provided image carefully.

HANDWRITING RULES:
- Handwritten text is common on surveys - read it carefully using context clues
- Look for checkmarks (✓), crosses (X), circles around numbers, underlines
- For Likert scales (1-5, 1-7), detect which number is circled or marked
- Handwritten responses may be messy - use context from nearby questions to help decode
- Numbers like 1, 2, 3, 4, 5 should be read even if poorly written
- Date fields often contain dates like DD/MM/YYYY or similar formats
- Names are often capitalized and can have mixed handwriting quality

OUTPUT SCHEMA (Strict JSON - no markdown):
{
  "questions": [
    {
      "id": "q1",
      "question": "Exact question text or inferred from context",
      "options": ["Option 1", "Option 2", ...],
      "selected": "The marked/circled option or handwritten value",
      "confidence": 0.0 to 1.0,
      "status": "OK" or "LOW_CONFIDENCE"
    }
  ],
  "diagnostics": {
    "avg_confidence": 0.0,
    "null_rate": 0.0,
    "logic_version": "Hydra-v5.6-HANDWRITING"
  }
}

CRITICAL:
- Always return valid JSON
- For unmarked questions, selected=null, confidence=0.9, status="OK"
- For handwritten text, confidence should be 0.5-0.8 range
- For clearly printed text, confidence can be 0.9-1.0
"""

class ExtractionOrchestrator:
    def __init__(self):
        # 1. Initialize Local Fail-safe Engine (Primary)
        self.local_processor = SurveyProcessor()

        # 2. Initialize OpenRouter (Fallback)
        or_api_key = os.getenv("VITE_OPENROUTER_API_KEY")
        if or_api_key:
            self.openrouter_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=or_api_key
            )
        else:
            self.openrouter_client = None

        # 3. Initialize Groq (Fallback)
        groq_api_key = os.getenv("VITE_GROQ_API_KEY")
        if groq_api_key:
            self.groq_client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_api_key
            )
        else:
            self.groq_client = None

        # 4. Initialize Google Gemini (Direct - Fallback)
        google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("VITE_GOOGLE_AI_KEY")
        if google_api_key:
            genai.configure(api_key=google_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.gemini_model = None

    async def digitize(self, image_b64: str) -> Dict[str, Any]:
        """Orchestrate extraction using LOCAL OCR only (no cloud dependencies)."""
        # Always try local OCR first - it's reliable and works offline
        engines = [
            ("LOCAL_OCR", self._digitize_local),
        ]

        errors = []
        for name, engine_fn in engines:
            try:
                logger.info(f"[HYDRA] Trying engine: {name}")
                result = await engine_fn(image_b64)
                
                if result and result.get("questions") and len(result["questions"]) > 0:
                    avg_conf = result.get("diagnostics", {}).get("avg_confidence", 0)
                    null_rate = result.get("diagnostics", {}).get("null_rate", 1.0)
                    
                    # Lower threshold for local OCR (it's reliable for most cases)
                    threshold = 0.15
                    
                    if avg_conf < threshold:
                        logger.warning(f"[HYDRA] {name} too low conf ({avg_conf:.2f}<{threshold}).")
                        errors.append(f"{name}: conf={avg_conf:.2f}")
                        continue
                    
                    result["diagnostics"]["engine"] = name
                    result["diagnostics"]["handwriting_mode"] = self._detect_handwriting(image_b64)
                    logger.info(f"[HYDRA] Success: {name}, conf={avg_conf:.2f}, null={null_rate:.2f}, questions={len(result['questions'])}")
                    return result
            except Exception as e:
                logger.error(f"[HYDRA] {name} failed: {e}")
                errors.append(f"{name}: {e}")

        return {
            "questions": [],
            "diagnostics": {"error": "OCR processing failed", "details": errors, "engine": "NONE", "v": "5.7"}
        }

    def _detect_handwriting(self, image_b64: str) -> bool:
        """Detect if image contains handwriting using OCR confidence analysis."""
        try:
            img_data = base64.b64decode(image_b64)
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return True
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Use a fresh reader here to be 100% safe against attribute shadowing
            import easyocr
            temp_reader = easyocr.Reader(['en'], gpu=False)
            results = temp_reader.readtext(img)
            
            # Close/Cleanup if needed (easyocr doesn't require explicit close for CPU)
            
            if not results:
                return True
            
            low_conf = sum(1 for r in results if len(r) >= 3 and r[2] < 0.6)
            total = len(results)
            
            return total > 0 and (low_conf / total) > 0.25
        except Exception as e:
            logger.warning(f"[HYDRA] Handwriting detection error: {e}")
            return True

    async def _digitize_local(self, image_b64: str) -> Optional[Dict[str, Any]]:
        """Run local Python OCR engine as the primary processor."""
        try:
            logger.info("[HYDRA] Running Local Native Engine (EasyOCR + img2table)")
            img_data = base64.b64decode(image_b64)
            pil_img = PILImage.open(io.BytesIO(img_data))
            
            # Use the existing SurveyProcessor
            local_result = self.local_processor.process(pil_img)
            
            questions = local_result.get("questions", [])
            avg_conf = sum(q.get("confidence", 0) for q in questions) / max(1, len(questions)) if questions else 0
            
            return {
                "questions": questions,
                "diagnostics": {
                    "avg_confidence": avg_conf,
                    "null_rate": sum(1 for q in questions if q.get("selected") is None) / max(1, len(questions)) if questions else 1,
                    "logic_version": "Hydra-v5.7-LOCAL"
                }
            }
        except Exception as e:
            logger.error(f"[HYDRA] Local engine failed: {str(e)}")
            return None

    def _resize_image_for_ai(self, image_b64: str, max_size: int = 2048) -> str:
        """Shrink high-res images to save token costs on cloud AI while preserving detail."""
        try:
            img_data = base64.b64decode(image_b64)
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            h, w = img.shape[:2]
            if max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_size = (int(w * scale), int(h * scale))
                img = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)
                
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.warning(f"[HYDRA] Optimization failed, using original: {str(e)}")
            return image_b64

    async def _digitize_openrouter(self, image_b64: str) -> Optional[Dict[str, Any]]:
        if not self.openrouter_client:
            return None

        # Optimization: Shrink image to reduce token cost by ~70%
        optimized_b64 = self._resize_image_for_ai(image_b64)

        response = self.openrouter_client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PRECISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{optimized_b64}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=600 # Smaller response to save credits
        )
        return json.loads(response.choices[0].message.content)

    async def _digitize_groq(self, image_b64: str) -> Optional[Dict[str, Any]]:
        if not self.groq_client:
            return None

        optimized_b64 = self._resize_image_for_ai(image_b64)
        
        try:
            # Using 11b-vision model which is more credit-efficient
            response = self.groq_client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PRECISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{optimized_b64}"
                                },
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=600
            )
            return json.loads(response.choices[0].message.content)
        except Exception:
            return None

    async def _digitize_gemini(self, image_b64: str) -> Optional[Dict[str, Any]]:
        if not self.gemini_model:
            return None

        optimized_b64 = self._resize_image_for_ai(image_b64)
        img_data = base64.b64decode(optimized_b64)
        
        contents = [
            PRECISION_PROMPT,
            {"mime_type": "image/jpeg", "data": img_data}
        ]
        response = self.gemini_model.generate_content(contents)
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        return json.loads(text)
