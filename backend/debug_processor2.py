import sys
sys.path.insert(0, 'E:/webProgramming/survey-digitizer/backend')

# Force reimport
import importlib
if 'services.processor' in sys.modules:
    del sys.modules['services.processor']

from services.processor import SurveyProcessor
from PIL import Image as PILImage
import logging
logging.basicConfig(level=logging.INFO)

img = PILImage.open('E:/webProgramming/survey-digitizer/test-file.png')
print("Created processor...")
proc = SurveyProcessor()
print("Processing image...")
result = proc.process(img)
print(f"\nQuestions found: {len(result['questions'])}")
for i, q in enumerate(result['questions'][:5]):
    print(f"  {i}: {q.get('question', 'N/A')[:60]}")
    print(f"      selected: {q.get('selected')}")
    print(f"      conf: {q.get('confidence')}")