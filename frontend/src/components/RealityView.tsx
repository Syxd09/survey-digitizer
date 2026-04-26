import { ExtractionQuestion, OrphanText, SurveyField } from '../services/api';
import './RealityView.css';

interface RealityViewProps {
  imageUrl: string;
  questions: ExtractionQuestion[];
  orphans?: OrphanText[];
  fields?: SurveyField[];
  imageWidth?: number;
  imageHeight?: number;
  hoveredIndex: number | null;
  onHover: (index: number | null) => void;
}

export const RealityView: React.FC<RealityViewProps> = ({
  imageUrl,
  questions,
  orphans = [],
  fields = [],
  imageWidth = 1000,
  imageHeight = 1000,
  hoveredIndex,
  onHover,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const updateScale = () => {
      if (containerRef.current) {
        const { width } = containerRef.current.getBoundingClientRect();
        setScale(width / imageWidth);
      }
    };

    window.addEventListener('resize', updateScale);
    updateScale();
    return () => window.removeEventListener('resize', updateScale);
  }, [imageWidth]);

  return (
    <div className="reality-view-container" ref={containerRef}>
      <img src={imageUrl} alt="Original Document" className="reality-image" />
      
      <svg 
        className="reality-overlay" 
        viewBox={`0 0 ${imageWidth} ${imageHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Orphaned OCR Regions (Unstructured Text) */}
        {orphans.map((o, idx) => (
          <g key={`orphan-${idx}`}>
            <rect
              x={o.bbox[0]}
              y={o.bbox[1]}
              width={o.bbox[2] - o.bbox[0]}
              height={o.bbox[3] - o.bbox[1]}
              className="reality-bbox orphan-bbox"
            />
            <title>{o.text}</title>
          </g>
        ))}

        {/* Metadata Fields */}
        {fields.map((f, idx) => (
          <g key={`field-${idx}`}>
            {f.bbox && (
              <rect
                x={f.bbox[0]}
                y={f.bbox[1]}
                width={f.bbox[2] - f.bbox[0]}
                height={f.bbox[3] - f.bbox[1]}
                className="reality-bbox field-label-bbox"
              />
            )}
            {f.value_bbox && (
              <rect
                x={f.value_bbox[0]}
                y={f.value_bbox[1]}
                width={f.value_bbox[2] - f.value_bbox[0]}
                height={f.value_bbox[3] - f.value_bbox[1]}
                className="reality-bbox field-value-bbox"
              />
            )}
          </g>
        ))}

        {/* Structured Questions */}
        {questions.map((q, idx) => {
          if (!q.bbox) return null;
          
          const [x1, y1, x2, y2] = q.bbox;
          const isHovered = hoveredIndex === idx;
          
          return (
            <g key={`q-${idx}`} onMouseEnter={() => onHover(idx)} onMouseLeave={() => onHover(null)}>
              {/* Question BBox */}
              <rect
                x={x1}
                y={y1}
                width={x2 - x1}
                height={y2 - y1}
                className={`reality-bbox question-bbox ${isHovered ? 'active' : ''}`}
              />
              
              {/* Value BBox (if exists) */}
              {q.value_bbox && (
                <rect
                  x={q.value_bbox[0]}
                  y={q.value_bbox[1]}
                  width={q.value_bbox[2] - q.value_bbox[0]}
                  height={q.value_bbox[3] - q.value_bbox[1]}
                  className={`reality-bbox value-bbox ${isHovered ? 'active' : ''}`}
                />
              )}

              {/* Label */}
              {isHovered && (
                <foreignObject x={x1} y={y1 - 25} width="400" height="40">
                  <div className="reality-label">
                    {q.question}
                  </div>
                </foreignObject>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};
