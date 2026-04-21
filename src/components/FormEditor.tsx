import React, { useState, useEffect, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Eye, EyeOff, Check } from 'lucide-react';

export interface FormQuestion {
  id: string;
  question: string;
  options: string[];
  selected: string | null;
  suggestions?: { value: string; score: number }[];
  status?: 'OK' | 'LOW_CONFIDENCE' | 'NOT_DETECTED' | 'AUTO_LOW_CONFIDENCE';
  confidence?: number;
}

interface FormEditorProps {
  questions: FormQuestion[];
  onChange: (questions: FormQuestion[]) => void;
  pipelineMode?: 'TABLE' | 'OCR';
}

// --- Adaptive Calibration Engine ---
// Tracks a rolling window of corrections to dynamically adjust auto-select thresholds.

const CALIBRATION_KEY = 'autoselect_calibration';
const ROLLING_WINDOW = 100;

// Default thresholds
const DEFAULT_CONFIDENCE_FLOOR = 0.60;
const DEFAULT_MARGIN = 0.20;
const SOFT_CONFIDENCE_FLOOR = 0.50;
const SOFT_MARGIN = 0.15;

interface CalibrationEntry {
  autoSelected: boolean;
  wasCorrected: boolean;
  timestamp: number;
}

class AdaptiveCalibrator {
  private entries: CalibrationEntry[] = [];
  private storageKey: string;
  confidenceFloor: number = DEFAULT_CONFIDENCE_FLOOR;
  margin: number = DEFAULT_MARGIN;

  constructor(mode: 'table' | 'ocr') {
    this.storageKey = `autoselect_calibration_${mode}`;
    this.load();
    this.recalculate();
  }

  private load() {
    try {
      const raw = localStorage.getItem(this.storageKey);
      if (raw) this.entries = JSON.parse(raw);
    } catch {}
  }

  private save() {
    try {
      // Keep only last ROLLING_WINDOW entries
      this.entries = this.entries.slice(-ROLLING_WINDOW);
      localStorage.setItem(this.storageKey, JSON.stringify(this.entries));
    } catch {}
  }

  /** Record that a question was auto-selected */
  recordAutoSelect() {
    this.entries.push({ autoSelected: true, wasCorrected: false, timestamp: Date.now() });
    this.save();
  }

  /** Record that user changed an auto-selected answer (i.e., it was wrong) */
  recordCorrection() {
    // Mark the most recent uncorrected auto-select as corrected
    for (let i = this.entries.length - 1; i >= 0; i--) {
      if (this.entries[i].autoSelected && !this.entries[i].wasCorrected) {
        this.entries[i].wasCorrected = true;
        break;
      }
    }
    this.save();
    this.recalculate();
  }

  private recalculate() {
    const autoEntries = this.entries.filter(e => e.autoSelected);
    if (autoEntries.length < 10) {
      // Not enough data — use defaults
      this.confidenceFloor = DEFAULT_CONFIDENCE_FLOOR;
      this.margin = DEFAULT_MARGIN;
      return;
    }

    const corrected = autoEntries.filter(e => e.wasCorrected).length;
    const errorRate = corrected / autoEntries.length;

    // High error rate → tighten thresholds
    if (errorRate > 0.15) {
      this.confidenceFloor = Math.min(0.85, DEFAULT_CONFIDENCE_FLOOR + 0.10);
      this.margin = Math.min(0.35, DEFAULT_MARGIN + 0.05);
    } 
    // Low error rate → slightly relax
    else if (errorRate < 0.05) {
      this.confidenceFloor = Math.max(0.45, DEFAULT_CONFIDENCE_FLOOR - 0.05);
      this.margin = Math.max(0.12, DEFAULT_MARGIN - 0.03);
    } 
    // Normal → defaults
    else {
      this.confidenceFloor = DEFAULT_CONFIDENCE_FLOOR;
      this.margin = DEFAULT_MARGIN;
    }
  }

  getErrorRate(): number {
    const autoEntries = this.entries.filter(e => e.autoSelected);
    if (autoEntries.length === 0) return 0;
    return autoEntries.filter(e => e.wasCorrected).length / autoEntries.length;
  }
}

// --- Form-Level Metrics ---
export interface FormMetrics {
  form_status: 'GOOD' | 'PARTIAL' | 'BAD';
  confidence: number;
  null_rate: number;
  auto_fill_count: number;
  soft_fill_count: number;
}

