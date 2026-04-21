import React, { useState } from 'react';
import { CheckCircle2, Save, RefreshCcw, Check, Info } from 'lucide-react';
import { ExtractionQuestion } from '../services/api';
import './DigitalSurveyForm.css';

interface DigitalSurveyFormProps {
  scanId: string;
  surveyData: {
    form_type: string;
    column_headers: string[];
    raw_text?: string;
  };
  questions: ExtractionQuestion[];
  onApprove: (approvedQuestions: ExtractionQuestion[]) => Promise<void>;
  isApproving?: boolean;
}

export const DigitalSurveyForm: React.FC<DigitalSurveyFormProps> = ({
  scanId,
  surveyData,
  questions: initialQuestions,
  onApprove,
  isApproving = false
}) => {
  const [questions, setQuestions] = useState<ExtractionQuestion[]>(initialQuestions);

  const handleCellClick = (qIndex: number, headerValue: string) => {
    const updated = [...questions];
    updated[qIndex].selected = headerValue;
    setQuestions(updated);
  };

  const handleQuestionTextChange = (qIndex: number, newText: string) => {
    const updated = [...questions];
    updated[qIndex].question = newText;
    setQuestions(updated);
  };

  const headers = (surveyData?.column_headers || []).filter(
    h => !h.toLowerCase().includes('question') && !h.toLowerCase().includes('s.no') && h.trim() !== ''
  );

  return (
    <div className="digital-survey-form">
      <div className="survey-header-bar">
        <div className="survey-meta">
          <span className="form-type-badge">{surveyData.form_type.toUpperCase()}</span>
          <span className="survey-info">
            <Info size={14} />
            Please review the extracted grid. Click cells to correct misread marks.
          </span>
        </div>
      </div>

      <div className="survey-table-container">
        <table className="survey-table">
          <thead>
            <tr>
              <th className="sno-col">#</th>
              <th className="question-col">Question</th>
              {headers.map((h, i) => (
                <th key={i} className="response-col">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {questions.map((q, rIdx) => (
              <tr key={rIdx} className={q.confidence < 0.8 ? 'low-confidence-row' : ''}>
                <td className="sno-col">{rIdx + 1}</td>
                <td className="question-col">
                  <input
                    type="text"
                    value={q.question}
                    onChange={(e) => handleQuestionTextChange(rIdx, e.target.value)}
                    className="question-input"
                  />
                  {q.confidence < 0.8 && (
                    <div className="confidence-warning">Low confidence: {(q.confidence * 100).toFixed(0)}%</div>
                  )}
                </td>
                {headers.map((h, cIdx) => {
                  const isSelected = q.selected === h;
                  return (
                    <td 
                      key={cIdx} 
                      className={`response-col clickable-cell ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleCellClick(rIdx, h)}
                    >
                      <div className="cell-content">
                        {isSelected && <Check size={20} className="check-icon" />}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="survey-actions">
        <button 
          className="approve-btn" 
          onClick={() => onApprove(questions)}
          disabled={isApproving}
        >
          {isApproving ? (
            <RefreshCcw size={18} className="spin" />
          ) : (
            <CheckCircle2 size={18} />
          )}
          <span>APPROVE & SAVE FORM</span>
        </button>
      </div>
    </div>
  );
};
