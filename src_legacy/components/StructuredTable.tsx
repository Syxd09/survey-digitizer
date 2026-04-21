import React, { useState, useEffect, useRef, useCallback } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, ChevronUp, ChevronDown, Keyboard } from 'lucide-react';
import { SurveyResponse } from '../services/formatterService';

interface StructuredTableProps {
  data: SurveyResponse[];
  onEdit: (qId: string, newValue: string) => void;
}

export const StructuredTable: React.FC<StructuredTableProps> = ({ data, onEdit }) => {
  const [focusedIdx, setFocusedIdx] = useState(-1);
  const [editCount, setEditCount] = useState(0);
  const [reviewStartTime] = useState(Date.now());
  const cardRefs = useRef([] as (HTMLDivElement | null)[]);

  // Find error rows (LOW_CONFIDENCE, NOT_DETECTED, or undetected value)
  const errorIndices = data.reduce((acc: number[], row, i) => {
    if (row.status === 'LOW_CONFIDENCE' || row.status === 'NOT_DETECTED' || row.value === 'undetected') {
      acc.push(i);
    }
    return acc;
  }, []);

  // Auto-focus on first error row on mount
  useEffect(() => {
    if (errorIndices.length > 0 && focusedIdx === -1) {
      const firstError = errorIndices[0];
      setFocusedIdx(firstError);
      setTimeout(() => {
        cardRefs.current[firstError]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 300);
    }
  }, []);

  // Jump to next error
  const jumpToNextError = useCallback(() => {
    const nextErrors = errorIndices.filter(i => i > focusedIdx);
    if (nextErrors.length > 0) {
      setFocusedIdx(nextErrors[0]);
      cardRefs.current[nextErrors[0]]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focusedIdx, errorIndices]);

  // Jump to prev error
  const jumpToPrevError = useCallback(() => {
    const prevErrors = errorIndices.filter(i => i < focusedIdx);
    if (prevErrors.length > 0) {
      const target = prevErrors[prevErrors.length - 1];
      setFocusedIdx(target);
      cardRefs.current[target]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focusedIdx, errorIndices]);

  // Keyboard Speed Mode: keys 1-6 fill the focused row
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (focusedIdx < 0 || focusedIdx >= data.length) return;
      // Ignore if user is typing in an input field
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      const key = e.key;
      if (['1', '2', '3', '4', '5', '6'].includes(key)) {
        e.preventDefault();
        const row = data[focusedIdx];
        onEdit(row.qId, key);
        setEditCount(c => c + 1);
        // Auto-advance to next error
        setTimeout(jumpToNextError, 150);
      }
      if (key === 'ArrowDown' || key === 'Enter') {
        e.preventDefault();
        jumpToNextError();
      }
      if (key === 'ArrowUp') {
        e.preventDefault();
        jumpToPrevError();
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [focusedIdx, data, onEdit, jumpToNextError, jumpToPrevError]);

  const getStatusColor = (row: SurveyResponse) => {
    if (row.value === 'undetected' || row.status === 'NOT_DETECTED') return 'error';
    if (row.status === 'LOW_CONFIDENCE') return 'warning';
    return 'success';
  };

  const getStatusBg = (color: string) => {
    if (color === 'error') return 'bg-red-500/10 border-red-500/30';
    if (color === 'warning') return 'bg-amber-500/10 border-amber-500/30';
    return 'bg-emerald-500/10 border-emerald-500/30';
  };

  const getStatusIcon = (color: string) => {
    if (color === 'error') return <XCircle size={14} className="text-red-500" />;
    if (color === 'warning') return <AlertTriangle size={14} className="text-amber-500" />;
    return <CheckCircle2 size={14} className="text-emerald-500" />;
  };

  const elapsedSecs = Math.round((Date.now() - reviewStartTime) / 1000);

  return (
    <div className="w-full space-y-3">
      {/* Correction Toolbar */}
      <div className="flex items-center justify-between bg-surface-container-high rounded-2xl px-4 py-3 border border-outline-variant/10">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${errorIndices.length > 0 ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'}`} />
            <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">
              {errorIndices.length > 0 ? `${errorIndices.length} need review` : 'All clear'}
            </span>
          </div>
          {errorIndices.length > 0 && (
            <div className="flex items-center gap-1">
              <button onClick={jumpToPrevError} className="p-1 hover:bg-surface-container-highest rounded-lg transition-colors">
                <ChevronUp size={16} className="text-on-surface-variant" />
              </button>
              <button onClick={jumpToNextError} className="p-1 hover:bg-surface-container-highest rounded-lg transition-colors">
                <ChevronDown size={16} className="text-on-surface-variant" />
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-[9px] font-bold text-on-surface-variant uppercase tracking-wider">
            <Keyboard size={12} />
            <span>Keys 1-6 to fill</span>
          </div>
          <span className="text-[9px] font-mono font-bold text-outline">
            {editCount} edits • {elapsedSecs}s
          </span>
        </div>
      </div>

      {/* Data Rows */}
      <div className="bg-surface-container-low rounded-3xl overflow-hidden border border-outline-variant/10 shadow-xl">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-high border-b border-outline-variant/10">
              <th className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-on-surface-variant w-12">#</th>
              <th className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Question</th>
              <th className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-on-surface-variant w-64">Answer</th>
              <th className="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-on-surface-variant w-24">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/5">
            {data.map((row, idx) => {
              const color = getStatusColor(row);
              const isFocused = idx === focusedIdx;
              const isError = row.status === 'LOW_CONFIDENCE' || row.status === 'NOT_DETECTED' || row.value === 'undetected';

              return (
                <tr
                  key={row.qId}
                  ref={el => { cardRefs.current[idx] = el as any; }}
                  onClick={() => setFocusedIdx(idx)}
                  className={`transition-all cursor-pointer ${
                    isFocused
                      ? 'bg-primary/5 ring-2 ring-inset ring-primary/30'
                      : isError
                        ? 'bg-red-500/[0.02] hover:bg-red-500/[0.05]'
                        : 'hover:bg-surface-container-lowest'
                  }`}
                >
                  {/* Q Number */}
                  <td className="px-4 py-4">
                    <span className={`text-sm font-bold ${isFocused ? 'text-primary' : 'text-on-surface-variant'}`}>
                      {row.qId.replace('q', '')}
                    </span>
                  </td>

                  {/* Question Text */}
                  <td className="px-4 py-4">
                    <div className="text-sm font-medium text-on-surface leading-snug">{row.question}</div>
                  </td>

                  {/* Answer: Correction Strip */}
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-1.5">
                      {/* Option buttons 1-6 (or from options if available) */}
                      {(row.options && row.options.length > 0 ? row.options : ['1', '2', '3', '4', '5', '6']).map((opt, i) => {
                        const isSelected = row.value === opt || row.value === String(i + 1);
                        const suggestion1 = row.suggestions?.[0];
                        const suggestion2 = row.suggestions?.[1];
                        const isSuggestion1 = suggestion1 && (suggestion1.value === opt || suggestion1.value === String(i + 1));
                        const isSuggestion2 = suggestion2 && (suggestion2.value === opt || suggestion2.value === String(i + 1));

                        let btnClass = 'bg-surface-container-highest text-on-surface-variant hover:bg-surface-container-high';
                        if (isSelected) {
                          btnClass = 'bg-primary text-on-primary shadow-md shadow-primary/20 scale-105';
                        } else if (isSuggestion1 && !isSelected && isError) {
                          btnClass = 'bg-emerald-500/15 text-emerald-700 border-emerald-500/40 ring-1 ring-emerald-500/30 animate-pulse';
                        } else if (isSuggestion2 && !isSelected && isError) {
                          btnClass = 'bg-amber-500/15 text-amber-700 border-amber-500/40';
                        }

                        return (
                          <button
                            key={i}
                            onClick={(e) => {
                              e.stopPropagation();
                              const val = row.options && row.options.length > 0 ? opt : String(i + 1);
                              onEdit(row.qId, val);
                              setEditCount(c => c + 1);
                              setFocusedIdx(idx);
                            }}
                            className={`min-w-[32px] h-8 px-2 rounded-lg text-xs font-bold transition-all active:scale-95 border border-transparent ${btnClass}`}
                          >
                            {row.options && row.options.length > 0 ? opt : i + 1}
                          </button>
                        );
                      })}
                    </div>
                    {/* Show suggestion scores if error */}
                    {isError && row.suggestions && row.suggestions.length > 0 && (
                      <div className="flex gap-2 mt-1.5">
                        {row.suggestions.map((s, i) => (
                          <span key={i} className={`text-[8px] font-mono font-bold ${i === 0 ? 'text-emerald-600' : 'text-amber-600'}`}>
                            {s.value}: {(s.score * 100).toFixed(1)}%
                          </span>
                        ))}
                      </div>
                    )}
                  </td>

                  {/* Status */}
                  <td className="px-4 py-4">
                    <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[9px] font-black uppercase tracking-wider ${getStatusBg(color)}`}>
                      {getStatusIcon(color)}
                      <span className={`${color === 'error' ? 'text-red-600' : color === 'warning' ? 'text-amber-600' : 'text-emerald-600'}`}>
                        {row.value === 'undetected' ? 'NULL' : row.status === 'LOW_CONFIDENCE' ? 'LOW' : 'OK'}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
