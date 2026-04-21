import { useState, useEffect, useRef, useCallback } from 'react';
import { imageService, QualityMetrics } from '../services/image';

export const useCamera = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const lastAnalysisRef = useRef<number>(0);
  
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [metrics, setMetrics] = useState<QualityMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    if (streamRef.current) return; // Already running

    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { 
          facingMode: 'environment',
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        }
      });
      
      streamRef.current = mediaStream;
      setStream(mediaStream);
      
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (err) {
      setError('Camera access denied');
      console.error(err);
    }
  }, []);

  const stop = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
      setStream(null);
    }
  }, []); // Explicitly stable, no dependencies

  // Analysis Loop
  useEffect(() => {
    if (!stream || !videoRef.current || !canvasRef.current) return;

    let active = true;
    const analyze = (time: number) => {
      if (!active) return;
      
      // Throttle to ~10fps (100ms) to prevent UI saturation/crashes
      if (time - lastAnalysisRef.current > 100) {
        const video = videoRef.current!;
        const canvas = canvasRef.current!;
        
        if (video.readyState === video.HAVE_ENOUGH_DATA) {
          const ctx = canvas.getContext('2d', { alpha: false })!;
          canvas.width = 300;
          canvas.height = 300;
          ctx.drawImage(video, 0, 0, 300, 300);
          
          const q = imageService.analyzeQuality(canvas);
          setMetrics(q);
          lastAnalysisRef.current = time;
        }
      }
      
      requestAnimationFrame(analyze);
    };

    requestAnimationFrame(analyze);
    return () => { active = false; };
  }, [stream]);

  const capture = useCallback((): string | null => {
    if (!videoRef.current) return null;
    
    const video = videoRef.current;
    const captureCanvas = document.createElement('canvas');
    captureCanvas.width = video.videoWidth;
    captureCanvas.height = video.videoHeight;
    const ctx = captureCanvas.getContext('2d')!;
    ctx.drawImage(video, 0, 0);
    
    return captureCanvas.toDataURL('image/jpeg', 0.95);
  }, []);

  return {
    videoRef,
    canvasRef,
    stream,
    metrics,
    error,
    start,
    stop,
    capture
  };
};