export function computeFormMetrics(questions: FormQuestion[]): FormMetrics {
  if (questions.length === 0) return { form_status: 'BAD', confidence: 0, null_rate: 1, auto_fill_count: 0, soft_fill_count: 0 };

  const nullCount = questions.filter(q => !q.selected).length;
  const null_rate = nullCount / questions.length;

  const avgConfidence = questions.reduce((acc, q) => {
    if (!q.suggestions || q.suggestions.length === 0) return acc;
    return acc + q.suggestions[0].score;
  }, 0) / questions.length;

  const auto_fill_count = questions.filter(q => q.status === 'OK' && q.selected).length;
  const soft_fill_count = questions.filter(q => q.status === 'AUTO_LOW_CONFIDENCE').length;

  let form_status: 'GOOD' | 'PARTIAL' | 'BAD' = 'GOOD';
  if (null_rate > 0.5 || avgConfidence < 0.3) form_status = 'BAD';
  else if (null_rate > 0.2 || avgConfidence < 0.5) form_status = 'PARTIAL';

  return { form_status, confidence: Math.round(avgConfidence * 100) / 100, null_rate: Math.round(null_rate * 100) / 100, auto_fill_count, soft_fill_count };
}

// --- Error Pattern Learning ---
// Tracks which question indices are frequently corrected by the user.
// If a position is corrected repeatedly, the system stops auto-filling it.

const PATTERN_KEY = 'error_pattern_tracker';
const CORRECTION_THRESHOLD = 3; // after this many corrections, demote auto-confidence

class ErrorPatternTracker {
  private corrections: Record<string, number> = {};
  private streaks: Record<string, number> = {}; // Tracks sessions without correction

  constructor() {
    try {
      const rawC = localStorage.getItem(PATTERN_KEY);
      if (rawC) this.corrections = JSON.parse(rawC);
      const rawS = localStorage.getItem(PATTERN_KEY + '_streaks');
      if (rawS) this.streaks = JSON.parse(rawS);
    } catch {}
  }

  private save() {
    try { 
      localStorage.setItem(PATTERN_KEY, JSON.stringify(this.corrections)); 
      localStorage.setItem(PATTERN_KEY + '_streaks', JSON.stringify(this.streaks));
    } catch {}
  }

  /** Record a correction at a given question index */
  recordCorrection(questionIndex: number) {
    const key = `idx_${questionIndex}`;
    this.corrections[key] = (this.corrections[key] || 0) + 1;
    this.streaks[key] = 0; // Reset success streak
    this.save();
  }

  /** Record a session where this index was fine (not corrected) */
  recordSuccess(questionIndex: number) {
    const key = `idx_${questionIndex}`;
    this.streaks[key] = (this.streaks[key] || 0) + 1;
    
    // Learning Decay: If 5 sessions without correction, reset the block
    if (this.streaks[key] >= 5) {
      this.corrections[key] = 0;
      this.streaks[key] = 0;
    }
    this.save();
  }

  /** Check if a question index has been frequently corrected */
  isProblematic(questionIndex: number): boolean {
    return (this.corrections[`idx_${questionIndex}`] || 0) >= CORRECTION_THRESHOLD;
  }

  /** Get correction count for a question index */
  getCount(questionIndex: number): number {
    return this.corrections[`idx_${questionIndex}`] || 0;
  }
}

// --- Singletons ---
const tableCalibrator = new AdaptiveCalibrator('table');
const ocrCalibrator = new AdaptiveCalibrator('ocr');
const patternTracker = new ErrorPatternTracker();

