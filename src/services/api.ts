const API_BASE = 'http://localhost:8000';

export interface ExtractionQuestion {
  question: string;
  selected: string | null;
  confidence: number;
  status: string;
  imageHash?: string;
}

export interface ProcessResponse {
  questions: ExtractionQuestion[];
  diagnostics: any;
}

export interface ScanStatusResponse {
  scanId: string;
  status: 'uploaded' | 'good' | 'bad' | 'conflict' | 'failed' | 'processing';
  confidence: number;
  extractedData?: {
    questions: ExtractionQuestion[];
    survey_data?: {
      form_type: string;
      columns: string[];
      column_headers?: string[]; // Legacy compatibility
      header_text: string;
      instructions: string;
      form_metadata: {
        raw_header?: string;
        study_code?: string;
        title?: string;
        form_number?: string;
        [key: string]: any;
      };
    };
  };
  diagnostics?: any;
  error?: string;
}

export interface DatasetMetrics {
  total_forms: number;
  avg_processing_time: number;
  avg_confidence: number;
  avg_null_rate: number;
  throughput_fpm: number;
  status_distribution: Record<string, number>;
  failure_rate: number;
  conflict_rate: number;
}

export const hydraApi = {
  /**
   * Async Ingest: returns scanId immediately
   */
  ingest: async (imageBase64: string): Promise<{ scanId: string }> => {
    const response = await fetch(`${API_BASE}/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: imageBase64,
        datasetId: 'default-authority',
        userId: 'admin'
      })
    });
    if (!response.ok) throw new Error('Hydra Ingestion failed');
    return response.json();
  },

  /**
   * Poll for scan status/results
   */
  getScanStatus: async (scanId: string): Promise<ScanStatusResponse> => {
    const response = await fetch(`${API_BASE}/scan/default-authority/${scanId}`);
    if (!response.ok) throw new Error('Failed to fetch scan status');
    return response.json();
  },

  /**
   * Fetch aggregate metrics for a dataset
   */
  getDatasetMetrics: async (): Promise<DatasetMetrics> => {
    const response = await fetch(`${API_BASE}/metrics/default-authority`);
    if (!response.ok) throw new Error('Failed to fetch metrics');
    return response.json();
  },

  /**
   * List all scans in a dataset for The Vault
   */
  listScans: async (): Promise<ScanStatusResponse[]> => {
    const response = await fetch(`${API_BASE}/list/default-authority`);
    if (!response.ok) throw new Error('Failed to list scans');
    return response.json();
  },

  /**
   * Register a correction to the Hydra Memory Vault
   */
  registerFeedback: async (imageHash: string, correctedText: string): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scanId: 'manual-correction',
          questionId: 'unknown',
          correctedText,
          imageHash
        })
      });
      const data = await response.json();
      return data.success;
    } catch (error) {
      console.error('Feedback failed:', error);
      return false;
    }
  },

  /**
   * Export dataset as Excel (blob)
   */
  exportDataset: async (): Promise<Blob> => {
    const response = await fetch(`${API_BASE}/export?dataset_id=default-authority`);
    if (!response.ok) throw new Error('Export failed');
    return response.blob();
  },

  /**
   * Engine Health Check
   */
  checkHealth: async (): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
};
