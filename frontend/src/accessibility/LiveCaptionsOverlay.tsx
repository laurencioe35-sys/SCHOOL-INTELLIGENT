type LiveCaptionsOverlayProps = {
  caption: string;
  isActive: boolean;
};

export function LiveCaptionsOverlay({ caption, isActive }: LiveCaptionsOverlayProps) {
  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className={isActive ? "live-captions active" : "live-captions"}
      role="status"
    >
      {caption}
    </div>
  );
}

type RecognizedShapeDescriptionProps = {
  shapeType: string;
  confidence: number;
  isConfirmed: boolean;
};

export function RecognizedShapeDescription({
  shapeType,
  confidence,
  isConfirmed,
}: RecognizedShapeDescriptionProps) {
  const state = isConfirmed ? "confirmada" : "sugerida";
  return (
    <span className="sr-only">
      Figura {shapeType} {state}, confianza {Math.round(confidence * 100)} por ciento.
    </span>
  );
}