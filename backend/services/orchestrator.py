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

# Load credentials
load_dotenv()

logger = logging.getLogger(__name__)

# SYSTEM PROMPT FOR PRECISION DIGITIZATION
PRECISION_PROMPT = """
Analyze the provided image of a survey form and extract all question-response pairs with 100% precision.
The form may contain tables with checkmarks, circled numbers (Likert scales), or handwritten text.

OUTPUT SCHEMA (Strict JSON):
{
  "questions": [
    {
      "id": "q1",
      "question": "Exact text of the question",
      "options": ["Option 1", "Option 2", ...],
      "selected": "The exact text or number of the marked/circled option",
      "confidence": 0.0 to 1.0,
      "status": "OK" or "LOW_CONFIDENCE" (if ambiguous)
    }
  ],
  "diagnostics": {
    "avg_confidence": 0.0,
    "null_rate": 0.0,
    "logic_version": "Hydra-v5.0-LOCAL-FIRST"
  }
}

RULES:
1. If a row has no mark, set "selected" to null and confidence to 1.0.
2. If multiple marks exist for one question, set status to "LOW_CONFIDENCE".
3. Maintain the order of questions as they appear on the page.
4. Extract the EXACT text of the question.
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
        """Orchestrate multi-model extraction with LOCAL-FIRST priority."""
        # LOCAL is now #1 to bypass API credit limits and ensure 100% uptime
        engines = [
            ("LOCAL_OCR", self._digitize_local),
            ("OPENROUTER", self._digitize_openrouter),
            ("GROQ_LAVA", self._digitize_groq),
            ("GEMINI_DIRECT", self._digitize_gemini)
        ]

        errors = []
        for name, engine_fn in engines:
            try:
                logger.info(f"[HYDRA] Attempting extraction with engine: {name}")
                result = await engine_fn(image_b64)
                if result and result.get("questions") and len(result["questions"]) > 0:
                    result["diagnostics"]["engine"] = name
                    return result
            except Exception as e:
                logger.error(f"[HYDRA] Engine {name} failed: {str(e)}")
                errors.append(f"{name}: {str(e)}")

        # Final Fallback: Return empty result with error details
        return {
            "questions": [],
            "diagnostics": {
                "error": "All AI engines failed",
                "details": errors,
                "engine": "NONE",
                "v": "5.0-RESCUE"
            }
        }

    async def _digitize_local(self, image_b64: str) -> Optional[Dict[str, Any]]:
        """Run local Python OCR engine as the primary processor."""
        try:
            logger.info("[HYDRA] Running Local Native Engine (EasyOCR + img2table)")
            img_data = base64.b64decode(image_b64)
            pil_img = PILImage.open(io.BytesIO(img_data))
            
            # Use the existing SurveyProcessor
            local_result = self.local_processor.process(pil_img)
            
            return {
                "questions": local_result.get("questions", []),
                "diagnostics": {
                    "avg_confidence": sum(q.get("confidence", 0) for q in local_result.get("questions", [])) / max(1, len(local_result.get("questions", []))),
                    "null_rate": sum(1 for q in local_result.get("questions", []) if q.get("selected") is None) / max(1, len(local_result.get("questions", []))),
                    "logic_version": "Hydra-v5.0-LOCAL"
                }
            }
        except Exception as e:
            logger.error(f"[HYDRA] Local engine failed: {str(e)}")
            return None

    def _resize_image_for_ai(self, image_b64: str, max_size: int = 1500) -> str:
        """Shrink high-res images to save token costs on cloud AI."""
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
