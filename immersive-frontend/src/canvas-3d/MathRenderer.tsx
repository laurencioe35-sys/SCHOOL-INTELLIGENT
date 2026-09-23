/**
 * Renderiza una fórmula en LaTeX usando KaTeX. Se activa cuando el
 * ai-agents-engine emite un UIComponentSchema con component_type="formula".
 * NOTA: no compilado/ejecutado en este entorno (requiere `katex` instalado
 * y su CSS importado a nivel de la app).
 */
import React, { useEffect, useRef } from "react";
import katex from "katex";

export function MathRenderer({ latex }: { latex: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    try {
      katex.render(latex, ref.current, { throwOnError: false, displayMode: true });
    } catch (err) {
      ref.current.textContent = `Error renderizando fórmula: ${latex}`;
    }
  }, [latex]);

  return <div ref={ref} className="math-renderer" />;
}
