import React, { useState } from 'react';
import { 
  CheckCircle, 
  AlertCircle, 
  ChevronRight, 
  Save, 
  FileText,
  BrainCircuit,
  CornerDownRight
} from 'lucide-react';
import { useHydraStore } from '../store/useHydraStore';
import { hydraApi } from '../services/api';
import './Workbench.css';

export const Workbench: React.FC = () => {
  const { scannedPages, updatePageStatus } = useHydraStore();
  const [activePageId, setActivePageId] = useState<string | null>(
    scannedPages.length > 0 ? scannedPages[0].id : null
  );
  const [isSaving, setIsSaving] = useState(false);

  const activePage = scannedPages.find(p => p.id === activePageId);

  const handleCorrection = async (index: number, newValue: string) => {
    if (!activePage || !activePage.result) return;
    
    // Optimistic update
    const updatedResult = { ...activePage.result };
    const field = updatedResult.questions[index];
    const originalValue = field.response;
    field.response = newValue;
    
    updatePageStatus(activePage.id, activePage.status, updatedResult);

    // If it's a real correction, send to Memory Vault
    if (originalValue !== newValue && field.imageHash) {
      await hydraApi.registerFeedback(field.imageHash, newValue);
    }
  };

  return (
    <div className="workbench-station">
      {/* Page Browser Sidebar */}
      <aside className="workbench-browser">
        <div className="browser-header">
          <FileText size={14} />
          <span>SCANNED DOCUMENTS</span>
        </div>
        <div className="browser-list">
          {scannedPages.map((page, idx) => (
            <button 
              key={page.id}
              className={`browser-item ${activePageId === page.id ? 'active' : ''}`}
              onClick={() => setActivePageId(page.id)}
            >
              <div className="item-index">{idx + 1}</div>
              <div className="item-meta">
                <span className="item-id">#SCAN-{page.id.slice(0, 4)}</span>
                <span className={`item-status ${page.status.toLowerCase()}`}>{page.status}</span>
              </div>
              {page.status === 'COMPLETED' && <CheckCircle size={14} className="status-icon" />}
            </button>
          ))}
          {scannedPages.length === 0 && <div className="browser-empty">No scans yet</div>}
        </div>
      </aside>

      {/* Main Review Grid */}
      <main className="workbench-editor">
        {activePage ? (
          <div className="editor-container">
            <div className="editor-header">
              <div className="doc-info">
                <BrainCircuit size={20} className="header-icon" />
                <div>
                  <h3>HYDRA EXTRACTION</h3>
                  <p>Document Precision: {(activePage.result?.avgConfidence || 0 * 100).toFixed(1)}%</p>
                </div>
              </div>
              <div className="header-actions">
                <button className="export-btn">
                  <Save size={16} />
                  <span>EXPORT DATA</span>
                </button>
              </div>
            </div>

            <div className="grid-container">
              <div className="grid-header">
                <div className="col">QUESTION / FIELD</div>
                <div className="col">EXTRACTED RESPONSE</div>
                <div className="col">CONFIDENCE</div>
              </div>
              
              <div className="grid-body">
                {activePage.result?.questions.map((field, idx) => (
                  <div key={idx} className="grid-row">
                    <div className="col field-label">
                      <span className="row-num">{idx + 1}</span>
                      {field.question}
                    </div>
                    <div className="col field-input">
                      <div className="input-wrapper">
                        <input 
                          type="text" 
                          defaultValue={field.response}
                          onBlur={(e) => handleCorrection(idx, e.target.value)}
                          className={field.confidence > 0.8 ? 'high-conf' : ''}
                        />
                        {field.confidence > 0.8 && <div className="neural-glow-line" />}
                      </div>
                    </div>
                    <div className="col field-meta">
                      <div className={`confidence-pill ${field.confidence > 0.8 ? 'certified' : ''}`}>
                        {(field.confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                ))}
                {!activePage.result && (
                  <div className="grid-loading">
                    <RefreshCcw size={24} className="spin" />
                    <span>Hydra is analyzing this document...</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="workbench-intro">
            <AlertCircle size={48} color="var(--on-surface-muted)" />
            <h2>Select a document to begin review</h2>
            <p>Documents scanned in the Command Center will appear in the list on the left.</p>
          </div>
        )}
      </main>
    </div>
  );
};

const RefreshCcw = ({ size, className }: { size: number; className?: string }) => (
  <svg 
    width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" 
    strokeLinecap="round" strokeLinejoin="round" className={className}
  >
    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" />
    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
    <path d="M21 21v-5h-5" />
  </svg>
);
