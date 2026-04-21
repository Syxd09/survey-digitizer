import React from 'react';
import { analyticsService } from '../services/analyticsService';
import { BarChart3, Download, Trash2, X, Target, Clock, Zap, AlertTriangle } from 'lucide-react';

export function DiagnosticsDashboard({ onClose }: { onClose: () => void }) {
  const [metrics, setMetrics] = React.useState(analyticsService.calculateMetrics());

  const handleRefresh = () => {
    setMetrics(analyticsService.calculateMetrics());
  };

  const handleClear = () => {
    if (confirm('Clear all diagnostics logs?')) {
      analyticsService.clearLogs();
      handleRefresh();
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-surface/95 backdrop-blur-xl flex flex-col pt-20 pb-10 px-6 overflow-y-auto">
      <div className="max-w-4xl mx-auto w-full space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-4xl font-black tracking-tight text-on-surface">Diagnostics</h2>
            <p className="text-on-surface-variant font-medium">Session-wide performance & reliability</p>
          </div>
          <button onClick={onClose} className="p-3 bg-surface-container-high rounded-full hover:bg-surface-container-highest transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Aggregate Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <MetricCard icon={<Target className="text-primary" />} label="Raw Accuracy" value={`${metrics.avgRawAccuracy.toFixed(1)}%`} />
          <MetricCard icon={<Zap className="text-tertiary" />} label="F1 Score" value={metrics.f1.toFixed(3)} />
          <MetricCard icon={<Clock className="text-primary" />} label="Avg Review" value={`${metrics.avgReviewTime.toFixed(0)}s`} />
          <MetricCard icon={<AlertTriangle className="text-error" />} label="Compliance" value={`${(metrics.complianceRate * 100).toFixed(0)}%`} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Confusion Matrix */}
          <div className="bg-surface-container-low rounded-3xl p-6 border border-outline-variant/10 space-y-4">
            <h3 className="text-sm font-black uppercase tracking-widest text-on-surface-variant">Confusion Matrix</h3>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="p-4 bg-primary/10 rounded-xl">
                <p className="text-[10px] font-bold uppercase text-primary mb-1">TP (Corrected Flags)</p>
                <p className="text-2xl font-black text-primary">{metrics.confusionMatrix.tp}</p>
              </div>
              <div className="p-4 bg-error/10 rounded-xl">
                <p className="text-[10px] font-bold uppercase text-error mb-1">FP (False Alarms)</p>
                <p className="text-2xl font-black text-error">{metrics.confusionMatrix.fp}</p>
              </div>
              <div className="p-4 bg-error/10 rounded-xl">
                <p className="text-[10px] font-bold uppercase text-error mb-1">FN (Missed Errors)</p>
                <p className="text-2xl font-black text-error">{metrics.confusionMatrix.fn}</p>
              </div>
              <div className="p-4 bg-primary/20 rounded-xl">
                <p className="text-[10px] font-bold uppercase text-on-surface-variant mb-1">TN (Silent Success)</p>
                <p className="text-2xl font-black text-on-surface">{metrics.confusionMatrix.tn}</p>
              </div>
            </div>
            <div className="flex justify-between pt-4 text-[11px] font-black uppercase tracking-tighter text-outline">
              <span>Precision: {metrics.precision.toFixed(2)}</span>
              <span>Recall: {metrics.recall.toFixed(2)}</span>
            </div>
          </div>

          {/* Problem Questions */}
          <div className="bg-surface-container-low rounded-3xl p-6 border border-outline-variant/10 space-y-4">
            <h3 className="text-sm font-black uppercase tracking-widest text-on-surface-variant">Problem Indices</h3>
            <div className="space-y-3">
              {metrics.problemQuestions.map((pq, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-lg bg-surface-container-high flex items-center justify-center font-bold text-xs">Q{pq.index + 1}</span>
                    <div className="w-32 h-2 bg-surface-container-highest rounded-full overflow-hidden">
                      <div className="h-full bg-error rounded-full" style={{ width: `${pq.editRate * 100}%` }}></div>
                    </div>
                  </div>
                  <span className="text-xs font-black text-error">{(pq.editRate * 100).toFixed(0)}% Edit Rate</span>
                </div>
              ))}
              {metrics.problemQuestions.length === 0 && <p className="text-xs text-outline italic">No edits recorded yet.</p>}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-4 pt-8">
          <button onClick={() => analyticsService.exportToCSV()} className="flex-1 py-4 bg-primary text-on-primary rounded-2xl font-black flex items-center justify-center gap-3 shadow-lg">
            <Download size={20} /> Export CSV Summary
          </button>
          <button onClick={() => analyticsService.exportToJSON()} className="flex-1 py-4 bg-surface-container-high text-on-surface rounded-2xl font-bold flex items-center justify-center gap-3">
            <BarChart3 size={20} /> Export Detailed JSON
          </button>
          <button onClick={handleClear} className="p-4 text-error bg-error/10 rounded-2xl hover:bg-error/15 transition-colors">
            <Trash2 size={24} />
          </button>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode, label: string, value: string }) {
  return (
    <div className="bg-surface-container-low p-5 rounded-3xl border border-outline-variant/10 space-y-2">
      <div className="flex items-center justify-between">
        <div className="p-2 bg-surface-container-high rounded-xl">{icon}</div>
        <span className="text-[10px] font-black uppercase tracking-widest text-outline">{label}</span>
      </div>
      <p className="text-2xl font-black text-on-surface">{value}</p>
    </div>
  );
}