export const FormEditor: React.FC<FormEditorProps> = ({ questions, onChange, pipelineMode }) => {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [wrongAnswerCount, setWrongAnswerCount] = useState(0);
  const [editCount, setEditCount] = useState(0);
  const [startTime] = useState(Date.now());
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);

  const calibrator = pipelineMode === 'OCR' ? ocrCalibrator : tableCalibrator;

  // Auto-select best answers on mount (adaptive + soft mode)
  useEffect(() => {
    const floor = calibrator.confidenceFloor;
    const margin = calibrator.margin;

    const updated = questions.map((q, qIdx) => {
      // Record session success for decay logic if this index isn't corrected later
      // We assume it's successful initially; corrections happen in selectAnswer
      patternTracker.recordSuccess(qIdx);

      if (q.selected || !q.suggestions || q.suggestions.length < 2) return q;

      // Error Pattern Gate: if this position is frequently corrected, skip auto-fill
      if (patternTracker.isProblematic(qIdx)) {
        return { ...q, status: 'LOW_CONFIDENCE' as const };
      }

      const scores = q.suggestions.map(s => s.score);
      const min = Math.min(...scores);
      const max = Math.max(...scores);
      if (max === min) return q;

      const normTop1 = (q.suggestions[0].score - min) / (max - min);
      const normTop2 = (q.suggestions[1].score - min) / (max - min);
      const gap = normTop1 - normTop2;

      // Tier 1: HIGH confidence auto-fill (adaptive thresholds)
      if (normTop1 >= floor && gap >= margin) {
        calibrator.recordAutoSelect();
        return { ...q, selected: q.suggestions[0].value, status: 'OK' as const };
      }

      // Tier 2: SOFT auto-fill (moderate confidence, still useful)
      if (normTop1 >= SOFT_CONFIDENCE_FLOOR && gap >= SOFT_MARGIN) {
        calibrator.recordAutoSelect();
        return { ...q, selected: q.suggestions[0].value, status: 'AUTO_LOW_CONFIDENCE' as const };
      }

      // Below both tiers → leave null, show suggestions
      return { ...q, confidence: normTop1 };
    });

    if (updated.some((q, i) => q.selected !== questions[i].selected)) {
      onChange(updated);
    }
  }, []);

  // Live timer
  useEffect(() => {
    const t = setInterval(() => setElapsed(Math.round((Date.now() - startTime) / 1000)), 1000);
    return () => clearInterval(t);
  }, [startTime]);

  // Auto-save on every change
  useEffect(() => {
    try {
      localStorage.setItem('form_autosave', JSON.stringify(questions));
    } catch {}
  }, [questions]);

  // Build the visible question list (include AUTO_LOW_CONFIDENCE as reviewable)
  const visibleQuestions = errorsOnly
    ? questions.filter(q => !q.selected || q.status === 'LOW_CONFIDENCE' || q.status === 'NOT_DETECTED' || q.status === 'AUTO_LOW_CONFIDENCE')
    : questions;

  const errorCount = questions.filter(q => !q.selected || q.status === 'LOW_CONFIDENCE' || q.status === 'NOT_DETECTED' || q.status === 'AUTO_LOW_CONFIDENCE').length;

  // Clamp currentIdx
  const safeIdx = Math.min(currentIdx, Math.max(0, visibleQuestions.length - 1));
  const currentQ = visibleQuestions[safeIdx];
  const realIdx = currentQ ? questions.findIndex(q => q.id === currentQ.id) : -1;

  // Select an answer (feeds correction data back to calibrator)
  const selectAnswer = useCallback((value: string) => {
    if (realIdx < 0) return;
    const prev = questions[realIdx];

    // Track if user is overriding an auto-selected value
    const wasAutoSelected = prev.status === 'OK' || prev.status === 'AUTO_LOW_CONFIDENCE';
    const isCorrection = wasAutoSelected && prev.selected !== null && prev.selected !== value;
    if (isCorrection) {
      calibrator.recordCorrection();
      patternTracker.recordCorrection(realIdx);
      setWrongAnswerCount(prev => prev + 1);
    }

    const updated = [...questions];
    updated[realIdx] = { ...updated[realIdx], selected: value, status: 'OK' };
    onChange(updated);
    setEditCount(c => c + 1);

    // Auto-advance to next error
    setTimeout(() => {
      if (errorsOnly) {
        const remaining = updated.filter(q => !q.selected || q.status === 'LOW_CONFIDENCE' || q.status === 'NOT_DETECTED' || q.status === 'AUTO_LOW_CONFIDENCE');
        if (remaining.length === 0) setDone(true);
      } else {
        const nextError = questions.findIndex((q, i) => i > realIdx && (!q.selected || q.status !== 'OK'));
        if (nextError >= 0) {
          const nextVisIdx = visibleQuestions.findIndex(q => q.id === questions[nextError].id);
          if (nextVisIdx >= 0) setCurrentIdx(nextVisIdx);
        } else {
          const allDone = updated.every(q => q.selected && q.status === 'OK');
          if (allDone) setDone(true);
          else setCurrentIdx(Math.min(safeIdx + 1, visibleQuestions.length - 1));
        }
      }
    }, 100);
  }, [realIdx, questions, onChange, errorsOnly, visibleQuestions, safeIdx]);

  // Keyboard: number keys + arrows
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (!currentQ) return;

      if (['1', '2', '3', '4', '5', '6', '7', '8', '9'].includes(e.key)) {
        e.preventDefault();
        const optIdx = parseInt(e.key) - 1;
        if (currentQ.options[optIdx]) selectAnswer(currentQ.options[optIdx]);
      }
      if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault();
        setCurrentIdx(Math.min(safeIdx + 1, visibleQuestions.length - 1));
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setCurrentIdx(Math.max(safeIdx - 1, 0));
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [currentQ, safeIdx, visibleQuestions, selectAnswer]);

  // --- DONE STATE ---
  if (done || visibleQuestions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <div className="w-20 h-20 rounded-full bg-emerald-500/10 flex items-center justify-center">
          <Check size={40} className="text-emerald-500" />
        </div>
        <h3 className="text-2xl font-black text-on-surface">All Done!</h3>
        <p className="text-on-surface-variant text-sm font-medium">
          {editCount} corrections in {elapsed}s
        </p>
        {errorsOnly && errorCount === 0 && (
          <button
            onClick={() => { setErrorsOnly(false); setDone(false); setCurrentIdx(0); }}
            className="mt-2 px-6 py-2 bg-surface-container-high text-on-surface-variant rounded-xl text-sm font-bold hover:bg-surface-container-highest transition-all"
          >
            Review All Questions
          </button>
        )}
      </div>
    );
  }

  // --- SINGLE CARD VIEW ---
  return (
    <div className="space-y-4">
      {/* Compact Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">
            {safeIdx + 1} / {visibleQuestions.length}
          </span>
          {errorCount > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-500/10">
              <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span className="text-[9px] font-black text-amber-600">{errorCount} left</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setErrorsOnly(!errorsOnly); setCurrentIdx(0); setDone(false); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-bold transition-all ${
              errorsOnly ? 'bg-primary text-on-primary' : 'bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest'
            }`}
          >
            {errorsOnly ? <EyeOff size={12} /> : <Eye size={12} />}
            {errorsOnly ? 'Errors Only' : 'Show All'}
          </button>
          <span className="text-[9px] font-mono text-outline">{editCount} edits • {elapsed}s</span>
        </div>
      </div>

      {/* Question Card — Single Focus */}
      <div className="bg-surface-container-low rounded-3xl border border-outline-variant/10 shadow-xl overflow-hidden">
        {/* Question Header */}
        <div className="px-6 pt-6 pb-3">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-black text-primary">Q{questions.indexOf(currentQ) + 1}</span>
            {currentQ.status === 'OK' && currentQ.selected ? (
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 text-[8px] font-black uppercase">
                <Check size={10} /> Done
              </div>
            ) : (
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 text-[8px] font-black uppercase animate-pulse">
                Needs answer
              </div>
            )}
            
            {/* Confidence Heatmark */}
            {currentQ.confidence !== undefined && (
              <div className="flex items-center gap-2 ml-auto">
                <span className="text-[9px] font-black uppercase text-on-surface-variant">Trust Level:</span>
                <div className="h-1.5 w-16 bg-surface-container-highest rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-1000 ${
                      currentQ.confidence > 0.8 ? 'bg-emerald-500' : 
                      currentQ.confidence > 0.5 ? 'bg-amber-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${currentQ.confidence * 100}%` }}
                  />
                </div>
                <span className={`text-[10px] font-mono font-bold ${
                   currentQ.confidence > 0.8 ? 'text-emerald-500' : 
                   currentQ.confidence > 0.5 ? 'text-amber-500' : 'text-red-500'
                }`}>
                  {Math.round(currentQ.confidence * 100)}%
                </span>
              </div>
            )}
          </div>
          <p className="text-base font-semibold text-on-surface leading-relaxed">
            {currentQ.question || <span className="text-outline italic">No question text</span>}
          </p>
        </div>

        {/* Options — Large Tap Targets */}
        <div className="px-4 pb-6 space-y-2">
          {currentQ.options.map((opt, i) => {
            const isSelected = currentQ.selected === opt;
            const isSuggestion1 = !currentQ.selected && currentQ.suggestions?.[0]?.value === opt;

            return (
              <button
                key={i}
                onClick={() => selectAnswer(opt)}
                className={`w-full flex items-center gap-4 px-5 py-4 rounded-2xl text-left transition-all active:scale-[0.98] ${
                  isSelected
                    ? 'bg-primary text-on-primary shadow-lg shadow-primary/20'
                    : isSuggestion1
                      ? 'bg-emerald-500/10 border-2 border-emerald-500/30 text-on-surface hover:bg-emerald-500/20'
                      : 'bg-surface-container-highest text-on-surface hover:bg-surface-container-high border-2 border-transparent'
                }`}
              >
                {/* Option Number */}
                <span className={`w-8 h-8 rounded-xl flex items-center justify-center text-sm font-black flex-shrink-0 ${
                  isSelected ? 'bg-on-primary/20 text-on-primary' : 'bg-surface-container-low text-on-surface-variant'
                }`}>
                  {i + 1}
                </span>

                {/* Option Text */}
                <span className="font-bold text-sm flex-1">{opt}</span>

                {/* Selection Indicator */}
                {isSelected && (
                  <div className="w-6 h-6 rounded-full bg-on-primary/20 flex items-center justify-center flex-shrink-0">
                    <Check size={14} />
                  </div>
                )}
                {isSuggestion1 && !isSelected && (
                  <span className="text-[8px] font-black text-emerald-600 uppercase tracking-wider flex-shrink-0">
                    suggested
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Navigation — Prev / Next */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrentIdx(Math.max(safeIdx - 1, 0))}
          disabled={safeIdx === 0}
          className="flex items-center gap-2 px-5 py-3 rounded-2xl bg-surface-container-high text-on-surface-variant font-bold text-sm hover:bg-surface-container-highest transition-all active:scale-95 disabled:opacity-30"
        >
          <ChevronLeft size={18} /> Prev
        </button>

        {/* Progress Dots */}
        <div className="flex gap-1 max-w-[200px] overflow-hidden">
          {visibleQuestions.map((q, i) => (
            <button
              key={q.id}
              onClick={() => setCurrentIdx(i)}
              className={`h-2 rounded-full transition-all ${
                i === safeIdx
                  ? 'w-6 bg-primary'
                  : q.selected && q.status === 'OK'
                    ? 'w-2 bg-emerald-500'
                    : 'w-2 bg-amber-500/50'
              }`}
            />
          ))}
        </div>

        <button
          onClick={() => setCurrentIdx(Math.min(safeIdx + 1, visibleQuestions.length - 1))}
          disabled={safeIdx >= visibleQuestions.length - 1}
          className="flex items-center gap-2 px-5 py-3 rounded-2xl bg-primary text-on-primary font-bold text-sm hover:brightness-110 transition-all active:scale-95 disabled:opacity-30 shadow-md shadow-primary/20"
        >
          Next <ChevronRight size={18} />
        </button>
      </div>
      <div className="hidden" id="evaluation-data" data-wrong-answers={wrongAnswerCount} data-edit-count={editCount} />
    </div>
  );
};

// --- Export Utilities ---

export function exportFormAsJSON(questions: FormQuestion[], filename = 'form_export.json') {
  const data = {
    exportedAt: new Date().toISOString(),
    totalQuestions: questions.length,
    questions: questions.map((q, i) => ({
      number: i + 1,
      question: q.question,
      options: q.options,
      selected: q.selected
    }))
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  triggerDownload(blob, filename);
}

export function exportFormAsCSV(questions: FormQuestion[], filename = 'form_export.csv') {
  const headers = ['Q.No', 'Question', 'Options', 'Selected Answer'];
  const rows = questions.map((q, i) => [
    i + 1,
    `"${q.question.replace(/"/g, '""')}"`,
    `"${q.options.join(', ')}"`,
    q.selected || ''
  ]);
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  triggerDownload(blob, filename);
}

export function saveFormLocally(questions: FormQuestion[]) {
  const key = `form_draft_${Date.now()}`;
  localStorage.setItem(key, JSON.stringify(questions));
  localStorage.setItem('form_draft_latest', key);
  return key;
}

export function loadLatestDraft(): FormQuestion[] | null {
  const latestKey = localStorage.getItem('form_draft_latest');
  if (!latestKey) return null;
  const data = localStorage.getItem(latestKey);
  return data ? JSON.parse(data) : null;
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
