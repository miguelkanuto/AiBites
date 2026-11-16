import { useId } from "react";

/**
 * Marca da AiBites: um chip com uma mordida (os "bites") e três barras de dados.
 * A mordida é um recorte de verdade (máscara), então funciona sobre qualquer fundo.
 */
export function LogoMark({ size = 32, body = "var(--cobalt)", bars = "#fff", pins = "var(--ink)" }: { size?: number; body?: string; bars?: string; pins?: string }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <defs>
        <mask id={id}>
          <rect width="40" height="40" fill="#fff" />
          <circle cx="31.5" cy="8.5" r="6.2" fill="#000" />
        </mask>
      </defs>
      <g stroke={pins} strokeWidth="2.6" strokeLinecap="round">
        <path d="M3.5 15h4M3.5 21h4M3.5 27h4M32.5 21h4M32.5 27h4M15 32.5v4M21 32.5v4M27 32.5v4" />
      </g>
      <rect x="7.5" y="7.5" width="25" height="25" rx="7.5" fill={body} mask={`url(#${id})`} />
      <g fill={bars}>
        <rect x="13" y="14.5" width="11" height="3.2" rx="1.6" />
        <rect x="13" y="20.4" width="15" height="3.2" rx="1.6" />
        <rect x="13" y="26.3" width="8" height="3.2" rx="1.6" />
      </g>
    </svg>
  );
}

export function Logo({ size = 32, onDark = false }: { size?: number; onDark?: boolean }) {
  return (
    <span className="logo" style={{ fontSize: size * 0.78 }}>
      <LogoMark size={size} body={onDark ? "#8CA2FF" : "var(--cobalt)"} bars={onDark ? "#12141A" : "#fff"} pins={onDark ? "#fff" : "var(--ink)"} />
      <span className="logo-word">
        <span className="logo-ai">ai</span>
        <span>bites</span>
      </span>
    </span>
  );
}
