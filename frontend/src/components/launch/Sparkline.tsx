/** Deterministic, seeded trend line (Virtuals' inline-sparkline pattern) --
 * same shape every render for a given seed, not random noise on refresh. */
function seededPoints(seed: string, n = 9): number[] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const points: number[] = [];
  let v = 0.5;
  for (let i = 0; i < n; i++) {
    h = (h * 1103515245 + 12345) >>> 0;
    const step = ((h % 1000) / 1000 - 0.5) * 0.35;
    v = Math.min(1, Math.max(0.08, v + step));
    points.push(v);
  }
  return points;
}

export function Sparkline({ seed, color = "#ff6b4a" }: { seed: string; color?: string }) {
  const points = seededPoints(seed);
  const w = 100;
  const h = 28;
  const coords = points.map((p, i) => `${(i / (points.length - 1)) * w},${h - p * h}`).join(" ");
  const up = points[points.length - 1] >= points[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-7 w-full" preserveAspectRatio="none">
      <polyline
        points={coords}
        fill="none"
        stroke={up ? color : "#9a8b7a"}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
