import React, { useEffect, useState, useRef, useCallback } from 'react';
import { 
  Camera, 
  RefreshCcw, 
  CheckCircle2, 
  AlertCircle, 
  Zap, 
  Upload, 
  Power, 
  Focus,
  Lock,
  Loader2,
  Check,
  FolderOpen
} from 'lucide-react';
import { useCamera } from '../hooks/useCamera';
import { useHydraStore } from '../store/useHydraStore';
import { hydraApi } from '../services/api';
import './Scanner.css';

export const Scanner: React.FC = () => {
  const { videoRef, metrics, start, stop, capture, stream, error } = useCamera();
  const { addPage, scannedPages } = useHydraStore();
  
  const [isSystemActive, setIsSystemActive] = useState(false);
  const [isAutoScan, setIsAutoScan] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [stabilityCounter, setStabilityCounter] = useState(0);
  const [cooldown, setCooldown] = useState(0);
  const [lastScanStatus, setLastScanStatus] = useState<'IDLE' | 'SUCCESS' | 'ERROR'>('IDLE');
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const lockTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 1. Power Toggle Logic
  const toggleSystem = () => {
    if (isSystemActive) {
      stop();
      setIsSystemActive(false);
      setIsAutoScan(false);
    } else {
      start();
      setIsSystemActive(true);
    }
  };

  // 2. Robust Auto-Scan Intelligence
  useEffect(() => {
    if (!isAutoScan || !metrics?.isStable || cooldown > 0 || isIngesting) {
      setStabilityCounter(0);
      if (lockTimerRef.current) clearInterval(lockTimerRef.current);
      return;
    }

    lockTimerRef.current = setInterval(() => {
      setStabilityCounter(prev => {
        if (prev >= 15) { // 1.5 seconds target
          handleCapture();
          return 0;
        }
        return prev + 1;
      });
    }, 100);

    return () => {
      if (lockTimerRef.current) clearInterval(lockTimerRef.current);
    };
  }, [isAutoScan, metrics?.isStable, cooldown, isIngesting]);

  // 3. Cooldown & Notify Lifecycle
  useEffect(() => {
    if (cooldown > 0) {
      const timer = setTimeout(() => setCooldown(prev => prev - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [cooldown]);

  useEffect(() => {
    if (lastScanStatus !== 'IDLE') {
      const timer = setTimeout(() => setLastScanStatus('IDLE'), 3000);
      return () => clearTimeout(timer);
    }
  }, [lastScanStatus]);

  const processImage = async (image: string) => {
    try {
      setIsIngesting(true);
      const { scanId } = await hydraApi.ingest(image);
      addPage(image, scanId);
      setLastScanStatus('SUCCESS');
      setCooldown(3); 
    } catch (err) {
      console.error('Ingestion failed:', err);
      setLastScanStatus('ERROR');
    } finally {
      setIsIngesting(false);
    }
  };

  const handleCapture = async () => {
    if (isIngesting || cooldown > 0) return;
    
    const image = await capture(true);
    if (image) await processImage(image);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      if (!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = async (event) => {
        const b64 = event.target?.result as string;
        if (b64) await processImage(b64);
      };
      reader.readAsDataURL(file);
    });
    if (e.target) e.target.value = '';
  };

  return (
    <div className="scanner-station">
      <div className="scanner-viewfinder">
        {!isSystemActive ? (
          <div className="system-dormant">
            <div className="dormant-box">
              <Zap size={48} className="faded-icon" />
              <h2>SYSTEM DORMANT</h2>
              <p>Activate the Hydra Vision engine to begin scanning.</p>
              <button className="activate-btn" onClick={toggleSystem}>
                <Power size={18} />
                <span>INITIALIZE NEURAL LINK</span>
              </button>
            </div>
          </div>
        ) : (
          <>
            <video 
              ref={videoRef} 
              autoPlay 
              playsInline 
              muted 
              className={metrics?.isStable ? 'stable' : ''}
            />
            
            {/* Visual Notifications */}
            {lastScanStatus === 'SUCCESS' && (
              <div className="scan-ping success">
                <Check size={48} strokeWidth={3} />
                <span>IMAGE INGESTED</span>
              </div>
            )}
            
            {/* Neural Lock HUD */}
            {isAutoScan && metrics?.isStable && !isIngesting && cooldown === 0 && (
              <div className="neural-lock-ui">
                <div className="lock-ring">
                  <svg viewBox="0 0 100 100">
                    <circle 
                      cx="50" cy="50" r="45" 
                      style={{ strokeDashoffset: 283 - (283 * (stabilityCounter / 15)) }} 
                    />
                  </svg>
                  <Lock size={24} className="lock-icon" />
                </div>
                <span>LOCKING...</span>
              </div>
            )}

            {/* Quality HUD */}
            <div className="scanner-hud">
              <div className="hud-metric">
                <span className="label">STABILITY</span>
                <div className="bar-container">
                  <div 
                    className="bar" 
                    style={{ 
                      width: `${Math.min(100, (metrics?.blur || 0) * 15)}%`,
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

            <div className="scanner-overlay">
              <div className="corner tl" />
              <div className="corner tr" />
              <div className="corner bl" />
              <div className="corner br" />
            </div>
          </>
        )}

        {isIngesting && (
          <div className="processing-overlay">
            <div className="neural-pulse-box">
              <RefreshCcw size={48} className="spin" />
              <span>Hydra Normalizing & Ingesting...</span>
            </div>
          </div>
        )}
      </div>

      <div className="scanner-controls">
        <div className="scanner-status">
          <div className="status-badge">
            {isIngesting ? (
              <><Loader2 size={14} className="spin" /> <span>Transmitting to Hydra</span></>
            ) : cooldown > 0 ? (
              <><RefreshCcw size={14} className="spin" /> <span>Recalibrating ({cooldown}s)</span></>
            ) : metrics?.isStable ? (
              <><CheckCircle2 size={14} color="var(--success)" /> <span>Target Locked</span></>
            ) : (
              <><Focus size={14} color="var(--tertiary)" /> <span>Scanning Environment</span></>
            )}
          </div>
          <p className="status-hint">
            {isAutoScan ? 'Auto-Scan enabled. Hold document steady.' : 'Manual capture mode engaged.'}
          </p>
        </div>

        <div className="capture-ops">
          <button 
            className={`op-btn ${isAutoScan ? 'active' : ''}`} 
            onClick={() => setIsAutoScan(!isAutoScan)}
            disabled={!isSystemActive || isIngesting}
            title="Auto-Scan Toggle"
          >
            <Focus size={18} />
          </button>

          <button 
            className={`capture-btn ${(!isSystemActive || isIngesting || cooldown > 0) ? 'disabled' : ''}`}
            onClick={handleCapture}
            disabled={!isSystemActive || isIngesting || cooldown > 0}
          >
            <div className="btn-inner">
              <Camera size={24} />
            </div>
            <div className="btn-ring" />
          </button>
          
          <button 
            className="op-btn" 
            onClick={toggleSystem}
            title="Toggle Engine"
          >
            <Power size={18} color={isSystemActive ? 'var(--error)' : 'var(--success)'} />
          </button>
        </div>

        <div className="scanner-history">
          {/* File Input */}
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileUpload} 
            accept="image/*" 
            multiple
            style={{ display: 'none' }} 
          />
          {/* Folder Input */}
          <input 
            type="file" 
            ref={folderInputRef}
            onChange={handleFileUpload} 
            accept="image/*" 
            //@ts-ignore
            webkitdirectory=""
            directory=""
            multiple
            style={{ display: 'none' }} 
          />
          
          <div className="history-ops">
            <button 
              className="upload-op-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={isIngesting}
              title="Upload Files"
            >
              <Upload size={18} />
            </button>
            <button 
              className="upload-op-btn"
              onClick={() => folderInputRef.current?.click()}
              disabled={isIngesting}
              title="Upload Folder"
            >
              <FolderOpen size={18} />
            </button>
          </div>
          
          <div className="history-thumbs-box">
            {scannedPages.slice(0, 3).map(page => (
              <div key={page.id} className={`history-thumb ${page.status}`}>
                <img src={page.image} alt="scanned" />
                {page.status === 'processing' && <Loader2 size={12} className="thumb-spin spin" />}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
