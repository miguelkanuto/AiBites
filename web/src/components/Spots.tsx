/** Ilustração de apoio da faixa de segurança: escudo gordo, cadeado e uma chave de dados, chapados. */
export function ShieldSpot() {
  return (
    <svg viewBox="0 0 320 300" role="img" aria-label="Escudo com um cadeado e três barras de dados" className="spot">
      <rect x="20" y="30" width="280" height="250" rx="28" fill="#1B2030" />
      <path d="M160 52l96 36v72c0 52-38 92-96 112-58-20-96-60-96-112V88l96-36z" fill="#8CA2FF" />
      <path d="M160 52l96 36v72c0 52-38 92-96 112V52z" fill="#6C86F5" />
      <rect x="118" y="132" width="84" height="66" rx="14" fill="#12141A" />
      <path d="M134 132v-18a26 26 0 0 1 52 0v18" fill="none" stroke="#12141A" strokeWidth="14" strokeLinecap="round" />
      <circle cx="160" cy="161" r="9" fill="#FFD21F" />
      <rect x="156" y="164" width="8" height="18" rx="4" fill="#FFD21F" />
      <g fill="#FFD21F">
        <rect x="236" y="34" width="62" height="12" rx="6" />
        <rect x="256" y="54" width="42" height="12" rx="6" />
      </g>
    </svg>
  );
}
