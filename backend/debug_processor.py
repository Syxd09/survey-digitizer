import sys
sys.path.insert(0, '.')

from services.processor import SurveyProcessor
from PIL import Image as PILImage

print("Loading image...")
img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')

print("Creating processor...")
proc = SurveyProcessor()

print("Processing...")
result = proc.process(img)

print("\nQuestions found:", len(result['questions']))
for i, q in enumerate(result['questions'][:10]):
    print(f"  {i}: {q.get('question', 'N/A')[:50]}")
    print(f"      selected: {q.get('selected')}")
    print(f"      conf: {q.get('confidence')}")

print("\nDiagnostics:", result.get('diagnostics', {}))
