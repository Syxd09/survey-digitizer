import React from 'react';
import { 
  ArrowLeft, 
  Download, 
  Trash2, 
  AlertTriangle, 
  Lightbulb, 
  Zap, 
  BarChart, 
  Table as TableIcon, 
  Layout, 
  Search,
  Clock,
  CheckCircle2,
  XCircle
} from 'lucide-react';
import { evaluationService, AggregateMetrics, OptimizationSuggestion } from '../services/evaluationService';

interface EvaluationDashboardProps {
  onNavigate: (s: any) => void;
}

export const EvaluationDashboard: React.FC<EvaluationDashboardProps> = ({ onNavigate }) => {
  const summary = evaluationService.getPipelineSummary();
  const suggestions = evaluationService.getOptimizationSuggestions(summary.overall);

  const MetricCard = ({ title, value, unit, icon: Icon, color }: { title: string, value: string | number, unit?: string, icon: any, color: string }) => (
    <div className="bg-surface-container-low rounded-[32px] p-6 border border-outline-variant/10 shadow-sm hover:shadow-md transition-all flex flex-col gap-4">
      <div className={`w-12 h-12 rounded-2xl bg-${color}/10 flex items-center justify-center text-${color}`}>
        <Icon size={24} />
      </div>
      <div>
        <p className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant mb-1">{title}</p>
        <div className="flex items-baseline gap-1">
          <span className="text-3xl font-black text-on-surface">{value}</span>
          <span className="text-sm font-bold text-on-surface-variant">{unit}</span>
        </div>
      </div>
    </div>
  );

  const PipelineRow = ({ title, metrics, icon: Icon }: { title: string, metrics: AggregateMetrics, icon: any }) => (
    <div className="grid grid-cols-6 gap-4 py-4 border-b border-outline-variant/10 items-center">
      <div className="col-span-1 flex items-center gap-2">
        <Icon size={16} className="text-primary" />
        <span className="text-sm font-black text-on-surface uppercase tracking-tight">{title}</span>
      </div>
      <div className="text-sm font-medium text-on-surface text-center">{metrics.totalForms} Forms</div>
      <div className="text-sm font-medium text-on-surface text-center">{metrics.avgTimePerForm.toFixed(1)}s</div>
      <div className={`text-sm font-bold text-center ${metrics.wrongAnswerRate > 0 ? 'text-error' : 'text-emerald-500'}`}>
        {(metrics.wrongAnswerRate * 100).toFixed(1)}%
      </div>
      <div className="text-sm font-medium text-on-surface text-center">{(metrics.nullRate * 100).toFixed(1)}%</div>
      <div className="text-sm font-medium text-on-surface text-center">{(metrics.retakeRate * 100).toFixed(1)}%</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-surface p-6 pb-20">
      <div className="max-w-6xl mx-auto space-y-8 pt-20">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div className="space-y-1">
            <button 
              onClick={() => onNavigate('HOME')}
              className="flex items-center gap-2 text-primary font-black text-[10px] uppercase tracking-widest hover:gap-3 transition-all mb-2"
            >
              <ArrowLeft size={16} /> Dashboard
            </button>
            <h1 className="text-4xl font-black text-on-surface tracking-tight">Real-World Evaluation</h1>
            <p className="text-on-surface-variant font-medium">Performance metrics across {summary.overall.totalForms} sessions.</p>
          </div>
          
          <div className="flex gap-3">
            <button 
              onClick={() => { if(window.confirm('Clear all session data?')) { evaluationService.clearLogs(); onNavigate('HOME'); } }}
              className="p-3 bg-error/10 text-error rounded-2xl hover:bg-error/20 transition-all shadow-sm"
              title="Clear Logs"
            >
              <Trash2 size={20} />
            </button>
            <button 
              onClick={() => evaluationService.exportToJSON()}
              className="p-3 bg-surface-container-high text-on-surface-variant rounded-2xl hover:bg-surface-container-highest transition-all shadow-sm"
              title="Export JSON"
            >
              <Download size={20} />
            </button>
            <button 
              onClick={() => evaluationService.exportToCSV()}
              className="flex items-center gap-2 px-6 py-3 bg-primary text-on-primary rounded-2xl font-black shadow-xl shadow-primary/20 hover:brightness-110 active:scale-95 transition-all"
            >
              <BarChart size={18} /> Export Summary (CSV)
            </button>
          </div>
        </div>

        {/* Global Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard 
            title="Avg Time/Form" 
            value={summary.overall.avgTimePerForm.toFixed(1)} 
            unit="sec" 
            icon={Clock} 
            color="primary" 
          />
          <MetricCard 
            title="Wrong Answer Rate" 
            value={(summary.overall.wrongAnswerRate * 100).toFixed(1)} 
            unit="%" 
            icon={XCircle} 
            color={summary.overall.wrongAnswerRate > 0 ? 'error' : 'emerald'} 
          />
          <MetricCard 
            title="Total Null Rate" 
            value={(summary.overall.nullRate * 100).toFixed(1)} 
            unit="%" 
            icon={Search} 
            color="amber" 
          />
          <MetricCard 
            title="Retake Frequency" 
            value={(summary.overall.retakeRate * 100).toFixed(1)} 
            unit="%" 
            icon={Zap} 
            color="indigo" 
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Pipeline Analysis */}
          <div className="lg:col-span-2 bg-surface-container-low rounded-[40px] p-8 border border-outline-variant/10 shadow-lg">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
                <Layout size={20} />
              </div>
              <h3 className="text-xl font-black text-on-surface">Pipeline Performance</h3>
            </div>
            
            <div className="space-y-2">
              <div className="grid grid-cols-6 gap-4 pb-4 border-b border-outline-variant/20 text-[10px] font-black uppercase tracking-widest text-on-surface-variant text-center">
                <div className="text-left">Pipeline</div>
                <div>Volume</div>
                <div>Avg Time</div>
                <div>Error Rate</div>
                <div>Null Rate</div>
                <div>Retake</div>
              </div>
              
              <PipelineRow title="Table Pipeline" metrics={summary.tableMode} icon={TableIcon} />
              <PipelineRow title="OCR Pipeline" metrics={summary.ocrMode} icon={Search} />
            </div>
          </div>

          <div className="bg-surface-container-low rounded-[40px] p-8 border border-outline-variant/10 shadow-lg flex flex-col">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-600">
                <Lightbulb size={20} />
              </div>
              <h3 className="text-xl font-black text-on-surface">Optimization Engine</h3>
            </div>

            <div className="flex-1 space-y-8 overflow-y-auto max-h-[60vh] pr-2 custom-scrollbar">
              {/* Table Pipeline Suggestions */}
              {summary.tableMode.totalForms > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <TableIcon size={14} className="text-on-surface-variant" />
                    <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Table Pipeline</span>
                  </div>
                  {evaluationService.getOptimizationSuggestions(summary.tableMode).length === 0 ? (
                    <p className="text-[10px] text-emerald-500 font-bold px-4 italic">No issues detected.</p>
                  ) : (
                    evaluationService.getOptimizationSuggestions(summary.tableMode).map((s, i) => (
                      <div key={`table-${i}`} className={`p-4 rounded-2xl border flex items-start gap-4 ${
                        s.type === 'CRITICAL' ? 'bg-error/5 border-error/20' : 
                        s.type === 'WARNING' ? 'bg-amber-500/5 border-amber-500/20' : 'bg-primary/5 border-primary/20'
                      }`}>
                        {s.type === 'CRITICAL' ? <XCircle className="text-error shrink-0 mt-0.5" size={18} /> :
                         s.type === 'WARNING' ? <AlertTriangle className="text-amber-500 shrink-0 mt-0.5" size={18} /> :
                         <Lightbulb className="text-primary shrink-0 mt-0.5" size={18} />}
                        <div>
                          <p className={`text-xs font-black mb-1 ${
                            s.type === 'CRITICAL' ? 'text-error' : 
                            s.type === 'WARNING' ? 'text-amber-600' : 'text-primary'
                          }`}>{s.message}</p>
                          <p className="text-[10px] text-on-surface-variant font-medium leading-relaxed">{s.action}</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* OCR Pipeline Suggestions */}
              {summary.ocrMode.totalForms > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Search size={14} className="text-on-surface-variant" />
                    <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">OCR Pipeline</span>
                  </div>
                  {evaluationService.getOptimizationSuggestions(summary.ocrMode).length === 0 ? (
                    <p className="text-[10px] text-emerald-500 font-bold px-4 italic">No issues detected.</p>
                  ) : (
                    evaluationService.getOptimizationSuggestions(summary.ocrMode).map((s, i) => (
                      <div key={`ocr-${i}`} className={`p-4 rounded-2xl border flex items-start gap-4 ${
                        s.type === 'CRITICAL' ? 'bg-error/5 border-error/20' : 
                        s.type === 'WARNING' ? 'bg-amber-500/5 border-amber-500/20' : 'bg-primary/5 border-primary/20'
                      }`}>
                        {s.type === 'CRITICAL' ? <XCircle className="text-error shrink-0 mt-0.5" size={18} /> :
                         s.type === 'WARNING' ? <AlertTriangle className="text-amber-500 shrink-0 mt-0.5" size={18} /> :
                         <Lightbulb className="text-primary shrink-0 mt-0.5" size={18} />}
                        <div>
                          <p className={`text-xs font-black mb-1 ${
                            s.type === 'CRITICAL' ? 'text-error' : 
                            s.type === 'WARNING' ? 'text-amber-600' : 'text-primary'
                          }`}>{s.message}</p>
                          <p className="text-[10px] text-on-surface-variant font-medium leading-relaxed">{s.action}</p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {summary.overall.totalForms === 0 && (
                <div className="bg-surface-container-high rounded-2xl p-6 text-center">
                  <p className="text-sm font-bold text-on-surface-variant italic">Waiting for session data...</p>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};
