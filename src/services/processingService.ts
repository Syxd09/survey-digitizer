/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { FormTemplate, QuestionTemplate } from './templateService';

export interface DetectionResult {
  answers: Record<string, any>;
  confidences: Record<string, number>;
  alignedImageUrl: string;
}

export async function processFormImage(
  imageUrl: string,
  template: FormTemplate,
  pageNumber: number = 1
): Promise<DetectionResult> {
  // 1. Load Image
  const img = await loadImage(imageUrl);
  
  // 2. Image Alignment (Mock perspective correction/normalization)
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d')!;
  canvas.width = 1000; // Normalized width
  canvas.height = 1414; // A4 aspect ratio
  
  // In a real implementation, we'd detect edges and warp the image here.
  // For now, we just draw it to our normalized canvas.
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const alignedImageUrl = canvas.toDataURL('image/jpeg', 0.8);
  
  // 3. Answer Detection Engine
  const answers: Record<string, any> = {};
  const confidences: Record<string, number> = {};
  
  const page = template.pages.find(p => p.pageNumber === pageNumber);
  if (!page) throw new Error(`Page ${pageNumber} not found in template`);

  for (const q of page.questions) {
    if (q.type === 'choice' && q.options) {
      let bestOption = null;
      let maxDensity = -1;
      let secondMaxDensity = -1;
      
      const densities: { value: any; density: number }[] = [];

      for (const opt of q.options) {
        const density = detectMarking(ctx, opt.region, canvas.width, canvas.height);
        densities.push({ value: opt.value, density });
        
        if (density > maxDensity) {
          secondMaxDensity = maxDensity;
          maxDensity = density;
          bestOption = opt.value;
        } else if (density > secondMaxDensity) {
          secondMaxDensity = density;
        }
      }

      answers[q.id] = bestOption;
      
      // Confidence calculation: difference between top two options
      // If one is significantly darker, high confidence.
      const confidence = Math.min(100, Math.max(0, (maxDensity - secondMaxDensity) * 500));
      confidences[q.id] = confidence;
    }
  }

  return { answers, confidences, alignedImageUrl };
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

/**
 * Detects marking in a specific region by analyzing pixel density.
 * Returns a value representing how "marked" the region is.
 */
function detectMarking(
  ctx: CanvasRenderingContext2D,
  region: { x: number; y: number; width: number; height: number },
  canvasWidth: number,
  canvasHeight: number
): number {
  const rx = region.x * canvasWidth;
  const ry = region.y * canvasHeight;
  const rw = region.width * canvasWidth;
  const rh = region.height * canvasHeight;
  
  const imageData = ctx.getImageData(rx, ry, rw, rh);
  const data = imageData.data;
  
  let darkPixels = 0;
  const threshold = 120; // Dark pixel threshold

  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const brightness = (r + g + b) / 3;
    
    if (brightness < threshold) {
      darkPixels++;
    }
  }
  
  return darkPixels / (rw * rh);
}
