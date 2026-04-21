import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Check, Cpu, Layers, Maximize, Zap } from 'lucide-react';

interface DigitizingOverlayProps {
  image: string;
  onComplete: () => void;
}

export default function DigitizingOverlay({ image, onComplete }: DigitizingOverlayProps) {
  const [phase, setPhase] = useState(0);
  const phases = [
    { name: 'Correcting Perspective', icon: <Maximize size={32} />, duration: 800 },
    { name: 'Contrast Enhancement', icon: <Zap size={32} />, duration: 600 },
    { name: 'Neural Segmentation', icon: <Layers size={32} />, duration: 1000 },
    { name: 'Extracting Data Fields', icon: <Cpu size={32} />, duration: 1200 },
  ];

  useEffect(() => {
    let current = 0;
    const runPhases = async () => {
      for (let i = 0; i < phases.length; i++) {
        setPhase(i);
        await new Promise(r => setTimeout(r, phases[i].duration));
      }
      setTimeout(onComplete, 500);
    };
    runPhases();
  }, []);

  return (
    <div className="fixed inset-0 z-[200] bg-black/95 backdrop-blur-3xl flex flex-col items-center justify-center overflow-hidden">
      {/* Background Image with stylized effects for each phase */}
      <div className="absolute inset-0 opacity-10 overflow-hidden flex items-center justify-center">
        <motion.img 
            src={image} 
            initial={{ scale: 1.2, rotate: 5 }}
            animate={{ 
              scale: phase === 0 ? 1.1 : 1, 
              rotate: phase === 0 ? 0 : 0,
              filter: `
                grayscale(${phase >= 1 ? 0.5 : 0}) 
                contrast(${phase >= 1 ? 2 : 1}) 
                brightness(${phase >= 1 ? 1.2 : 1})
                blur(${phase === 2 ? 1 : 0}px)
              `
            }}
            transition={{ duration: 0.8 }}
            className="w-full h-full object-contain" 
            alt="Survey Preview" 
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-black" />
      </div>

      {/* Central Progress Orbit */}
      <div className="relative w-72 h-72 flex items-center justify-center">
        <motion.div 
          animate={{ rotate: 360 }}
          transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
          className="absolute inset-0 border-2 border-primary/10 rounded-full"
        />
        <motion.div 
          animate={{ rotate: -360 }}
          transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
          className="absolute inset-6 border border-emerald-500/10 rounded-full border-dashed"
        />
        <motion.div 
          animate={{ opacity: [0.1, 0.4, 0.1] }}
          transition={{ duration: 2, repeat: Infinity }}
          className="absolute inset-0 bg-primary/5 rounded-full"
        />
        
        <div className="z-10 flex flex-col items-center gap-4">
            <AnimatePresence mode="wait">
              <motion.div 
                key={phase}
                initial={{ scale: 0.5, opacity: 0, rotate: -45 }}
                animate={{ scale: 1, opacity: 1, rotate: 0 }}
                exit={{ scale: 1.5, opacity: 0, rotate: 45 }}
                className="w-24 h-24 bg-primary/20 rounded-[2rem] flex items-center justify-center text-primary border border-primary/30 shadow-[0_0_30px_rgba(59,130,246,0.3)]"
              >
                {phases[phase].icon}
              </motion.div>
            </AnimatePresence>
            <div className="text-center space-y-1">
                <motion.p 
                  key={`tx1-${phase}`}
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-white/40 font-black uppercase tracking-[0.3em] text-[10px]"
                >
                  Phase 0{phase + 1}
                </motion.p>
                <motion.p 
                  key={`tx2-${phase}`}
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-white font-black text-lg tracking-tight"
                >
                  {phases[phase].name}...
                </motion.p>
            </div>
        </div>
      </div>

      {/* Progress Items List */}
      <div className="mt-16 w-full max-w-xs px-4 space-y-5">
        {phases.map((p, i) => (
          <div key={i} className="flex items-center gap-5 transition-all duration-500" style={{ opacity: i <= phase ? 1 : 0.1, transform: `translateX(${i <= phase ? 0 : 20}px)` }}>
            <div className={`w-8 h-8 rounded-xl border-2 flex items-center justify-center transition-all duration-500 ${i < phase ? 'bg-emerald-500 border-emerald-500 text-black shadow-[0_0_15px_rgba(16,185,129,0.4)]' : i === phase ? 'border-primary shadow-[0_0_10px_rgba(59,130,246,0.4)]' : 'border-white/10'}`}>
              {i < phase ? <Check size={18} strokeWidth={4} /> : <div className={`w-1.5 h-1.5 bg-white rounded-full ${i === phase ? 'animate-ping' : ''}`} />}
            </div>
            <div className="flex flex-col">
              <span className={`text-[10px] font-black tracking-widest uppercase mb-0.5 ${i === phase ? 'text-primary' : 'text-white/20'}`}>
                {i < phase ? 'Completed' : i === phase ? 'Running' : 'Pending'}
              </span>
              <span className={`text-sm font-bold ${i === phase ? 'text-white' : 'text-white/40'}`}>
                {p.name}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Dynamic Data Stream Visualization */}
      <div className="absolute bottom-10 left-0 w-full flex justify-center gap-1 opacity-20 pointer-events-none overflow-hidden h-32">
        {[...Array(20)].map((_, i) => (
          <motion.div 
            key={i}
            animate={{ 
              y: [150, -150],
              opacity: [0, 1, 0]
            }}
            transition={{ 
              duration: 1 + Math.random() * 2, 
              repeat: Infinity, 
              delay: Math.random() * 2 
            }}
            className="w-[1px] bg-primary"
          />
        ))}
      </div>

      {/* Global Horizontal Scanning Line */}
      <motion.div 
        animate={{ top: ['-10%', '110%'] }}
        transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
        className="absolute left-0 right-0 h-[3px] bg-gradient-to-r from-transparent via-primary/50 to-transparent shadow-[0_0_20px_rgba(59,130,246,0.6)] z-20 pointer-events-none"
      />
    </div>
  );
}
