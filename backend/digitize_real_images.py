"""
Hydra v12.5 — Real Image Digitization Suite
===========================================
Processes all images in the `test-images` directory and exports the results
as structured Markdown files into the `test-results` directory.
"""

import os
import glob
import json
import time
from services.processor import SurveyProcessor

def process_real_images():
    input_dir = "test-images"
    output_dir = "test-results"
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    image_files = sorted(glob.glob(os.path.join(input_dir, "*.[jp][pn]*[g]")))
    
    if not image_files:
        print(f"No images found in {input_dir}/")
        return

    print("=" * 60)
    print(f"🚀 INITIALIZING HYDRA CDP ENGINE for {len(image_files)} real images")
    print("=" * 60)
    
    t0 = time.time()
    processor = SurveyProcessor()
    print(f"   Loaded engine in {time.time() - t0:.2f}s\n")

    for img_path in image_files:
        filename = os.path.basename(img_path)
        base_name = os.path.splitext(filename)[0]
        md_path = os.path.join(output_dir, f"{base_name}_digitized.md")
        
        print("─" * 60)
        print(f"📄 Processing: {filename}")
        
        try:
            t_start = time.time()
            result = processor.process(img_path)
            elapsed = time.time() - t_start
            
            doc_type = result.get("diagnostics", {}).get("doc_type", {}).get("type", "unknown")
            confidence = result.get("diagnostics", {}).get("doc_type", {}).get("confidence", 0)
            questions = result.get("questions", [])
            
            print(f"   ✓ Classified as: {doc_type} (conf: {confidence:.2f})")
            print(f"   ✓ Extracted {len(questions)} fields in {elapsed:.2f}s")
            
            # Generate Markdown Export
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# Digitized Output: {filename}\n\n")
                f.write(f"**Document Type:** `{doc_type}` (Confidence: {confidence:.2f})\n")
                f.write(f"**Processing Time:** {elapsed:.2f} seconds\n\n")
                f.write("## Extracted Data\n\n")
                f.write("| Field / Question | Extracted Value | Confidence | Status |\n")
                f.write("| :--- | :--- | :--- | :--- |\n")
                
                for q in questions:
                    field = q.get("question", "").replace("|", "\\|")
                    val = q.get("selected", "").replace("|", "\\|")
                    conf = f"{q.get('confidence', 0):.2f}"
                    status = q.get("status", "")
                    
                    status_emoji = "✅" if status == "ok" else ("⚠️" if status == "corrected" else "🔍")
                    
                    f.write(f"| **{field}** | {val} | {conf} | {status_emoji} {status} |\n")
                
                f.write("\n## Raw Diagnostics\n")
                f.write("```json\n")
                f.write(json.dumps(result.get("diagnostics", {}), indent=2))
                f.write("\n```\n")
            
            print(f"   ✓ Saved digital version to: {md_path}")
            
        except Exception as e:
            print(f"   ❌ ERROR processing {filename}: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("✨ BATCH PROCESSING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    process_real_images()
