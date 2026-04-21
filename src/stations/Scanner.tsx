import React, { useEffect, useState, useRef } from 'react';
import { Camera, RefreshCcw, CheckCircle2, AlertCircle, Zap, Upload } from 'lucide-react';
import { useCamera } from '../hooks/useCamera';
import { useHydraStore } from '../store/useHydraStore';
import { hydraApi } from '../services/api';
import './Scanner.css';

export const Scanner: React.FC = () => {
  const { videoRef, metrics, stream, start, stop, capture, error } = useCamera();
  const { addPage, updatePageStatus, scannedPages } = useHydraStore();
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    start();
    return () => stop();
  }, [start, stop]);

  const processImage = async (image: string) => {
    const pageId = addPage(image);
    setIsProcessing(true);

    try {
      updatePageStatus(pageId, 'PROCESSING');
      const result = await hydraApi.process(image);
      updatePageStatus(pageId, 'COMPLETED', result);
    } catch (err) {
      updatePageStatus(pageId, 'FAILED');
      console.error('Processing failed:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCapture = async () => {
    const image = capture();
    if (image) await processImage(image);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (event) => {
      const b64 = event.target?.result as string;
      if (b64) await processImage(b64);
    };
    reader.readAsDataURL(file);
  };

  return (
    <div className="scanner-station">
      <div className="scanner-viewfinder">
        <video 
          ref={videoRef} 
          autoPlay 
          playsInline 
          muted 
          className={metrics?.isStable ? 'stable' : ''}
        />
        
        {/* Quality HUD */}
        <div className="scanner-hud">
          <div className="hud-metric">
            <span className="label">STABILITY</span>
            <div className="bar-container">
              <div 
                className="bar" 
                style={{ 
                  width: `${Math.min(100, (metrics?.blur || 0) * 10)}%`,
                  background: metrics?.isStable ? 'var(--success)' : 'var(--tertiary)'
                }} 
              />
            </div>
          </div>
          <div className="hud-metric">
            <span className="label">LUMINANCE</span>
            <div className="bar-container">
              <div 
                className="bar" 
                style={{ 
                  width: `${Math.min(100, (metrics?.brightness || 0) / 2.55)}%`,
                  background: 'var(--primary)'
                }} 
              />
            </div>
          </div>
        </div>

        {/* Framing Guides */}
        <div className="scanner-overlay">
          <div className="corner tl" />
          <div className="corner tr" />
          <div className="corner bl" />
          <div className="corner br" />
        </div>

        {isProcessing && (
          <div className="processing-overlay">
            <div className="neural-pulse-box">
              <Zap size={48} className="pulse-icon" />
              <span>Hydra Ingesting...</span>
            </div>
          </div>
        )}
      </div>

      <div className="scanner-controls">
        <div className="scanner-status">
          <div className="status-badge">
            {metrics?.isStable ? (
              <><CheckCircle2 size={14} color="var(--success)" /> <span>System Stable</span></>
            ) : (
              <><AlertCircle size={14} color="var(--tertiary)" /> <span>Align Document</span></>
            )}
          </div>
          <p className="status-hint">Position the survey form within the frame or upload a file.</p>
        </div>

        <div className="capture-ops">
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileUpload} 
            accept="image/*" 
            style={{ display: 'none' }} 
          />
          
          <button 
            className="upload-op-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={isProcessing}
          >
            <Upload size={18} />
          </button>

          <button 
            className={`capture-btn ${isProcessing ? 'disabled' : ''}`}
            onClick={handleCapture}
            disabled={isProcessing}
          >
            <div className="btn-inner">
              <Camera size={24} />
            </div>
            <div className="btn-ring" />
          </button>
          
          <div className="capture-op-placeholder" /> {/* Balancer */}
        </div>

        <div className="scanner-history">
          {scannedPages.slice(0, 3).map(page => (
            <div key={page.id} className={`history-thumb ${page.status.toLowerCase()}`}>
              <img src={page.image} alt="scanned" />
              <div className="thumb-status-box">
                {page.status === 'COMPLETED' && <CheckCircle2 size={12} fill="var(--success)" color="var(--bg-primary)" />}
                {page.status === 'PROCESSING' && <RefreshCcw size={12} className="spin" />}
              </div>
            </div>
          ))}
          {scannedPages.length === 0 && (
            <div className="history-empty">
              <span>Ready</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
