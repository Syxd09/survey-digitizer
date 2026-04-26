import React, { useState, useEffect, useRef } from 'react';
import { hydraApi } from '../services/api';
import './ReviewStation.css';

interface Field {
  field_id: string;
  type: string;
  raw_text: string;
  cleaned_text: string;
  field_conf: number;
  status: string;
  bbox: number[]; // [x1, y1, x2, y2]
}

interface RequestItem {
  request_id: string;
  status: string;
  overall_conf: number;
  processed_at: string;
}

const ReviewStation: React.FC = () => {
  const [queue, setQueue] = useState<RequestItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeRequest, setActiveRequest] = useState<{trace: any, fields: Field[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeFieldId, setActiveFieldId] = useState<string | null>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchQueue();
  }, []);

  const fetchQueue = async () => {
    try {
      const data = await hydraApi.listForms('NEEDS_REVIEW');
      setQueue(data.data || []);
    } catch (err) {
      console.error("Failed to fetch queue", err);
    }
  };

  const selectRequest = async (id: string) => {
    setSelectedId(id);
    setLoading(true);
    try {
      const data = await hydraApi.getFormDetails(id);
      setActiveRequest(data);
      if (data.fields?.length > 0) {
        setActiveFieldId(data.fields[0].field_id);
      }
    } catch (err) {
      console.error("Failed to fetch request details", err);
    } finally {
      setLoading(false);
    }
  };

  const updateField = async (fieldId: string, newValue: string) => {
    if (!selectedId) return;
    try {
      await hydraApi.correctField(selectedId, fieldId, newValue);
      // Locally update to feel fast
      if (activeRequest) {
        setActiveRequest({
          ...activeRequest,
          fields: activeRequest.fields.map(f => f.field_id === fieldId ? { ...f, cleaned_text: newValue, status: 'OK' } : f)
        });
      }
    } catch (err) {
      console.error("Update failed", err);
    }
  };

  const API_KEY = import.meta.env.VITE_HYDRA_API_KEY || 'hydra_secret_v2';

  const handleFieldClick = (field: Field) => {
    setActiveFieldId(field.field_id);
    if (imageRef.current && scrollContainerRef.current && field.bbox) {
        const [x1, y1, x2, y2] = field.bbox;
        const img = imageRef.current;
        const container = scrollContainerRef.current;
        
        // Calculate relative position
        const scaleX = img.clientWidth / img.naturalWidth;
        const scaleY = img.clientHeight / img.naturalHeight;
        const centerY = (y1 + y2) / 2 * scaleY;
        
        container.scrollTo({
            top: centerY - container.clientHeight / 2,
            behavior: 'smooth'
        });
    }
  };

  const getImageUrl = (type: 'overlay' | 'original', id: string) => {
    const base = type === 'overlay' ? 'debug/overlay' : 'image/original';
    return `http://localhost:8000/${base}/${id}?api_key=${API_KEY}`;
  };

  return (
    <div className="review-station">
      <div className="review-header">
        <h1>Phase 11: Exception Review</h1>
        <div className="stats">
          <span>{queue.length} Forms Pending Review</span>
        </div>
      </div>

      <div className="review-content">
        {/* Left Panel: Request Queue */}
        <div className="review-queue">
          <div className="queue-header">Needs Review</div>
          <div className="queue-list">
            {queue.map(item => (
              <div 
                key={item.request_id} 
                className={`queue-item ${selectedId === item.request_id ? 'active' : ''}`}
                onClick={() => selectRequest(item.request_id)}
              >
                <div className="item-id">{item.request_id.slice(0, 12)}</div>
                <div className="item-meta">
                  <span className="status-badge status-review">{item.status}</span>
                  <span className="conf-score">{(item.overall_conf * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
            {queue.length === 0 && (
              <div className="empty-state">No forms pending review</div>
            )}
          </div>
        </div>

        {/* Center Panel: Side-by-Side Image + Fields */}
        <div className="review-workspace">
          {loading ? (
            <div className="empty-state">Loading analysis...</div>
          ) : activeRequest ? (
            <>
              <div className="image-viewer" ref={scrollContainerRef}>
                <img 
                  ref={imageRef}
                  src={getImageUrl('overlay', selectedId!)}
                  alt="Review Overlay"
                  className="full-review-image"
                  onError={(e) => {
                      e.currentTarget.src = getImageUrl('original', selectedId!);
                  }}
                />
                {/* Active Highlight Overlay */}
                {activeFieldId && activeRequest.fields.find(f => f.field_id === activeFieldId)?.bbox && imageRef.current && (
                    <div 
                        className="field-highlight-overlay"
                        style={{
                            position: 'absolute',
                            border: '4px solid #4facfe',
                            boxShadow: '0 0 0 9999px rgba(0,0,0,0.5)',
                            pointerEvents: 'none',
                            zIndex: 10,
                            left: `${(activeRequest.fields.find(f => f.field_id === activeFieldId)!.bbox[0] / imageRef.current.naturalWidth) * 100}%`,
                            top: `${(activeRequest.fields.find(f => f.field_id === activeFieldId)!.bbox[1] / imageRef.current.naturalHeight) * 100}%`,
                            width: `${((activeRequest.fields.find(f => f.field_id === activeFieldId)!.bbox[2] - activeRequest.fields.find(f => f.field_id === activeFieldId)!.bbox[0]) / imageRef.current.naturalWidth) * 100}%`,
                            height: `${((activeRequest.fields.find(f => f.field_id === activeFieldId)!.bbox[3] - activeRequest.fields.find(f => f.field_id === activeFieldId)!.bbox[1]) / imageRef.current.naturalHeight) * 100}%`,
                        }}
                    />
                )}
              </div>

              <div className="fields-panel">
                <div className="panel-header">Field Corrections</div>
                <div className="fields-list">
                  {activeRequest.fields.map(field => (
                    <div 
                        key={field.field_id} 
                        className={`field-row ${activeFieldId === field.field_id ? 'active' : ''} status-${field.status}`}
                        onClick={() => handleFieldClick(field)}
                    >
                      <div className="field-label-group">
                        <span className="field-id">{field.field_id}</span>
                        <span className="field-conf">{(field.field_conf * 100).toFixed(0)}%</span>
                      </div>
                      
                      <div className="field-input-group">
                        <input 
                          className="correction-input"
                          defaultValue={field.cleaned_text}
                          onBlur={(e) => {
                            if (e.target.value !== field.cleaned_text) {
                              updateField(field.field_id, e.target.value);
                            }
                          }}
                        />
                        <div className="original-val">OCR: <code>{field.raw_text || '[empty]'}</code></div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="panel-actions">
                    <button className="btn-approve-all" onClick={() => fetchQueue()}>Complete Review</button>
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state">Select a form from the left to begin human verification.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ReviewStation;
