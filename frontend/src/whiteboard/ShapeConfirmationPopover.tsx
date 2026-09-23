type ShapeCandidate = {
  shapeType: string;
  confidence: number;
  description: string;
};

type ShapeConfirmationPopoverProps = {
  candidates: ShapeCandidate[];
  onAccept: (shapeType: string) => void;
  onKeepFreehand: () => void;
};

export function ShapeConfirmationPopover({
  candidates,
  onAccept,
  onKeepFreehand,
}: ShapeConfirmationPopoverProps) {
  const selected = candidates[0];
  if (!selected) return null;
  const canAccept = selected.confidence >= 0.75;
  return (
    <section aria-label="Confirmar figura reconocida" role="dialog">
      <p>
        Sugerencia: {selected.description} ({Math.round(selected.confidence * 100)}% de confianza)
      </p>
      <button type="button" onClick={() => onAccept(selected.shapeType)} disabled={!canAccept}>
        Convertir
      </button>
      <button type="button" onClick={onKeepFreehand}>
        Mantener trazo
      </button>
    </section>
  );
}
