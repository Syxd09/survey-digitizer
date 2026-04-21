import os
import json
import logging
from typing import List, Dict, Optional
from pydantic import BaseModel
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class CorrectionItem(BaseModel):
    index: int
    corrected_text: str

class CorrectionResponse(BaseModel):
    corrections: List[CorrectionItem]

class LLMSemanticRefiner:
    def __init__(self):
        self.memory_file = "backend/feedback_loop/corrections.json"
        
        # Ensure memory directory exists
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        
        # Configure fallback providers
        self.providers = []
        
        # 1. Groq (Fastest)
        if groq_key := os.getenv("VITE_GROQ_API_KEY"):
            self.providers.append({
                "name": "Groq",
                "type": "openai",
                "client": OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"),
                "model": "llama3-70b-8192"
            })
            
        # 2. OpenRouter (High quality models)
        if or_key := os.getenv("VITE_OPENROUTER_API_KEY"):
            or_model = os.getenv("VITE_AI_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
            self.providers.append({
                "name": "OpenRouter",
                "type": "openai",
                "client": OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1"),
                "model": or_model
            })
            
        # 3. xAI (Grok)
        if xai_key := os.getenv("VITE_XAI_API_KEY"):
            self.providers.append({
                "name": "xAI",
                "type": "openai",
                "client": OpenAI(api_key=xai_key, base_url="https://api.x.ai/v1"),
                "model": "grok-beta"
            })
            
        # 4. Cerebras (Very fast inference)
        if cer_key := os.getenv("VITE_CEREBRAS_API_KEY"):
            self.providers.append({
                "name": "Cerebras",
                "type": "openai",
                "client": OpenAI(api_key=cer_key, base_url="https://api.cerebras.ai/v1"),
                "model": "llama3.1-8b"
            })
            
        # 5. Google Gemini (Original fallback)
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("VITE_GOOGLE_AI_KEY")
        if google_key:
            genai.configure(api_key=google_key)
            self.providers.append({
                "name": "Google Gemini",
                "type": "gemini",
                "model": genai.GenerativeModel(
                    'gemini-1.5-flash',
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    )
                )
            })

        self.enabled = len(self.providers) > 0
        
        if self.enabled:
            logger.info(f"[LLM] Semantic Refiner initialized with {len(self.providers)} fallback providers.")
        else:
            logger.warning("[LLM] Semantic Refiner disabled. No API keys found.")

    def _load_memory(self) -> List[Dict]:
        """Load past corrections to use as few-shot examples."""
        if not os.path.exists(self.memory_file):
            return []
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[LLM] Failed to load memory: {e}")
            return []

    def _call_provider(self, provider: dict, prompt: str) -> str:
        if provider["type"] == "openai":
            client: OpenAI = provider["client"]
            response = client.chat.completions.create(
                model=provider["model"],
                messages=[
                    {"role": "system", "content": "You are a helpful JSON assistant. Always output raw JSON starting with { and ending with }."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"} if "groq" in provider["name"].lower() or "openai" in provider["type"] else None
            )
            return response.choices[0].message.content
        elif provider["type"] == "gemini":
            response = provider["model"].generate_content(prompt)
            return response.text
        raise ValueError(f"Unknown provider type: {provider['type']}")

    def refine_questions(self, raw_header: str, form_type: str, questions: List[str]) -> List[str]:
        """
        Takes a list of raw OCR questions and uses the LLM to semantically refine them.
        Returns the list of refined questions.
        """
        if not self.enabled or not questions:
            return questions

        past_corrections = self._load_memory()
        
        memory_prompt = ""
        if past_corrections:
            memory_prompt = "LEARNING MEMORY - Pay close attention to these past mistakes to avoid repeating them:\n"
            for c in past_corrections[-20:]: # Take last 20 corrections to avoid context limits
                memory_prompt += f"- OCR saw: '{c['original']}' -> Corrected to: '{c['corrected']}'\n"

        # Build the indexed list
        questions_block = "\n".join([f"[{i}] {q}" for i, q in enumerate(questions)])

        prompt = f"""You are an expert Proofreader and Semantic Reasoner for an OCR extraction pipeline.
Your job is to read raw, messy text extracted from a handwritten or printed '{form_type}' survey, and return the semantically correct text.

INSTRUCTIONS:
1. Fix spelling, grammar, and obvious OCR artifact errors.
2. Use reasoning: If the text says "Wbat 1s your narne?", it should be "What is your name?".
3. Do NOT change the core meaning or intention of the question.
4. Output strict JSON with a "corrections" array.

EXPECTED JSON SCHEMA:
{{
  "corrections": [
    {{"index": 0, "corrected_text": "Corrected question text..."}}
  ]
}}

FORM CONTEXT (Use this to understand the topic of the questions):
{raw_header}

{memory_prompt}

RAW OCR QUESTIONS TO CORRECT:
{questions_block}
"""

        for provider in self.providers:
            try:
                logger.info(f"[LLM] Attempting semantic refinement with {provider['name']}...")
                response_text = self._call_provider(provider, prompt)
                
                # Parse the structured JSON response, handling potential markdown blocks
                if response_text is None:
                    continue
                    
                response_text = response_text.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                logger.info(f"[LLM] {provider['name']} Raw Output:\n{response_text}")
                    
                result_data = json.loads(response_text)
                
                # Create a mutable copy of the original questions
                refined_questions = list(questions)
                
                success = False
                for correction in result_data.get("corrections", []):
                    idx = correction.get("index")
                    corrected_text = correction.get("corrected_text")
                    if idx is not None and 0 <= idx < len(refined_questions):
                        logger.info(f"[LLM] Refined: '{refined_questions[idx]}' -> '{corrected_text}'")
                        refined_questions[idx] = corrected_text
                        success = True
                
                if success or len(result_data.get("corrections", [])) == 0:
                    return refined_questions
                    
            except Exception as e:
                logger.warning(f"[LLM] Provider {provider['name']} failed: {e}")
                continue # Try next provider
                
        logger.error("[LLM] All fallback API providers failed. Returning original text.")
        return questions

    def add_correction(self, original: str, corrected: str):
        """Append a user correction to the local memory file."""
        if not original or not corrected or original == corrected:
            return
            
        memory = self._load_memory()
        
        # Don't add exact duplicates
        if any(m['original'] == original and m['corrected'] == corrected for m in memory):
            return
            
        memory.append({
            "original": original,
            "corrected": corrected
        })
        
        try:
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, indent=2)
            logger.info(f"[LLM] Learned new pattern: '{original}' -> '{corrected}'")
        except Exception as e:
            logger.error(f"[LLM] Failed to save correction to memory: {e}")

# Global instance
_refiner_instance = None

def get_semantic_refiner() -> LLMSemanticRefiner:
    global _refiner_instance
    if _refiner_instance is None:
        _refiner_instance = LLMSemanticRefiner()
    return _refiner_instance
