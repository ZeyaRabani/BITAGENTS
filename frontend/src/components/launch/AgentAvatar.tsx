/* Distinct hues per agent (SwarmDojo's "each fighter gets its own color"
 * pattern) instead of four near-identical coral variants -- every agent
 * should read as its own thing at a glance, not interchangeable tiles. */
const PALETTES: [string, string][] = [
  ["#ff6b4a", "#f4a261"], // signal coral/amber (keep one as the "house" option)
  ["#4ad6c0", "#2a9d8f"], // teal
  ["#a78bfa", "#7c3aed"], // violet
  ["#f4a261", "#e9c46a"], // amber/gold
  ["#60a5fa", "#3b82f6"], // blue
  ["#f472b6", "#db2777"], // pink
];

function hashSeed(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return h;
}

/** The same color an agent's avatar renders with, for anything else on the
 * card (sparkline, accents) that should share its identity color. */
export function agentAccentColor(seed: string): string {
  return PALETTES[hashSeed(seed) % PALETTES.length][0];
}

export function AgentAvatar({ seed, size = 44 }: { seed: string; size?: number }) {
  const h = hashSeed(seed);
  const [from, to] = PALETTES[h % PALETTES.length];
  const initials = seed.slice(0, 2).toUpperCase();
  return (
    <div
      className="flex shrink-0 items-center justify-center font-display font-bold text-[#0c0a09]"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: `linear-gradient(135deg, ${from}, ${to})`,
      }}
    >
      {initials}
    </div>
  );
}
