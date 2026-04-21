import React, { useState } from 'react';
import { Database, Download, CheckCircle2, AlertCircle, RefreshCcw, FileText, Search } from 'lucide-react';
import { useHydraStore } from '../store/useHydraStore';
import { hydraApi, ExtractionQuestion } from '../services/api';
import './Workbench.css';

export const Workbench: React.FC = () => {
  const { scannedPages } = useHydraStore();
  const [selectedDocId, setSelectedDocId] = useState<string | null>(
    scannedPages.length > 0 ? scannedPages[0].id : null
  );
  const [isExporting, setIsExporting] = useState(false);

  const activeDoc = scannedPages.find(p => p.id === selectedDocId);

  const handleFieldChange = async (questionIndex: number, newValue: string) => {
    if (!activeDoc || !activeDoc.result?.extractedData) return;

    const questions = [...activeDoc.result.extractedData.questions];
    const target = questions[questionIndex];
    
    // Update local store immediately for UI responsiveness (optimistic)
    // In a real app, you might want a specific action in useHydraStore for this
    target.selected = newValue;
    
    // Register feedback to Hydra Memory Vault
    if (target.imageHash) {
      await hydraApi.registerFeedback(target.imageHash, newValue);
    }
  };

  const handleExport = async () => {
    try {
      setIsExporting(true);
      const blob = await hydraApi.exportDataset();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Hydra_Export_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Export failed:', err);
      alert('Export failed. Ensure backend is running.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="workbench-station">
      <div className="workbench-browser">
        <div className="browser-header">
          <Database size={14} />
          <span>IN-FLIGHT DOCUMENTS</span>
        </div>
        <div className="browser-list">
          {scannedPages.map((page, idx) => (
            <button
              key={page.id}
              className={`browser-item ${selectedDocId === page.id ? 'active' : ''}`}
              onClick={() => setSelectedDocId(page.id)}
            >
              <div className="item-index">{scannedPages.length - idx}</div>
              <div className="item-meta">
                <span className="item-id">{page.id.substring(0, 8)}...</span>
                <span className={`item-status ${page.status.toLowerCase()}`}>
                  {page.status}
                </span>
              </div>
            </button>
          ))}
          {scannedPages.length === 0 && (
            <div className="browser-empty">No documents found</div>
          )}
        </div>
      </div>

      <div className="workbench-editor">
        {activeDoc ? (
          <div className="editor-container">
            <div className="editor-header">
              <div className="doc-info">
                <FileText className="header-icon" size={24} />
                <div>
                  <h3>Document {activeDoc.id.substring(0, 8)}</h3>
                  <p>Injected {new Date(activeDoc.timestamp).toLocaleTimeString()}</p>
                </div>
              </div>
              <button 
                className="export-btn" 
                onClick={handleExport}
                disabled={isExporting}
              >
                {isExporting ? <RefreshCcw size={16} className="spin" /> : <Download size={16} />}
                <span>EXPORT DATA</span>
              </button>
            </div>

            <div className="grid-container">
              <div className="grid-header">
                <div>SURVEY FIELD</div>
                <div>EXTRACTED VALUE (EDITABLE)</div>
                <div>CONFIDENCE</div>
              </div>

              <div className="grid-body">
                {(activeDoc.status === 'processing' || activeDoc.status === 'uploaded') ? (
                  <div className="grid-loading">
                    <RefreshCcw size={40} className="spin" />
                    <p>Hydra is extracting data... ({activeDoc.status})</p>
                  </div>
                ) : activeDoc.result?.extractedData?.questions ? (
                  activeDoc.result.extractedData.questions.map((q, idx) => (
                    <div key={idx} className="grid-row">
                      <div className="field-label">
                        <span className="row-num">{idx + 1}</span>
                        {q.question}
                      </div>
                      <div className="input-wrapper">
                        <input
                          type="text"
                          defaultValue={q.selected || ''}
                          onBlur={(e) => handleFieldChange(idx, e.target.value)}
                          className={q.confidence > 0.85 ? 'high-conf' : ''}
                        />
                        {q.confidence > 0.95 && <div className="neural-glow-line" />}
                      </div>
                      <div className={`confidence-pill ${q.confidence > 0.9 ? 'certified' : ''}`}>
                        {(q.confidence * 100).toFixed(1)}%
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="grid-loading">
                    <AlertCircle size={40} color="var(--error)" />
                    <p>Extraction failed or no data found.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="workbench-intro">
            <Database size={64} color="var(--on-surface-muted)" />
            <h2>Authority Workbench</h2>
            <p>Select a document from the sidebar to review and verify extraction results.</p>
          </div>
        )}
      </div>
    </div>
  );
};
