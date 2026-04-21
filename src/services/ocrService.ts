import { processFormImage, DetectionResult } from './processingService';
import { auth } from '../lib/firebase';

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
 * Step 1: Ingest Form Image into Production Backend Queue
 */
export async function ingestFormForProcessing(
  imageBase64: string,
  datasetId: string,
  userId: string
): Promise<{ success: boolean; scanId: string; taskId: string }> {
  // Get Auth Token for Security Enforcement
  const currentUser = auth.currentUser;
  if (!currentUser) throw new Error("Authentication required for processing");
  
  const token = await currentUser.getIdToken();

  const response = await fetch(`${BACKEND_URL}/ingest`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
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
}

/**
 * Step 2: Poll for Result (In a full app, this would use Firestore listeners)
 * This logic will be migrated to Firestore listeners in App.tsx for better scalability.
 */
export async function pollProcessingStatus(scanId: string, datasetId: string): Promise<ExtractionResult | null> {
  // Note: For production-grade polling, we will use Firestore onSnapshot in App.tsx.
  // This helper is for manual checks if needed.
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
