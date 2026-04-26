const API_BASE = 'http://127.0.0.1:8000';
const API_KEY = import.meta.env.VITE_HYDRA_API_KEY || 'hydra_secret_v2';

const getHeaders = (extra = {}) => ({
  'Content-Type': 'application/json',
  'X-API-Key': API_KEY,
  ...extra
});

export interface ExtractionQuestion {
  question: string;
  selected: string | null;
  confidence: number;
  status: string;
  imageHash?: string;
  bbox?: [number, number, number, number];
  value_bbox?: [number, number, number, number];
}

export interface OrphanText {
  text: string;
  bbox: [number, number, number, number];
  conf: number;
}

export interface SurveyField {
  label: string;
  value: string;
  bbox?: [number, number, number, number];
  value_bbox?: [number, number, number, number];
}

export interface ProcessResponse {
  questions: ExtractionQuestion[];
  diagnostics: any;
}

export interface ScanStatusResponse {
  scanId: string;
  status: 'uploaded' | 'good' | 'bad' | 'conflict' | 'failed' | 'processing' | 'NEEDS_REVIEW' | 'AUTO_ACCEPT' | 'REJECT';
  confidence: number;
  extractedData?: {
    questions: ExtractionQuestion[];
      survey_data?: {
        form_type: string;
        columns: string[];
        column_headers?: string[]; // Legacy compatibility
        header_text: string;
        instructions: string;
        orphans: OrphanText[];
        fields: SurveyField[];
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
      headers: getHeaders(),
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
   * Synchronous Survey Processing: processes image and returns structured survey data
   */
  processSurvey: async (imageBase64: string): Promise<{ scanId: string; questions: ExtractionQuestion[]; survey_data: any }> => {
    const response = await fetch(`${API_BASE}/process-survey`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        image: imageBase64,
        datasetId: 'default-authority',
        userId: 'admin'
      })
    });
    if (!response.ok) throw new Error('Survey processing failed');
    return response.json();
  },

  /**
   * Poll for scan status/results
   */
  getScanStatus: async (scanId: string): Promise<ScanStatusResponse> => {
    const response = await fetch(`${API_BASE}/scan/default-authority/${scanId}`, {
      headers: getHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch scan status');
    return response.json();
  },

  /**
   * Fetch aggregate metrics for a dataset
   */
  getDatasetMetrics: async (): Promise<DatasetMetrics> => {
    const response = await fetch(`${API_BASE}/metrics/default-authority`, {
      headers: getHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch metrics');
    return response.json();
  },

  /**
   * List all scans in a dataset for The Vault
   */
  listScans: async (): Promise<ScanStatusResponse[]> => {
    const response = await fetch(`${API_BASE}/list/default-authority`, {
      headers: getHeaders()
    });
    if (!response.ok) throw new Error('Failed to list scans');
    return response.json();
  },

  /**
   * Register a correction to the Hydra Memory Vault
   */
  registerFeedback: async (
    imageHash: string, 
    originalQuestion?: string,
    correctedQuestion?: string,
    originalAnswer?: string,
    correctedAnswer?: string
  ): Promise<boolean> => {
    try {
      const response = await fetch(`${API_BASE}/feedback`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          scanId: 'manual-correction',
          questionId: 'unknown',
          originalQuestion,
          correctedQuestion,
          originalAnswer,
          correctedAnswer,
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
    const response = await fetch(`${API_BASE}/export?dataset_id=default-authority`, {
      headers: getHeaders()
    });
    if (!response.ok) throw new Error('Export failed');
    return response.blob();
  },

  /**
   * Phase 11: List forms for Review Station
   */
  listForms: async (status?: string): Promise<any> => {
    const url = status ? `${API_BASE}/forms?status=${status}` : `${API_BASE}/forms`;
    const response = await fetch(url, { headers: getHeaders() });
    return response.json();
  },

  /**
   * Phase 11: Get form details
   */
  getFormDetails: async (requestId: string): Promise<any> => {
    const response = await fetch(`${API_BASE}/forms/${requestId}`, {
      headers: getHeaders()
    });
    return response.json();
  },

  /**
   * Phase 11: Correct field
   */
  correctField: async (requestId: string, fieldId: string, value: string): Promise<any> => {
    const response = await fetch(`${API_BASE}/forms/${requestId}/correct`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify({ fieldId, value })
    });
    return response.json();
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
