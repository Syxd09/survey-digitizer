import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Camera, RefreshCcw, CheckCircle2, AlertCircle, Zap, Upload } from 'lucide-react';
import { useCamera } from '../hooks/useCamera';
import { useHydraStore } from '../store/useHydraStore';
import { hydraApi } from '../services/api';
import './Scanner.css';

export const Scanner: React.FC = () => {
  const { videoRef, metrics, start, stop, capture } = useCamera();
  const { addPage, updatePageStatus, scannedPages } = useHydraStore();
  const [isCapturing, setIsCapturing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    start();
    return () => stop();
  }, [start, stop]);

  /**
   * Polling Logic for Async Scans
   */
  useEffect(() => {
    const unfinishedPages = scannedPages.filter(
      p => p.status === 'uploaded' || p.status === 'processing'
    );

    if (unfinishedPages.length === 0) return;

    const interval = setInterval(async () => {
      for (const page of unfinishedPages) {
        try {
          const statusResult = await hydraApi.getScanStatus(page.id);
          
          if (statusResult.status !== 'uploaded' && statusResult.status !== 'processing') {
            updatePageStatus(page.id, statusResult.status, statusResult);
          } else if (statusResult.status === 'processing' && page.status !== 'processing') {
            updatePageStatus(page.id, 'processing');
          }
        } catch (err) {
          console.error(`Status check failed for ${page.id}:`, err);
        }
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [scannedPages, updatePageStatus]);

  const processImage = async (image: string) => {
    try {
      setIsCapturing(true);
      // 1. Kick off async ingestion
      const { scanId } = await hydraApi.ingest(image);
      
      // 2. Add to store
      addPage(image, scanId);
    } catch (err) {
      console.error('Ingestion failed:', err);
    } finally {
      setIsCapturing(false);
    }
  };

  const handleCapture = async () => {
    const image = capture();
    if (image) await processImage(image);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = async (event) => {
        const b64 = event.target?.result as string;
        if (b64) await processImage(b64);
      };
      reader.readAsDataURL(file);
    });
    
    // Reset input
    if (fileInputRef.current) fileInputRef.current.value = '';
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

        {isCapturing && (
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
          <p className="status-hint">Position the survey form within the frame or upload files.</p>
        </div>

        <div className="capture-ops">
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileUpload} 
            accept="image/*" 
            multiple
            style={{ display: 'none' }} 
          />
          
          <button 
            className="upload-op-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={isCapturing}
          >
            <Upload size={18} />
          </button>

          <button 
            className={`capture-btn ${isCapturing ? 'disabled' : ''}`}
            onClick={handleCapture}
            disabled={isCapturing}
          >
            <div className="btn-inner">
              <Camera size={24} />
            </div>
            <div className="btn-ring" />
          </button>
          
          <div className="capture-op-placeholder" /> {/* Balancer */}
        </div>

        <div className="scanner-history">
          {scannedPages.slice(0, 5).map(page => (
            <div key={page.id} className={`history-thumb ${page.status.toLowerCase()}`}>
              <img src={page.image} alt="scanned" />
              <div className="thumb-status-box">
                {(page.status === 'good' || page.status === 'conflict') && <CheckCircle2 size={12} fill="var(--success)" color="var(--bg-primary)" />}
                {(page.status === 'uploaded' || page.status === 'processing') && <RefreshCcw size={12} className="spin" />}
                {page.status === 'bad' && <AlertCircle size={12} fill="var(--tertiary)" color="var(--bg-primary)" />}
                {page.status === 'failed' && <AlertCircle size={12} fill="var(--error)" color="var(--bg-primary)" />}
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
