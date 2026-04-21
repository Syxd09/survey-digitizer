import { Quad, detectQuad, warpPerspective, refineAlignment, analyzeImageQuality } from './alignmentService';

import { bufferManager } from './bufferManager';


export interface ExtractedRow {

  sno: string;
  question: string;
  value: string;
  confidence: number;
}

export type ResultState = 'GOOD' | 'PARTIAL' | 'BAD';

export interface DetectionResult {
  rows: ExtractedRow[];
  debugImageUrl: string;
  questionnaireType: string;
  state: ResultState;
  score: number; // 0-1
  brightness: number;
  contrast: number;
  tilt: number;
}



/**
 * Main entry point for local deterministic extraction.
 */
export async function processFormImage(
  imageUrl: string,
  debugEnabled: boolean = true
): Promise<DetectionResult> {
  const img = await loadImage(imageUrl);
  
  // 1. Initial Alignment (Quad Detection + Warp)
  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = img.width;
  tempCanvas.height = img.height;
  const tempCtx = tempCanvas.getContext('2d')!;
  tempCtx.drawImage(img, 0, 0);
  
  const { quad } = detectQuad(tempCanvas);
  let alignedCanvas = await warpPerspective(img, quad, 1000, 1414);

  
  // 2. Grid Refinement (Fine Skew Correction)
  alignedCanvas = await refineAlignment(alignedCanvas);
  const ctx = alignedCanvas.getContext('2d')!;

  // 3. Pre-processing: Adaptive Thresholding
  const { grayscale: thresholdedData } = bufferManager.prepareBuffers(1000 * 1414);
  const rawThresholded = adaptiveThreshold(ctx, 1000, 1414);
  thresholdedData.set(rawThresholded);
  
  // 4. Page Type Validation
  const qType = detectPageType(thresholdedData, 1000, 1414);

  
  const quality = analyzeImageQuality(tempCanvas);
  
  // 5. Region-Based Extraction (Only for SSIAR Templates)
  const rows: ExtractedRow[] = [];
  const debugCtx = createDebugContext(ctx, 1000, 1414);
  
  if (qType.includes('SSIAR')) {
    const isPage2 = qType.includes('Page 2');
    const questionsCount = isPage2 ? 12 : 13;
    const offset = isPage2 ? 13 : 0;
    
    for (let i = 0; i < questionsCount; i++) {
      const qResults = processQuestionRow(thresholdedData, i, debugCtx);
      qResults.sno = (i + 1 + offset).toString(); // Set absolute S.No
      qResults.question = `Survey Question ${qResults.sno}`;
      rows.push(qResults);
    }
  } else {
    console.log("[DETECTION] Deterministic extraction skipped for non-template form.");
  }



  return {
    rows,
    questionnaireType: qType,
    debugImageUrl: debugCtx.canvas.toDataURL(),
    state: 'GOOD', // Simplified for now
    score: 0.95,
    brightness: quality.brightness,
    contrast: quality.contrast,
    tilt: quality.tilt
  };
}



/**
 * Adaptive Thresholding: Handles uneven lighting/shadows.
 */
function adaptiveThreshold(ctx: CanvasRenderingContext2D, w: number, h: number): Uint8Array {
  const imageData = ctx.getImageData(0, 0, w, h);
  const data = imageData.data;
  const result = new Uint8Array(w * h);
  const S = Math.floor(w / 8); // Window size
  const T = 0.15; // Threshold percentage

  // Integral Image for fast local mean calculation
  const integral = new Uint32Array(w * h);
  for (let y = 0; y < h; y++) {
    let sum = 0;
    for (let x = 0; x < w; x++) {
      const idx = (y * w + x);
      const intensity = (data[idx * 4] + data[idx * 4 + 1] + data[idx * 4 + 2]) / 3;
      sum += intensity;
      integral[idx] = (y > 0 ? integral[idx - w] : 0) + sum;
    }
  }

  // Apply Threshold
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const idx = y * w + x;
      const x1 = Math.max(0, x - S / 2);
      const x2 = Math.min(w - 1, x + S / 2);
      const y1 = Math.max(0, y - S / 2);
      const y2 = Math.min(h - 1, y + S / 2);
      const count = (x2 - x1) * (y2 - y1);
      const sum = integral[y2 * w + x2] - integral[y1 * w + x2] - integral[y2 * w + x1] + integral[y1 * w + x1];
      
      const intensity = (data[idx * 4] + data[idx * 4 + 1] + data[idx * 4 + 2]) / 3;
      result[idx] = (intensity * count < sum * (1.0 - T)) ? 1 : 0;
    }
  }
  
  return result;
}

/**
 * Process a single row of questions using multiple metrics.
 */
