import React, { useState, useRef, useEffect } from "react";
import { ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import "./ImageViewer.css";

interface QualityMetrics {
  sharpness?: number;
  contrast?: number;
  brightness?: number;
  saturation?: number;
  skew_angle?: number;
  document_coverage?: number;
  quality_score?: number;
}

interface ImageViewerProps {
  imageUrl: string;
  actualWidth?: number;
  actualHeight?: number;
  qualityMetrics?: QualityMetrics;
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  }[];
  showMetrics?: boolean;
}

export const ImageViewer: React.FC<ImageViewerProps> = ({
  imageUrl,
  actualWidth = 1920,
  actualHeight = 1440,
  qualityMetrics = {},
  bbox = [],
  showMetrics = true,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const aspectRatio = actualWidth && actualHeight ? actualWidth / actualHeight : 1;

  const handleZoom = (direction: "in" | "out") => {
    setZoom((prev) => {
      const newZoom = direction === "in" ? prev * 1.2 : prev / 1.2;
      return Math.max(0.5, Math.min(newZoom, 5));
    });
  };

  const handleResetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (zoom <= 1) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || zoom <= 1 || !containerRef.current) return;

    const newX = e.clientX - dragStart.x;
    const newY = e.clientY - dragStart.y;

    const maxX = (containerRef.current.clientWidth * (zoom - 1)) / 2;
    const maxY = (containerRef.current.clientHeight * (zoom - 1)) / 2;

    setPan({
      x: Math.max(-maxX, Math.min(maxX, newX)),
      y: Math.max(-maxY, Math.min(maxY, newY)),
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const getQualityColor = (value: number) => {
    if (value >= 80) return "text-green-600";
    if (value >= 60) return "text-yellow-600";
    return "text-red-600";
  };

  return (
    <div className="image-viewer-container">
      <div className="image-viewer-controls">
        <button
          onClick={() => handleZoom("out")}
          title="Zoom Out"
          className="control-btn"
          disabled={zoom <= 0.5}
        >
          <ZoomOut size={20} />
        </button>
        <span className="zoom-level">{Math.round(zoom * 100)}%</span>
        <button
          onClick={() => handleZoom("in")}
          title="Zoom In"
          className="control-btn"
          disabled={zoom >= 5}
        >
          <ZoomIn size={20} />
        </button>
        <button onClick={handleResetView} title="Reset View" className="control-btn">
          <RotateCcw size={20} />
        </button>
      </div>

      <div
        ref={containerRef}
        className="image-viewer-main"
        style={{
          aspectRatio: `${aspectRatio} / 1`,
          cursor: zoom > 1 ? (isDragging ? "grabbing" : "grab") : "auto",
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div
          className="image-viewer-content"
          style={{
            transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
            transformOrigin: "center",
            transition: isDragging ? "none" : "transform 0.1s ease-out",
          }}
        >
          <img
            ref={imgRef}
            src={imageUrl}
            alt="Scanned document"
            className="viewer-image"
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
            }}
          />

          {/* Bounding boxes overlay */}
          {bbox.length > 0 && (
            <svg
              className="bbox-overlay"
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: "100%",
                pointerEvents: "none",
              }}
              viewBox={`0 0 ${actualWidth} ${actualHeight}`}
              preserveAspectRatio="none"
            >
              {bbox.map((box, idx) => (
                <rect
                  key={idx}
                  x={box.x}
                  y={box.y}
                  width={box.width}
                  height={box.height}
                  fill="none"
                  stroke={idx % 2 === 0 ? "#22c55e" : "#fb923c"}
                  strokeWidth="2"
                  opacity="0.7"
                />
              ))}
            </svg>
          )}
        </div>
      </div>

      {/* Quality metrics overlay */}
      {showMetrics && (
        <div className="quality-metrics">
          <div className="metrics-grid">
            {qualityMetrics.quality_score !== undefined && (
              <div className="metric-item">
                <span className="metric-label">Overall Quality</span>
                <span
                  className={`metric-value ${getQualityColor(
                    qualityMetrics.quality_score
                  )}`}
                >
                  {qualityMetrics.quality_score.toFixed(1)}/100
                </span>
              </div>
            )}
            {qualityMetrics.sharpness !== undefined && (
              <div className="metric-item">
                <span className="metric-label">Sharpness</span>
                <span className={`metric-value ${getQualityColor(qualityMetrics.sharpness)}`}>
                  {qualityMetrics.sharpness.toFixed(0)}
                </span>
              </div>
            )}
            {qualityMetrics.contrast !== undefined && (
              <div className="metric-item">
                <span className="metric-label">Contrast</span>
                <span className={`metric-value ${getQualityColor(qualityMetrics.contrast)}`}>
                  {qualityMetrics.contrast.toFixed(0)}
                </span>
              </div>
            )}
            {qualityMetrics.brightness !== undefined && (
              <div className="metric-item">
                <span className="metric-label">Brightness</span>
                <span className={`metric-value ${getQualityColor(qualityMetrics.brightness)}`}>
                  {qualityMetrics.brightness.toFixed(0)}
                </span>
              </div>
            )}
            {qualityMetrics.skew_angle !== undefined && (
              <div className="metric-item">
                <span className="metric-label">Skew Angle</span>
                <span className="metric-value">
                  {Math.abs(qualityMetrics.skew_angle).toFixed(1)}°
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
