/**
 * Real-World Evaluation & Data-Driven Optimization Service
 */

export interface EvaluationLog {
  id: string;
  timestamp: string;
  pipelineMode: 'TABLE' | 'OCR';
  processingTime: number; // ms (start to export)
  questionCount: number;
  nullCount: number;
  correctionCount: number; // total edits
  wrongAnswerCount: number; // auto-filled but overridden
  retakeFlag: boolean;
}

export interface AggregateMetrics {
  totalForms: number;
  avgTimePerForm: number; // seconds
  nullRate: number;
  correctionRate: number;
  retakeRate: number;
  wrongAnswerRate: number;
}

export interface PipelineSummary {
  tableMode: AggregateMetrics;
  ocrMode: AggregateMetrics;
  overall: AggregateMetrics;
}

export interface OptimizationSuggestion {
  type: 'WARNING' | 'TIP' | 'CRITICAL';
  message: string;
  action: string;
}

class EvaluationService {
  private STORAGE_KEY = 'survey_evaluation_logs';

  getLogs(): EvaluationLog[] {
    try {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  }

  saveLog(log: EvaluationLog) {
    const logs = this.getLogs();
    logs.push(log);
    // Keep only last 500 logs to prevent localStorage overflow
    if (logs.length > 500) logs.shift();
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(logs));
  }

  clearLogs() {
    localStorage.removeItem(this.STORAGE_KEY);
  }

  private calculateBatch(logs: EvaluationLog[]): AggregateMetrics {
    if (logs.length === 0) {
      return { totalForms: 0, avgTimePerForm: 0, nullRate: 0, correctionRate: 0, retakeRate: 0, wrongAnswerRate: 0 };
    }

    const totalQuestions = logs.reduce((acc, l) => acc + l.questionCount, 0);
    const totalNulls = logs.reduce((acc, l) => acc + l.nullCount, 0);
    const totalCorrections = logs.reduce((acc, l) => acc + l.correctionCount, 0);
    const totalWrongAnswers = logs.reduce((acc, l) => acc + l.wrongAnswerCount, 0);
    const totalRetakes = logs.filter(l => l.retakeFlag).length;
    const totalTime = logs.reduce((acc, l) => acc + l.processingTime, 0);

    return {
      totalForms: logs.length,
      avgTimePerForm: (totalTime / 1000) / logs.length,
      nullRate: totalNulls / totalQuestions,
      correctionRate: totalCorrections / totalQuestions,
      retakeRate: totalRetakes / logs.length,
      wrongAnswerRate: totalWrongAnswers / totalQuestions
    };
  }

  getPipelineSummary(): PipelineSummary {
    const logs = this.getLogs();
    const tableLogs = logs.filter(l => l.pipelineMode === 'TABLE');
    const ocrLogs = logs.filter(l => l.pipelineMode === 'OCR');

    return {
      tableMode: this.calculateBatch(tableLogs),
      ocrMode: this.calculateBatch(ocrLogs),
      overall: this.calculateBatch(logs)
    };
  }

  getOptimizationSuggestions(metrics: AggregateMetrics): OptimizationSuggestion[] {
    const suggestions: OptimizationSuggestion[] = [];

    // Rule 1: Prioritize Zero Wrong Answers
    if (metrics.wrongAnswerRate > 0) {
      suggestions.push({
        type: 'CRITICAL',
        message: 'Increase confidence floor and margin',
        action: 'Required to prevent incorrect auto-filled entries from reaching the review stage.'
      });
    }

    // Rule 2: High Null rate but no wrong answers
    if (metrics.nullRate > 0.25 && metrics.wrongAnswerRate === 0) {
      suggestions.push({
        type: 'TIP',
        message: 'Reduce strictness slightly',
        action: 'Opportunities to reduce manual entry burden as system accuracy is stable.'
      });
    }

    // Rule 3: High Correction rate
    if (metrics.correctionRate > 0.20) {
      suggestions.push({
        type: 'WARNING',
        message: 'Detection inconsistency — review ROI logic',
        action: 'System frequently triggers manual reviews. Check for alignment or ROI cropping shifted.'
      });
    }

    // Rule 4: Retake frequency
    if (metrics.retakeRate > 0.25) {
      suggestions.push({
        type: 'WARNING',
        message: 'High capture failure rate detected',
        action: 'Improve lighting or scanning environment guidance.'
      });
    }

    return suggestions;
  }

  exportToCSV() {
    const logs = this.getLogs();
    if (logs.length === 0) return;

    const headers = ['FormID', 'Timestamp', 'Pipeline', 'ProcessTime_MS', 'Questions', 'Nulls', 'Corrections', 'WrongAnswers', 'Retake'];
    const rows = logs.map(l => [
      l.id, l.timestamp, l.pipelineMode, l.processingTime, l.questionCount, l.nullCount, l.correctionCount, l.wrongAnswerCount, l.retakeFlag
    ].join(','));

    const csvContent = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evaluation_summary_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  }

  exportToJSON() {
    const logs = this.getLogs();
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evaluation_detailed_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
  }
}

export const evaluationService = new EvaluationService();
