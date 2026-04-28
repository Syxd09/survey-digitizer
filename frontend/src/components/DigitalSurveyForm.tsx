import React, { useState } from 'react';
import { Circle, CircleDot, Info } from 'lucide-react';
import { ExtractionQuestion } from '../services/api';
import './DigitalSurveyForm.css';

interface DigitalSurveyFormProps {
  scanId: string;
  surveyData: {
    form_type: string;
    column_headers?: string[];
    columns?: string[];
    raw_text?: string;
    form_metadata?: {
      study_code?: string;
      form_number?: string;
      title?: string;
      raw_header?: string;
    };
  };
  questions: ExtractionQuestion[];
  onApprove: (approvedQuestions: ExtractionQuestion[]) => Promise<void>;
  onFeedback?: (index: number, type: 'question' | 'answer', newValue: string) => void;
  onHoverIndex?: (index: number | null) => void;
  isApproving?: boolean;
}

export const DigitalSurveyForm: React.FC<DigitalSurveyFormProps> = ({
  scanId,
  surveyData,
  questions: initialQuestions,
  onApprove,
  onFeedback,
  onHoverIndex,
  isApproving = false
}) => {
  const [questions, setQuestions] = useState<ExtractionQuestion[]>(initialQuestions);

  const handleCellClick = (qIndex: number, headerValue: string) => {
    const updated = [...questions];
    const target = updated[qIndex];
    const originalAnswer = target.selected || '';
    
    if (originalAnswer === headerValue) return;
    
    target.selected = headerValue;
    setQuestions(updated);
    
    if (onFeedback && target.imageHash) {
      onFeedback(qIndex, 'answer', headerValue);
    }
  };

  const handleQuestionTextChange = (qIndex: number, newText: string) => {
    const updated = [...questions];
    const target = updated[qIndex];
    const originalQuestion = target.question;
    
    if (originalQuestion === newText) return;
    
    target.question = newText;
    setQuestions(updated);
    
    if (onFeedback && target.imageHash) {
      onFeedback(qIndex, 'question', newText);
    }
  };

  // Support both legacy column_headers and new columns array
  const rawHeaders = surveyData?.columns || surveyData?.column_headers || [];
  const headers = rawHeaders
    .filter(h => !h.toLowerCase().includes('question') && !h.toLowerCase().includes('s.no') && h.trim() !== '')
    .map(h => {
      const v = h.trim();
      if (v === '1') return 'Not True';
      if (v === '2') return 'Somewhat True';
      if (v === '3') return 'Certainly True';
      return h;
    });

  const meta = surveyData?.form_metadata || {};

  return (
    <div className="google-form-container">
      
      {/* HEADER CARD */}
      <div className="gf-card gf-header-card">
        <div className="gf-top-accent"></div>
        <div className="gf-header-content">
          {meta.title ? (
            <h1 className="gf-title">{meta.title}</h1>
          ) : (
            <h1 className="gf-title">Survey Form</h1>
          )}
          
          <div className="gf-description">
            {meta.raw_header && !meta.title ? meta.raw_header : (meta.raw_header || "Please review the extracted answers below.")}
          </div>
          
          <div className="gf-meta-tags">
            {meta.study_code && <span className="gf-tag">Study Code: {meta.study_code}</span>}
            {meta.form_number && <span className="gf-tag">Form No: {meta.form_number}</span>}
            <span className="gf-tag badge-primary">{surveyData.form_type.toUpperCase()}</span>
          </div>
        </div>
      </div>

      {/* QUESTIONS GRID CARD */}
      <div className="gf-card gf-questions-card">
        <div className="gf-grid-header">
          <div className="gf-row-header"></div> {/* Empty corner for questions column */}
          {headers.map((h, i) => (
            <div key={i} className="gf-col-header">{h}</div>
          ))}
        </div>
        
        <div className="gf-grid-body">
          {questions.map((q, rIdx) => (
            <div 
              key={rIdx} 
              className={`gf-grid-row ${q.confidence < 0.8 ? 'gf-row-warning' : ''}`}
              onMouseEnter={() => onHoverIndex?.(rIdx)}
              onMouseLeave={() => onHoverIndex?.(null)}
            >
              <div className="gf-row-question">
                <span className="gf-q-num">{rIdx + 1}.</span>
                <div className="gf-q-input-wrapper">
                  <input
                    type="text"
                    value={q.question}
                    onChange={(e) => handleQuestionTextChange(rIdx, e.target.value)}
                    className="gf-q-input"
                  />
                  <div className="gf-input-underline"></div>
                </div>
                {q.confidence < 0.8 && (
                  <div className="gf-confidence-warning">
                    <Info size={12} /> Low confidence: {(q.confidence * 100).toFixed(0)}%
                  </div>
                )}
              </div>
              
              {headers.map((h, cIdx) => {
                const isSelected = q.selected === h;
                return (
                  <div 
                    key={cIdx} 
                    className="gf-grid-cell"
                    onClick={() => handleCellClick(rIdx, h)}
                  >
                    <div className="gf-radio-button">
                      {isSelected ? (
                        <CircleDot size={20} className="gf-radio-icon selected" />
                      ) : (
                        <Circle size={20} className="gf-radio-icon" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* FOOTER ACTIONS */}
      <div className="gf-footer">
        <button 
          className="gf-submit-btn" 
          onClick={() => onApprove(questions)}
          disabled={isApproving}
        >
          {isApproving ? 'Saving...' : 'Submit'}
        </button>
        <span className="gf-footer-text">Never submit passwords through Google Forms.</span>
      </div>
      
    </div>
  );
};