function processQuestionRow(binaryData: Uint8Array, rowIdx: number, debugCtx: CanvasRenderingContext2D): ExtractedRow {
  const options = [1, 2, 3, 4, 5, 6];
  const scores: { value: number; score: number }[] = [];

  // Refined coordinates based on SSIAR Q2/Q3 form layout
  const rowStartX = 0.435; // Start of the options table
  const rowStartY = 0.148; // First row start
  const rowHeight = 0.056; // Standardized vertical spacing
  const colWidth = 0.082; // Standardized horizontal spacing
  
  const currentY = rowStartY + rowIdx * rowHeight;
  
  const NOISE_FLOOR = 0.10;
  
  options.forEach((val, colIdx) => {
    const rx = rowStartX + colIdx * colWidth;
    const rw = 0.045;
    const rh = 0.038;
    
    const metric = calculateRegionMetrics(binaryData, rx, currentY, rw, rh, 1000, 1414);
    
    // Combined Metric: Density weighted towards the center of the region
    const score = metric.density * 0.7 + metric.edgeDensity * 0.3;
    scores.push({ value: val, score });
    
    drawDebugRect(debugCtx, rx, currentY, rw, rh, score, `${val} (${score.toFixed(2)})`);
  });

  // Log detection matrix for transparency
  console.log(`[DETECTION] Q${rowIdx + 1} Matrix:`, scores.map(s => `[${s.value}: ${s.score.toFixed(3)}]`).join(' '));


  scores.sort((a, b) => b.score - a.score);
  
  const top1 = scores[0];
  const top2 = scores[1];
  
  // Noise Floor Check: If absolute top score is too low, it's a silent region
  const isUndetected = top1.score < NOISE_FLOOR;

  
  // Robust confidence: (Top1 - Top2) / Top1
  const confidence = top1.score > 0.01 ? (top1.score - top2.score) / top1.score : 0;

  return {
    sno: (rowIdx + 1).toString(),
    question: `Survey Question ${rowIdx + 1}`,
    value: isUndetected ? "undetected" : top1.value.toString(),
    confidence: isUndetected ? 0 : Math.round(confidence * 100)
  };

}

function calculateRegionMetrics(data: Uint8Array, rx: number, ry: number, rw: number, rh: number, w: number, h: number) {
  const x1 = Math.floor(rx * w);
  const y1 = Math.floor(ry * h);
  const x2 = Math.floor((rx + rw) * w);
  const y2 = Math.floor((ry + rh) * h);
  
  let darkPixels = 0;
  let edges = 0;
  
  const width = x2 - x1;
  const height = y2 - y1;
  const regionData = new Uint8Array(width * height);

  for (let y = y1; y < y2; y++) {
    for (let x = x1; x < x2; x++) {
      const idx = y * w + x;
      const ridx = (y - y1) * width + (x - x1);
      if (data[idx] === 1) {
        darkPixels++;
        regionData[ridx] = 1;
      }
      
      // Basic edge detection (absolute diff with neighbor)
      if (x < x2 - 1 && data[idx] !== data[idx + 1]) edges++;
      if (y < y2 - 1 && data[idx] !== data[idx + w]) edges++;
    }
  }
  
  const ccResult = countConnectedComponents(regionData, width, height);
  const total = width * height;
  
  // Normalized Continuity: Largest component size relative to expected bubble size
  const continuity = ccResult.maxSize / (width * height * 0.5);
  
  return {
    density: darkPixels / total,
    edgeDensity: edges / total,
    blobCount: ccResult.count,
    continuity: Math.min(1.0, continuity)
  };
}

/**
 * 8-way Connected Component Analysis using BFS.
 */
function countConnectedComponents(data: Uint8Array, w: number, h: number): { count: number; maxSize: number } {
  let count = 0;
  let maxSize = 0;
  const visited = new Uint8Array(w * h);
  const queue: number[] = [];

  for (let i = 0; i < data.length; i++) {
    if (data[i] === 1 && !visited[i]) {
      count++;
      let currentSize = 0;
      queue.push(i);
      visited[i] = 1;

      while (queue.length > 0) {
        const curr = queue.shift()!;
        currentSize++;
        const cx = curr % w;
        const cy = Math.floor(curr / w);

        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            const nx = cx + dx;
            const ny = cy + dy;
            if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
              const nidx = ny * w + nx;
              if (data[nidx] === 1 && !visited[nidx]) {
                visited[nidx] = 1;
                queue.push(nidx);
              }
            }
          }
        }
      }
      if (currentSize > maxSize) maxSize = currentSize;
    }
  }
  return { count, maxSize };
}



function detectPageType(data: Uint8Array, w: number, h: number): string {
  // Check for SSIAR Q2 Page 1 Marker (Top Header)
  const headerMetric = calculateRegionMetrics(data, 0.4, 0.05, 0.2, 0.04, w, h);
  
  // Check for SSIAR Q2 Page 2 Marker
  const page2Marker = calculateRegionMetrics(data, 0.8, 0.02, 0.1, 0.05, w, h);
  
  if (headerMetric.density > 0.03) {
    return "SSIAR Q2 (Page 1)";
  } else if (page2Marker.density > 0.02) {
    return "SSIAR Q2 (Page 2)";
  }
  
  // No recognized template marker found
  console.log("[DETECTION] No template matched. Defaulting to AI_SMART_MODE.");
  return "AI_SMART_MODE";
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

function createDebugContext(origCtx: CanvasRenderingContext2D, w: number, h: number): CanvasRenderingContext2D {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(origCtx.canvas, 0, 0);
  return ctx;
}

function drawDebugRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, score: number, label: string) {
  const color = score > 0.15 ? '#4ade80' : score > 0.05 ? '#facc15' : '#f87171';
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.strokeRect(x * 1000, y * 1414, w * 1000, h * 1414);
  
  ctx.fillStyle = color;
  ctx.font = 'bold 12px monospace';
  ctx.fillText(label, x * 1000, y * 1414 - 5);
}
