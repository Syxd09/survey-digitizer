import React, { useState, useEffect, useRef } from 'react';
import { Camera, X, RotateCcw, Zap, ZapOff } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { Quad, detectQuad, analyzeImageQuality } from '../services/alignmentService';

interface CameraScannerProps {
  onCapture: (blob: Blob, quad: Quad) => void;
  onClose: () => void;
  autoCapture?: boolean;
}

export default function CameraScanner({ onCapture, onClose, autoCapture = true }: CameraScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [torch, setTorch] = useState(false);
  const [detectedQuad, setDetectedQuad] = useState<Quad | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isStable, setIsStable] = useState(false);
  const [stabilityCounter, setStabilityCounter] = useState(0);

  useEffect(() => {
    async function setupCamera() {
      try {
        const s = await navigator.mediaDevices.getUserMedia({
          video: { 
            facingMode: 'environment', 
            width: { ideal: 1920 }, 
            height: { ideal: 1080 } 
          }
        });
        setStream(s);
        if (videoRef.current) videoRef.current.srcObject = s;
      } catch (err) {
        console.error("Camera access failed:", err);
        alert("Camera access is required for scanning. Please check your permissions.");
      }
    }
    setupCamera();
    return () => {
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
      }
    };
  }, []);

  // Real-time quad detection loop
  useEffect(() => {
    if (!stream) return;
    const interval = setInterval(() => {
      if (videoRef.current && canvasRef.current) {
        const canvas = canvasRef.current;
        const video = videoRef.current;
        
        // Use a smaller canvas for quad detection performance
        const scale = 0.25;
        canvas.width = video.videoWidth * scale;
        canvas.height = video.videoHeight * scale;
        
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          
          const { quad, confidence } = detectQuad(canvas);
          const quality = analyzeImageQuality(canvas);
          
          const stable = quality.isStable && confidence > 0.8;
          setIsStable(stable);
          
          if (stable) {
            setDetectedQuad(quad);
            setStabilityCounter(prev => prev + 1);
          } else {
            setStabilityCounter(0);
          }
        }
      }
    }, 200);
    return () => clearInterval(interval);
  }, [stream]);

  // Auto-capture logic
  useEffect(() => {
    if (autoCapture && stabilityCounter >= 6) { // ~1.2 seconds of stability
      handleCapture();
    }
  }, [stabilityCounter]);

  const handleCapture = () => {
    if (!videoRef.current || isCapturing) return;
    
    setIsCapturing(true);
    const video = videoRef.current;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.drawImage(video, 0, 0);
      canvas.toBlob((blob) => {
        if (blob) {
          // If no quad is detected yet, use a default fallback
          const quad = detectedQuad || {
            topLeft: { x: 0.1, y: 0.1 },
            topRight: { x: 0.9, y: 0.1 },
            bottomLeft: { x: 0.1, y: 0.9 },
            bottomRight: { x: 0.9, y: 0.9 }
          };
          onCapture(blob, quad);
        }
        setIsCapturing(false);
      }, 'image/jpeg', 0.95);
    }
  };

  const toggleTorch = async () => {
    const track = stream?.getVideoTracks()[0];
    if (track && 'applyConstraints' in (track as any)) {
      try {
        const newTorch = !torch;
        await (track as any).applyConstraints({ advanced: [{ torch: newTorch }] });
        setTorch(newTorch);
      } catch (e) {
        console.warn("Torch not supported on this device.");
      }
    }
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black flex flex-col items-center justify-center overflow-hidden">
      <video 
        ref={videoRef} 
        autoPlay 
        playsInline 
        className="absolute inset-0 w-full h-full object-cover opacity-60"
      />
      
      {/* Scanning Overlay Container */}
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
        <div className={`w-[80%] aspect-[3/4] border-2 ${isStable ? 'border-emerald-500/40' : 'border-white/20'} rounded-3xl relative overflow-hidden transition-colors duration-300`}>
          {/* Corner Decorations */}
          <div className={`absolute top-0 left-0 w-16 h-16 border-t-4 border-l-4 ${isStable ? 'border-emerald-500' : 'border-primary'} rounded-tl-3xl shadow-[0_0_15px_rgba(0,0,0,0.5)] transition-colors`} />
          <div className={`absolute top-0 right-0 w-16 h-16 border-t-4 border-r-4 ${isStable ? 'border-emerald-500' : 'border-primary'} rounded-tr-3xl shadow-[0_0_15px_rgba(0,0,0,0.5)] transition-colors`} />
          <div className={`absolute bottom-0 left-0 w-16 h-16 border-b-4 border-l-4 ${isStable ? 'border-emerald-500' : 'border-primary'} rounded-bl-3xl shadow-[0_0_15px_rgba(0,0,0,0.5)] transition-colors`} />
          <div className={`absolute bottom-0 right-0 w-16 h-16 border-b-4 border-r-4 ${isStable ? 'border-emerald-500' : 'border-primary'} rounded-br-3xl shadow-[0_0_15px_rgba(0,0,0,0.5)] transition-colors`} />
          
          {/* Animated Laser Line */}
          <motion.div 
            animate={{ top: ['5%', '95%', '5%'], opacity: isStable ? 1 : 0.4 }}
            transition={{ duration: isStable ? 1.5 : 4, repeat: Infinity, ease: "easeInOut" }}
            className={`absolute left-6 right-6 h-1 ${isStable ? 'bg-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.8)]' : 'bg-primary/60 shadow-[0_0_20px_rgba(59,130,246,0.8)]'} z-10 transition-all`}
          />

          {/* Ghost Image Mock for Digitization vibe */}
          <div className="absolute inset-0 bg-primary/5 flex items-center justify-center opacity-20">
            <motion.div 
              animate={{ opacity: [0.1, 0.3, 0.1] }}
              transition={{ duration: 2, repeat: Infinity }}
              className="w-full h-full border border-primary/20"
            />
          </div>
        </div>
      </div>

      {/* Detected Quad Visualizer (Optional UI) */}
      <AnimatePresence>
        {detectedQuad && (
          <svg className="absolute inset-0 w-full h-full pointer-events-none z-20 overflow-visible">
            <motion.path 
              initial={{ opacity: 0 }}
              animate={{ opacity: isStable ? 0.6 : 0.3 }}
              exit={{ opacity: 0 }}
              d={`M ${detectedQuad.topLeft.x * 100}% ${detectedQuad.topLeft.y * 100}% 
                 L ${detectedQuad.topRight.x * 100}% ${detectedQuad.topRight.y * 100}% 
                 L ${detectedQuad.bottomRight.x * 100}% ${detectedQuad.bottomRight.y * 100}% 
                 L ${detectedQuad.bottomLeft.x * 100}% ${detectedQuad.bottomLeft.y * 100}% Z`}
              fill={isStable ? "rgba(16, 185, 129, 0.2)" : "rgba(59, 130, 246, 0.2)"}
              stroke={isStable ? "#10b981" : "#3b82f6"}
              strokeWidth="2"
              strokeDasharray="5,5"
              transition={{ duration: 0.3 }}
            />
          </svg>
        )}
      </AnimatePresence>

      {/* Top Controls */}
      <div className="absolute top-10 left-0 w-full flex justify-between px-10 z-50">
        <button 
          onClick={onClose} 
          className="p-4 bg-black/50 backdrop-blur-xl rounded-full text-white hover:bg-black/80 transition-all border border-white/10"
        >
          <X size={24} />
        </button>
        <button 
          onClick={toggleTorch} 
          className="p-4 bg-black/50 backdrop-blur-xl rounded-full text-white hover:bg-black/80 transition-all border border-white/10"
        >
          {torch ? <Zap size={24} className="text-yellow-400" /> : <ZapOff size={24} />}
        </button>
      </div>

      {/* Bottom Interface */}
      <div className="absolute bottom-12 left-0 w-full px-10 flex flex-col items-center gap-10 z-50">
        <div className={`flex items-center gap-3 px-6 py-2.5 rounded-full backdrop-blur-md border transition-all duration-500 ${isStable ? 'bg-emerald-500/20 border-emerald-500/30 text-emerald-100 scale-110 shadow-[0_0_20px_rgba(16,185,129,0.2)]' : 'bg-black/30 border-white/5 text-white/80'}`}>
          {isStable && <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ repeat: Infinity }} className="w-2 h-2 rounded-full bg-emerald-500" />}
          <span className="text-[10px] font-black uppercase tracking-[0.3em]">
            {isStable ? (stabilityCounter > 3 ? "Auto-Capturing..." : "Document Locked") : "Align Survey with Frame"}
          </span>
        </div>

        <div className="flex items-center justify-between w-full max-w-sm">
          <button className="p-4 bg-white/5 backdrop-blur-md rounded-full text-white/40 cursor-not-allowed">
            <RotateCcw size={28} />
          </button>
          
          <button 
            onClick={handleCapture}
            disabled={isCapturing}
            className={`relative group p-2 rounded-full border-4 ${isCapturing ? 'border-primary/50' : 'border-white/50'} transition-all`}
          >
            <div className={`w-20 h-20 rounded-full ${isCapturing ? 'bg-primary/20' : 'bg-white'} flex items-center justify-center transition-all group-active:scale-95 shadow-2xl`}>
              {isCapturing ? (
                <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
              ) : (
                <Camera size={38} className="text-primary" />
              )}
            </div>
            {/* Pulsing ring when not capturing */}
            {!isCapturing && (
              <div className="absolute inset-0 rounded-full border-4 border-white/30 animate-ping opacity-20" />
            )}
          </button>

          <div className="w-16 flex justify-center">
             {/* Thumbnail mockup or similar */}
             <div className="w-12 h-16 bg-white/10 rounded-lg border border-white/20 overflow-hidden shadow-xl rotate-3">
                <div className="w-full h-full bg-gradient-to-br from-white/10 to-transparent" />
             </div>
          </div>
        </div>
      </div>

      {/* Hidden Canvas for computation */}
      <canvas ref={canvasRef} className="hidden" />
      
      <style>{`
        .bg-primary { background-color: rgb(59, 130, 246); }
        .text-primary { color: rgb(59, 130, 246); }
        .border-primary { border-color: rgb(59, 130, 246); }
        .shadow-primary { --tw-shadow-color: rgba(59, 130, 246, 0.5); }
      `}</style>
    </div>
  );
}
