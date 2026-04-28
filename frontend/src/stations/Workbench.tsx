import React, { useState } from 'react';
import { Database, Download, CheckCircle2, AlertCircle, RefreshCcw, FileText, Search } from 'lucide-react';
import { useHydraStore } from '../store/useHydraStore';
import { hydraApi, ExtractionQuestion } from '../services/api';
import { DigitalSurveyForm } from '../components/DigitalSurveyForm';
import { RealityView } from '../components/RealityView';
import { ImageViewer } from '../components/ImageViewer';
import './Workbench.css';

export const Workbench: React.FC = () => {
  const { scannedPages, selectedDocId, setSelectedDocId } = useHydraStore();
  
  // Auto-select first if none selected
  React.useEffect(() => {
    if (!selectedDocId && scannedPages.length > 0) {
      setSelectedDocId(scannedPages[0].id);
    }
  }, [scannedPages, selectedDocId, setSelectedDocId]);

  const [isExporting, setIsExporting] = useState(false);
  const [isApproved, setIsApproved] = useState(false);
  const [viewMode, setViewMode] = useState<'digital' | 'grid' | 'table' | 'reality' | 'viewer' | 'report'>('report');
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const activeDoc = scannedPages.find(p => p.id === selectedDocId);

  const handleFeedback = async (questionIndex: number, type: 'question' | 'answer', newValue: string) => {
    if (!activeDoc || !activeDoc.result?.extractedData) return;

    const questions = [...activeDoc.result.extractedData.questions];
    const target = questions[questionIndex];
    
    let originalQuestion = target.question;
    let originalAnswer = target.selected || '';
    
    if (type === 'question') {
      if (originalQuestion === newValue) return;
      target.question = newValue; // optimistic update
      if (target.imageHash) {
        await hydraApi.registerFeedback(target.imageHash, originalQuestion, newValue, undefined, undefined);
      }
    } else {
      if (originalAnswer === newValue) return;
      target.selected = newValue; // optimistic update
      if (target.imageHash) {
        await hydraApi.registerFeedback(target.imageHash, undefined, undefined, originalAnswer, newValue);
      }
    }
  };

  const handleApproveSurvey = async (approvedQuestions: ExtractionQuestion[]) => {
    if (!activeDoc || !activeDoc.result?.extractedData) return;
    
    // Calculate Active Learning corrections
    const originalQuestions = activeDoc.result.extractedData.questions || [];
    const corrections: { originalText: string, correctedText: string }[] = [];
    
    approvedQuestions.forEach((approvedQ, i) => {
      const originalQ = originalQuestions[i];
      if (originalQ && originalQ.question !== approvedQ.question) {
        corrections.push({
          originalText: originalQ.question,
          correctedText: approvedQ.question
        });
      }
    });
    
    try {
      setIsExporting(true); // Re-using export state for loading indicator
      const response = await fetch('http://127.0.0.1:8000/approve-survey', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scanId: activeDoc.id,
          datasetId: 'default-authority',
          questions: approvedQuestions,
          corrections: corrections
        })
      });
      if (response.ok) {
        setIsApproved(true);
        // Reset approval state after some time or if selection changes
        setTimeout(() => setIsApproved(false), 10000);
      } else {
        alert('Failed to save survey approval.');
      }
    } catch (e) {
      console.error('Survey approval failed:', e);
      alert('Survey approval failed. Ensure backend is running.');
    } finally {
      setIsExporting(false);
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

            {isApproved && (
              <div className="approval-success-overlay">
                <div className="success-card">
                  <CheckCircle2 size={48} color="var(--success)" />
                  <h2>SURVEY APPROVED</h2>
                  <p>The extraction has been verified and saved to the authority database.</p>
                  <div className="success-actions">
                    <button className="btn-download-now" onClick={handleExport}>
                      <Download size={18} />
                      <span>DOWNLOAD UPDATED EXCEL</span>
                    </button>
                    <button className="btn-dismiss" onClick={() => setIsApproved(false)}>DISMISS</button>
                  </div>
                </div>
              </div>
            )}

              <div className="workbench-main-workspace">
              {/* Left Side: Reality/Image Preview */}
              <div className="workbench-preview-side">
                <div className="preview-container">
                  <img src={activeDoc.image} alt="Original document" className={!activeDoc.result ? 'dimmed' : ''} />
                  {!activeDoc.result && <div className="scanning-line" />}
                </div>
              </div>

              {/* Right Side: Results (Always visible, loader integrated) */}
              <div className="workbench-results-side">
                <div className="results-header">
                  <div className="results-title">
                    <div className="status-indicator">
                      {!activeDoc.result ? (
                        <div className="neural-ping">
                          <RefreshCcw size={16} className="spin" />
                          <span>NEURAL EXTRACTION IN PROGRESS...</span>
                        </div>
                      ) : (
                        <div className="result-check">
                          <CheckCircle2 size={16} />
                          <span>EXTRACTION COMPLETE</span>
                        </div>
                      )}
                    </div>
                    <h2>Digitized Survey Results</h2>
                  </div>
                  <div className="view-selector">
                    <button className={viewMode === 'report' ? 'active' : ''} onClick={() => setViewMode('report')}>Result View</button>
                    <button className={viewMode === 'reality' ? 'active' : ''} onClick={() => setViewMode('reality')}>Reality View</button>
                    <button className={viewMode === 'digital' ? 'active' : ''} onClick={() => setViewMode('digital')}>Digital View</button>
                  </div>
                </div>

                <div className="results-content">
                  {!activeDoc.result && (
                    <div className="scanning-hud">
                      <div className="hud-metric">
                        <span className="hud-label">NEURAL THREADS</span>
                        <span className="hud-value">16 ACTIVE</span>
                      </div>
                      <div className="hud-metric">
                        <span className="hud-label">SYMBOL CONFIDENCE</span>
                        <span className="hud-value">CALCULATING...</span>
                      </div>
                      <div className="hud-progress-bar">
                        <div className="progress-fill" />
                      </div>
                    </div>
                  )}

                  {viewMode === 'report' ? (
                    <table className="digitized-result-table">
                      <thead>
                        <tr>
                          <th>Question</th>
                          <th>Survey Label</th>
                          <th>Physical Mark</th>
                          <th>Digitized Value</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeDoc.result?.extractedData?.questions ? (
                          activeDoc.result.extractedData.questions.map((q: any, idx: number) => {
                            const isSDQ = q.id && q.id.startsWith('q');
                            const val = q.digitized_value || (
                              q.raw_value === 'Certainly True' ? '3' : 
                              q.raw_value === 'Somewhat True' ? '2' : 
                              q.raw_value === 'Not True' ? '1' : 
                              q.raw_value
                            );
                            
                            let physicalMark = q.raw_value === 'UNANSWERED' ? 'None' : q.raw_value;
                            if (isSDQ) {
                              if (q.raw_value === 'Certainly True') physicalMark = 'Certainly True (3rd Col)';
                              else if (q.raw_value === 'Somewhat True') physicalMark = 'Somewhat True (2nd Col)';
                              else if (q.raw_value === 'Not True') physicalMark = 'Not True (1st Col)';
                            }

                            return (
                              <tr key={q.id || idx} className={q.confidence < 0.8 ? 'low-conf-row' : ''}>
                                <td className="q-id">{q.id ? q.id.toUpperCase() : `Q${idx + 1}`}</td>
                                <td className="q-label">{q.name || q.question}</td>
                                <td className="p-mark">{physicalMark}</td>
                                <td className="d-val">{val}</td>
                                <td className="status-cell">
                                  {q.status === 'OK' || q.confidence > 0.8 ? (
                                    <span className="badge-success">✅ Correct</span>
                                  ) : (
                                    <span className="badge-warning">⚠️ Review</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })
                        ) : (
                          [1, 2, 3, 4, 5, 6].map((i) => (
                            <tr key={`placeholder-${i}`} className="placeholder-row">
                              <td className="q-id">Q{i}</td>
                              <td className="q-label">
                                <div className="skeleton-line mini" />
                              </td>
                              <td className="p-mark">
                                <div className="skeleton-line mini dimmed" />
                              </td>
                              <td className="d-val">
                                <div className="skeleton-dot" />
                              </td>
                              <td className="status-cell">
                                <span className="scanning-status">
                                  <RefreshCcw size={12} className="spin" />
                                  EXTRACTING...
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  ) : viewMode === 'reality' && activeDoc.result?.extractedData ? (
                    <div className="reality-inline-view">
                      <RealityView
                        imageUrl={activeDoc.image}
                        questions={activeDoc.result.extractedData.questions}
                        orphans={activeDoc.result.extractedData.survey_data?.orphans}
                        fields={activeDoc.result.extractedData.survey_data?.fields}
                        imageWidth={activeDoc.result.diagnostics?.restoration?.processed_width || activeDoc.result.diagnostics?.vision?.width || 1920}
                        imageHeight={activeDoc.result.diagnostics?.restoration?.processed_height || activeDoc.result.diagnostics?.vision?.height || 1440}
                        hoveredIndex={hoveredIndex}
                        onHover={setHoveredIndex}
                      />
                    </div>
                  ) : viewMode === 'digital' && activeDoc.result?.extractedData ? (
                    <DigitalSurveyForm
                      scanId={activeDoc.id}
                      surveyData={activeDoc.result.extractedData.survey_data}
                      questions={activeDoc.result.extractedData.questions}
                      onApprove={handleApproveSurvey}
                      onFeedback={handleFeedback}
                      isApproving={isExporting}
                      onHoverIndex={setHoveredIndex}
                    />
                  ) : (
                    <div className="empty-state">
                       <p>Select a view mode above.</p>
                    </div>
                  )}
                </div>
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
