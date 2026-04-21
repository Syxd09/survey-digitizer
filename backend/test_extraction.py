import cv2
import json
import asyncio
import logging
from services.survey_extractor import SurveyExtractor
from services.llm_semantic_refiner import get_semantic_refiner

logging.basicConfig(level=logging.INFO)

async def main():
    image_path = "test_survey.jpg"
    print(f"Loading image: {image_path}")
    image = cv2.imread(image_path)
    
    if image is None:
        print("Failed to load image.")
        return

    print("Running SurveyExtractor...")
    extractor = SurveyExtractor()
    
    # We run extraction. Notice SurveyExtractor now internally calls get_semantic_refiner()
    # at the end to refine the text.
    result = extractor.extract(image)
    
    print("\n--- EXTRACTION RESULT ---")
    print(f"Form Type: {result.form_type}")
    print(f"Header: {result.header_text}")
    print(f"Metadata: {json.dumps(result.form_metadata, indent=2)}")
    print(f"Columns: {result.columns}")
    
    print("\n--- QUESTIONS (After LLM Refinement) ---")
    for q in result.questions:
        print(f"[{q.confidence:.2f}] {q.text}")

if __name__ == "__main__":
    asyncio.run(main())
