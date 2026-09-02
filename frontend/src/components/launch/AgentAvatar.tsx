const PALETTES: [string, string][] = [
  ["#ff6b4a", "#f4a261"],
  ["#f4a261", "#ff6b4a"],
  ["#e0665a", "#ff8a68"],
  ["#ffb17a", "#ff6b4a"],
];

function hashSeed(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return h;
}

export function AgentAvatar({ seed, size = 44 }: { seed: string; size?: number }) {
  const h = hashSeed(seed);
  const [from, to] = PALETTES[h % PALETTES.length];
  const initials = seed.slice(0, 2).toUpperCase();
  return (
    <div
      className="flex shrink-0 items-center justify-center border border-grid font-display font-bold text-[#0c0a09]"
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
