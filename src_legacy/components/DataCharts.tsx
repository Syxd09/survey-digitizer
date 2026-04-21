import React from 'react';

interface DistributionData {
  label: string;
  count: number;
}

export function DistributionChart({ data, title }: { data: DistributionData[], title: string }) {
  const max = Math.max(...data.map(d => d.count), 1);
  
  return (
    <div className="bg-surface-container-low p-6 rounded-3xl border border-outline-variant/10 space-y-4 shadow-sm">
      <h3 className="text-xs font-black uppercase tracking-widest text-on-surface-variant px-1">{title}</h3>
      <div className="space-y-3">
        {data.map((item, i) => (
          <div key={i} className="space-y-1">
            <div className="flex justify-between items-center text-[10px] font-bold text-on-surface tracking-tight">
              <span>{item.label}</span>
              <span className="text-primary">{item.count}</span>
            </div>
            <div className="h-3 bg-surface-container-highest rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
                style={{ width: `${(item.count / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MiniSparkline({ data }: { data: number[] }) {
  const max = Math.max(...data, 1);
  const width = 100;
  const height = 30;
  
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - (d / max) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width="40" height="15" viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="10"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        className="text-primary"
      />
    </svg>
  );
}
