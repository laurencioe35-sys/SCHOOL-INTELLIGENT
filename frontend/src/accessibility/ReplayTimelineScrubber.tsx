type ReplayEvent = {
  event_id: string;
  event_type: string;
  t_offset_ms: number;
};

type ReplayTimelineScrubberProps = {
  events: ReplayEvent[];
  positionMs: number;
  onSeek: (positionMs: number) => void;
};

export function ReplayTimelineScrubber({ events, positionMs, onSeek }: ReplayTimelineScrubberProps) {
  const durationMs = Math.max(events.at(-1)?.t_offset_ms ?? 0, 1);
  return (
    <section aria-label="Línea temporal de repaso de clase">
      <label htmlFor="replay-position">Posición de repaso: {positionMs} ms</label>
      <input
        id="replay-position"
        type="range"
        min="0"
        max={durationMs}
        value={Math.min(positionMs, durationMs)}
        onChange={(event) => onSeek(Number(event.target.value))}
      />
      <ol aria-label="Eventos de la clase">
        {events.map((event) => (
          <li key={event.event_id}>
            {event.event_type} · {event.t_offset_ms} ms
          </li>
        ))}
      </ol>
    </section>
  );
}