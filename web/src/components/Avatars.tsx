import type { ReactNode } from "react";

/** Ilustrações das personas: figuras chapadas, uma por papel, na paleta do site. */

type PersonProps = {
  bg: string;
  skin: string;
  top: string;
  hair?: "short" | "long" | "bun" | "cap";
  hairColor?: string;
  children?: ReactNode;
};

const INK = "#12141A";

function Person({ bg, skin, top, hair = "short", hairColor = INK, children }: PersonProps) {
  return (
    <svg viewBox="0 0 160 160" role="img" aria-hidden="true" className="avatar-svg">
      <rect width="160" height="160" fill={bg} />
      {hair === "long" && <path d="M52 70c-2 30 4 44 14 52h28c10-8 16-22 14-52 0-24-14-36-28-36s-28 12-28 36z" fill={hairColor} />}
      <path d="M18 160c0-31 27-50 62-50s62 19 62 50z" fill={top} />
      <rect x="68" y="90" width="24" height="30" rx="11" fill={skin} />
      <ellipse cx="80" cy="70" rx="26" ry="30" fill={skin} />
      {hair === "short" && <path d="M53 68c-2-22 11-34 27-34s29 12 27 34c-6-9-15-14-27-14s-21 5-27 14z" fill={hairColor} />}
      {hair === "long" && <path d="M54 66c0-18 11-30 26-30s26 12 26 30c-7-8-15-11-26-11s-19 3-26 11z" fill={hairColor} />}
      {hair === "bun" && (
        <>
          <circle cx="80" cy="33" r="12" fill={hairColor} />
          <path d="M54 68c-1-21 11-32 26-32s27 11 26 32c-6-9-15-13-26-13s-20 4-26 13z" fill={hairColor} />
        </>
      )}
      {hair === "cap" && (
        <>
          <path d="M53 62c0-18 11-28 27-28s27 10 27 28z" fill="#FFD21F" />
          <path d="M100 60h26c0 6-6 8-13 8h-13z" fill="#FFD21F" />
        </>
      )}
      <circle cx="70" cy="73" r="2.8" fill={INK} />
      <circle cx="90" cy="73" r="2.8" fill={INK} />
      <path d="M72 85q8 7 16 0" fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round" />
      {children}
    </svg>
  );
}

const AVATARS: Record<string, ReactNode> = {
  // Cliente: boné amarelo e camiseta preta.
  cliente: <Person bg="#FFD21F" skin="#C98F66" top={INK} hair="cap" />,
  // Vendedor: camisa azul com crachá.
  vendedor: (
    <Person bg="#2447F5" skin="#F2C9A5" top="#FFFFFF">
      <rect x="92" y="126" width="22" height="14" rx="3" fill="#2447F5" />
      <path d="M96 131h14M96 135h9" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </Person>
  ),
  // Gerente: blazer escuro e gravata.
  gerente: (
    <Person bg="#E4E6EB" skin="#8D5A3B" top={INK}>
      <path d="M70 112l10 14 10-14z" fill="#fff" />
      <path d="M77 118h6l3 22h-12z" fill="#2447F5" />
    </Person>
  ),
  // RH: cabelo longo e óculos.
  rh: (
    <Person bg="#EAEFFF" skin="#F2C9A5" top="#2447F5" hair="long" hairColor="#5A3A24">
      <g fill="none" stroke={INK} strokeWidth="3">
        <circle cx="70" cy="73" r="8.5" />
        <circle cx="90" cy="73" r="8.5" />
        <path d="M78.5 73h3" />
      </g>
    </Person>
  ),
  // TI: fone de atendimento e capuz.
  ti: (
    <Person bg="#FFD21F" skin="#C98F66" top="#12141A" hairColor="#12141A">
      <path d="M52 70c0-21 12-34 28-34s28 13 28 34" fill="none" stroke={INK} strokeWidth="5" strokeLinecap="round" />
      <rect x="45" y="66" width="11" height="20" rx="5" fill={INK} />
      <rect x="104" y="66" width="11" height="20" rx="5" fill={INK} />
      <path d="M108 86c0 8-8 12-18 12" fill="none" stroke={INK} strokeWidth="3" strokeLinecap="round" />
    </Person>
  ),
  // CEO: coque, terno claro.
  ceo: (
    <Person bg="#2447F5" skin="#8D5A3B" top="#F4F5F7" hair="bun">
      <path d="M62 112l18 20 18-20" fill="none" stroke="#12141A" strokeWidth="3" strokeLinejoin="round" />
    </Person>
  ),
};

export function Avatar({ persona }: { persona: string }) {
  return <>{AVATARS[persona] ?? AVATARS.cliente}</>;
}
