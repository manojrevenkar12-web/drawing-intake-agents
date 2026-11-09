import type { SplitResult } from "../../app/types";
import { label, pct } from "../../shared/format";
import { chart, color, font } from "../../theme/tokens";

const ORDER = ["title_block", "parts_list", "revision_table", "notes", "view"];
const SERIES = [
  { id: "detector" as const, name: "Trained segmenter (U-Net)", colour: color.series.system },
  { id: "template" as const, name: "Average sheet template", colour: color.series.baseline },
];

export function RegionChart({ regions, title }: { regions: SplitResult["regions"]; title: string }) {
  const groupH = SERIES.length * (chart.bar + chart.barGap) + chart.groupGap;
  const classes = ORDER.filter((c) => regions.detector[c] || regions.template[c]);
  const width = chart.labelWidth + chart.barArea + chart.valueRoom;
  return (
    <div className="figure">
      <h3>{title}</h3>
      <div className="legend">
        {SERIES.map((s) => (
          <span key={s.id}>
            <i className="swatch" style={{ background: s.colour }} />
            {s.name}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${width} ${classes.length * groupH}`} width="100%" style={{ maxWidth: width }} role="img"
        aria-label="Overlap with the true region, by region">
        {classes.map((cls, g) => (
          <g key={cls} transform={`translate(0 ${g * groupH})`}>
            <text x={0} y={chart.bar + chart.baseline} fontSize={font.size.sm} fill={color.ink}>{label(cls)}</text>
            {SERIES.map((s, i) => {
              const v = regions[s.id][cls]?.mean_iou ?? 0;
              const y = i * (chart.bar + chart.barGap);
              return (
                <g key={s.id}>
                  <rect x={chart.labelWidth} y={y} width={Math.max(1, v * chart.barArea)} height={chart.bar}
                    rx={chart.barRadius} fill={s.colour}><title>{`${s.name}: ${pct(v)}`}</title></rect>
                  <text x={chart.labelWidth + v * chart.barArea + chart.valueGap} y={y + chart.bar - chart.baseline + 1}
                    fontSize={font.size.xs} fill={color.ink2}>{pct(v)}</text>
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <p className="caption">Mean overlap (intersection over union) between the region found and the true one, per sheet.</p>
    </div>
  );
}
