// Small, dependency-free scale helpers for the SVG charts.

export function linear(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (x: number) => r0 + (x - d0) * k;
}

/** Round tick values whose first and last ticks enclose [lo, hi], so they can serve as the axis domain. */
export function ticks(lo: number, hi: number, count: number): number[] {
  if (hi <= lo) return [lo];
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const first = Math.floor(lo / step + 1e-9) * step;
  const last = Math.ceil(hi / step - 1e-9) * step;
  const out: number[] = [];
  for (let v = first; v <= last + step * 1e-9; v += step) out.push(Number(v.toFixed(10)));
  return out;
}

export function fmt(x: number, digits = 2): string {
  if (x === 0) return "0";
  const a = Math.abs(x);
  if (a >= 1000) return `${(x / 1000).toFixed(1)}K`;
  if (a < 0.01) return x.toExponential(1);
  return Number(x.toFixed(digits)).toString();
}

export function path(points: [number, number][]): string {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
}
