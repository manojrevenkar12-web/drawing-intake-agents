import { useState } from "react";
import type { Dashboard } from "../../app/types";
import { pct } from "../../shared/format";
import { linear, path, ticks } from "../../shared/scale";
import { chart, color, font } from "../../theme/tokens";

export function RoutingChart({ routing }: { routing: Dashboard["routing"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = routing.curve.filter((c) => c.threshold > 0);
  const W = chart.width;
  const { top, right, bottom, left } = chart.pad;
  const x = linear([0, 1], [left, W - right]);
  const yt = ticks(0, 1, chart.ticks);
  const y = linear([0, 1], [chart.height - bottom, top]);
  const yErr = linear([0, Math.max(0.1, ...pts.map((p) => p.error))], [chart.height - bottom, top]);
  const h = hover === null ? null : pts[hover];
  return (
    <div className="figure">
      <h3>Choosing what goes straight to the ERP</h3>
      <div className="legend">
        <span><i className="swatch" style={{ background: color.series.system }} />Share of fields accepted automatically</span>
        <span><i className="swatch" style={{ background: color.series.error }} />Wrong values among them (own scale)</span>
      </div>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${chart.height}`} width="100%" role="img" aria-label="Accepted share and error by confidence threshold">
          {yt.map((t) => (
            <g key={t}>
              <line x1={left} x2={W - right} y1={y(t)} y2={y(t)} stroke={color.grid} />
              <text x={left - chart.valueGap} y={y(t) + chart.baseline} textAnchor="end" fontSize={font.size.xs} fill={color.muted}>{pct(t)}</text>
            </g>
          ))}
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <text key={t} x={x(t)} y={chart.height - bottom + font.size.lg} textAnchor="middle" fontSize={font.size.xs} fill={color.muted}>{t}</text>
          ))}
          <text x={W - right} y={chart.height - chart.baseline} textAnchor="end" fontSize={font.size.xs} fill={color.muted}>confidence threshold</text>
          <line x1={x(routing.threshold)} x2={x(routing.threshold)} y1={top} y2={chart.height - bottom} stroke={color.ink} strokeDasharray="4 3" />
          <text x={x(routing.threshold) + chart.valueGap} y={top + font.size.sm} fontSize={font.size.xs} fill={color.ink}>chosen on dev: {routing.threshold}</text>
          <path d={path(pts.map((p) => [x(p.threshold), y(p.accepted_share)]))} fill="none" stroke={color.series.system} strokeWidth={chart.line} />
          <path d={path(pts.map((p) => [x(p.threshold), yErr(p.error)]))} fill="none" stroke={color.series.error} strokeWidth={chart.line} />
          {pts.map((p, i) => (
            <rect key={p.threshold} x={x(p.threshold) - chart.dot} y={top} width={chart.dot * 2} height={chart.height - top - bottom} fill="transparent"
              tabIndex={0} aria-label={`Threshold ${p.threshold}`} onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)}
              onMouseLeave={() => setHover(null)} onBlur={() => setHover(null)} />
          ))}
        </svg>
        {h && (
          <div className="tooltip" role="tooltip" style={{ left: `${(x(h.threshold) / W) * 100}%`, top: 0 }}>
            <strong>Threshold {h.threshold}</strong>
            <div>{pct(h.accepted_share, 1)} accepted, {pct(h.error, 1)} of them wrong</div>
          </div>
        )}
      </div>
      <p className="caption">
        Development drawings. Values found without their label (by their shape, or from the revision table) carry at
        most 0.6 confidence; the threshold sits just above them, where wrong values among accepted fields stay under
        {" "}{pct(routing.max_error, 1)}. Everything below it, and every failed value check, goes to an engineer.
      </p>
    </div>
  );
}
