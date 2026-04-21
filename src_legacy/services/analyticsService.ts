/**
 * Field Evaluation & Statistical Diagnostics Service
 * Purely local, no external tracking.
 */

export interface FormLog {
  formId: string;
  rawValues: string[];
  finalValues: string[];
  confidenceScores: number[];
  processingTime: number;
  reviewTime: number;
  editCount: number;
  editsPerQuestion: number;
  state: 'GOOD' | 'PARTIAL' | 'BAD';
  retakeSuggested: boolean;
  retakePerformed: boolean;
  brightness: number;
  contrast: number;
  tilt: number;
  timestamp: string;
}

export interface SessionMetrics {
  totalForms: number;
  avgRawAccuracy: number;
  avgReviewTime: number;
  avgEditCount: number;
  complianceRate: number;
  confusionMatrix: {
    tp: number;
    fp: number;
    fn: number;
    tn: number;
  };
  precision: number;
  recall: number;
  f1: number;
  problemQuestions: { index: number; editRate: number }[];
}

class AnalyticsService {
  private STORAGE_KEY = 'survey_diagnostics_logs';

  getLogs(): FormLog[] {
    const saved = localStorage.getItem(this.STORAGE_KEY);
    return saved ? JSON.parse(saved) : [];
  }

  saveLog(log: FormLog) {
    const logs = this.getLogs();
    logs.push(log);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(logs));
  }

  clearLogs() {
    localStorage.removeItem(this.STORAGE_KEY);
  }

  calculateMetrics(): SessionMetrics {
    const logs = this.getLogs();
    if (logs.length === 0) {
      return {
        totalForms: 0, avgRawAccuracy: 0, avgReviewTime: 0, avgEditCount: 0,
        complianceRate: 0, confusionMatrix: { tp: 0, fp: 0, fn: 0, tn: 0 },
        precision: 0, recall: 0, f1: 0, problemQuestions: []
      };
    }

    let totalRawAccuracy = 0;
    let totalReviewTime = 0;
    let totalEditCount = 0;
    let suggestedCount = 0;
    let performedCount = 0;
    const cm = { tp: 0, fp: 0, fn: 0, tn: 0 };
    const questionEdits = new Map<number, number>();
    const questionAppearances = new Map<number, number>();

    logs.forEach(log => {
      // Raw Accuracy
      let matchCount = 0;
      log.rawValues.forEach((v, i) => {
        const isCorrect = v === log.finalValues[i];
        if (isCorrect) matchCount++;

        // Confusion Matrix (Threshold 80%)
        const isLowConf = log.confidenceScores[i] < 80;
        const isEdited = !isCorrect;

        if (isLowConf && isEdited) cm.tp++;
        else if (isLowConf && !isEdited) cm.fp++;
        else if (!isLowConf && isEdited) cm.fn++;
        else cm.tn++;

        // Heatmap
        questionAppearances.set(i, (questionAppearances.get(i) || 0) + 1);
        if (isEdited) questionEdits.set(i, (questionEdits.get(i) || 0) + 1);
      });

      totalRawAccuracy += (matchCount / log.rawValues.length) * 100;
      totalReviewTime += log.reviewTime;
      totalEditCount += log.editCount;
      if (log.retakeSuggested) suggestedCount++;
      if (log.retakePerformed) performedCount++;
    });

    const precision = cm.tp / (cm.tp + cm.fp) || 0;
    const recall = cm.tp / (cm.tp + cm.fn) || 0;
    const f1 = 2 * (precision * recall) / (precision + recall) || 0;

    const problemQuestions = Array.from(questionAppearances.keys())
      .map(index => ({
        index,
        editRate: (questionEdits.get(index) || 0) / questionAppearances.get(index)!
      }))
      .sort((a, b) => b.editRate - a.editRate)
      .slice(0, 5);

    return {
      totalForms: logs.length,
      avgRawAccuracy: totalRawAccuracy / logs.length,
      avgReviewTime: totalReviewTime / logs.length,
      avgEditCount: totalEditCount / logs.length,
      complianceRate: suggestedCount > 0 ? performedCount / suggestedCount : 1,
      confusionMatrix: cm,
      precision,
      recall,
      f1,
      problemQuestions
    };
  }

  exportToCSV() {
    const logs = this.getLogs();
    if (logs.length === 0) return;

    const headers = ['FormID', 'Timestamp', 'RawAccuracy', 'EditCount', 'ProcessingTime', 'ReviewTime', 'State', 'RetakeSuggested', 'RetakePerformed'];
    const rows = logs.map(log => {
      let matchCount = 0;
      log.rawValues.forEach((v, i) => { if (v === log.finalValues[i]) matchCount++; });
      const rawAcc = (matchCount / log.rawValues.length) * 100;

      return [
        log.formId,
        log.timestamp,
        rawAcc.toFixed(2),
        log.editCount,
        log.processingTime.toFixed(0),
        log.reviewTime.toFixed(0),
        log.state,
        log.retakeSuggested,
        log.retakePerformed
      ].join(',');
    });

    const csvContent = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `survey_diagnostics_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
  }

  exportToJSON() {
    const logs = this.getLogs();
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `survey_diagnostics_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
  }
}

export const analyticsService = new AnalyticsService();
