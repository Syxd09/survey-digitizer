import { create } from 'zustand';

export type Station = 'COMMAND_CENTER' | 'WORKBENCH' | 'VAULT' | 'ANALYTICS';

interface ExtractionResult {
  scanId: string;
  questions: any[];
  avgConfidence: number;
  diagnostics: any;
}

interface ScannedPage {
  id: string;
  image: string; // base64
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  result?: ExtractionResult;
  timestamp: string;
}

interface HydraState {
  activeStation: Station;
  scannedPages: ScannedPage[];
  activeDatasetId: string;
  engineHealth: 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
  
  // Actions
  setStation: (station: Station) => void;
  addPage: (image: string) => string;
  updatePageStatus: (id: string, status: ScannedPage['status'], result?: ExtractionResult) => void;
  removePage: (id: string) => void;
  setEngineHealth: (health: HydraState['engineHealth']) => void;
}

export const useHydraStore = create<HydraState>((set) => ({
  activeStation: 'COMMAND_CENTER',
  scannedPages: [],
  activeDatasetId: 'default-authority',
  engineHealth: 'HEALTHY',

  setStation: (station) => set({ activeStation: station }),
  
  addPage: (image) => {
    const id = Math.random().toString(36).substring(7);
    set((state) => ({
      scannedPages: [
        {
          id,
          image,
          status: 'PENDING',
          timestamp: new Date().toISOString(),
        },
        ...state.scannedPages,
      ],
    }));
    return id;
  },

  updatePageStatus: (id, status, result) =>
    set((state) => ({
      scannedPages: state.scannedPages.map((p) =>
        p.id === id ? { ...p, status, result: result || p.result } : p
      ),
    })),

  removePage: (id) =>
    set((state) => ({
      scannedPages: state.scannedPages.filter((p) => p.id !== id),
    })),

  setEngineHealth: (health) => set({ engineHealth: health }),
}));
