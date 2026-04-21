import { processFormImage, DetectionResult } from './processingService';
import { getCurrentUser } from '../lib/localAuth';

export const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

/**
 * Interface representing the standardized extraction result from the backend.
 */
export interface ExtractionRow {
  sno: string;
  question: string;
  value: string;
  confidence: number;
  options?: string[];
  suggestions?: { value: string; score: number }[];
  status?: 'OK' | 'LOW_CONFIDENCE' | 'NOT_DETECTED';
}

export interface ExtractionResult {
  scanId: string;
  questionnaireType: string;
  rows: ExtractionRow[];
  overallConfidence: number;
  debugImageUrl?: string;
  status: 'pending' | 'completed' | 'failed' | 'conflict';
  error?: string;
  // Legacy / Metadata fields for UI compatibility
  extractionTier?: 'DETERMINISTIC' | 'OCR' | 'AI_SMART' | 'FAILED';
  pipelineMode?: 'TABLE' | 'OCR';
  preRetakeConfidence?: number;
  logicVersion?: string;
  diagnostics?: any;
}

/**
 * Ingest Form Image — tries backend first, falls back to local processing.
 */
export async function ingestFormForProcessing(
  imageBase64: string,
  datasetId: string,
  userId: string
): Promise<{ success: boolean; scanId: string; taskId: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/ingest`, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        image: imageBase64,
        datasetId,
        userId
      })
    });

    if (!response.ok) {
      throw new Error(`Ingestion failed: ${response.statusText}`);
    }

    return await response.json();
  } catch (err) {
    // Backend unavailable — fall back to local processing
    console.warn('[INGEST] Backend unavailable, falling back to local processing:', err);
    const scanId = crypto.randomUUID();
    return { success: true, scanId, taskId: `local-${scanId}` };
  }
}

/**
 * Process a form image entirely in the browser using the local deterministic pipeline.
 * Used as fallback when the backend is unavailable.
 */
export async function processFormLocally(imageUrl: string): Promise<ExtractionResult> {
  try {
    const result = await processFormImage(imageUrl, true);
    const scanId = crypto.randomUUID();

    return {
      scanId,
      questionnaireType: result.questionnaireType,
      rows: result.rows.map(r => ({
        ...r,
        options: ['1', '2', '3', '4', '5', '6'],
        status: r.confidence > 50 ? 'OK' as const : r.value === 'undetected' ? 'NOT_DETECTED' as const : 'LOW_CONFIDENCE' as const,
      })),
      overallConfidence: result.score,
      debugImageUrl: result.debugImageUrl,
      status: 'completed',
      extractionTier: 'DETERMINISTIC',
      pipelineMode: 'TABLE',
      logicVersion: 'local-v1.0',
      diagnostics: {
        engine: 'LOCAL_DETERMINISTIC',
        brightness: result.brightness,
        contrast: result.contrast,
        tilt: result.tilt
      }
    };
  } catch (err) {
    console.error('[LOCAL_PROCESS] Failed:', err);
    throw err;
  }
}

/**
 * Poll for Result
 */
export async function pollProcessingStatus(scanId: string, datasetId: string): Promise<ExtractionResult | null> {
  return null; 
}

/**
 * Helper to convert Blob URLs to Base64
 */
export async function toBase64(url: string): Promise<string> {
  if (url.startsWith('data:image')) return url;
  const response = await fetch(url);
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
