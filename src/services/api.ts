const API_BASE = 'http://localhost:8000';

export interface ExtractionQuestion {
  id: string;
  question: string;
  response: string;
  confidence: number;
  type: string;
  imageHash?: string;
}

export interface ProcessResponse {
  success: boolean;
  scanId: string;
  questions: ExtractionQuestion[];
  total: number;
  avgConfidence: number;
  diagnostics: any;
}

export const hydraApi = {
  /**
   * Directly digitize an image using Hydra V10.1
   */
  process: async (imageBase64: string): Promise<ProcessResponse> => {
    const response = await fetch(`${API_BASE}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: imageBase64,
        datasetId: 'default-authority',
        userId: 'admin'
      })
    });
    
    if (!response.ok) throw new Error('Hydra Engine failed to process');
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
