import type { SplitResult } from "../../app/types";
import { pct } from "../../shared/format";
import { chart, color, font } from "../../theme/tokens";

export function OnboardingChart({ onboarding }: { onboarding: SplitResult["onboarding"] }) {
  const ks = Object.keys(onboarding).sort((a, b) => Number(a) - Number(b));
  const width = chart.labelWidth + chart.barArea + chart.valueRoom;
  const rowH = chart.bar * 2 + chart.barGap * 4;
  return (
    <div className="figure">
      <h3>A new customer's title block, after a few of their drawings</h3>
      <svg viewBox={`0 0 ${width} ${ks.length * rowH}`} width="100%" style={{ maxWidth: width }} role="img"
        aria-label="Title-block accuracy by number of example drawings">
        {ks.map((k, i) => {
          const v = onboarding[k]!.field_accuracy;
          const y = i * rowH;
          return (
            <g key={k}>
              <text x={0} y={y + chart.bar * 1.5} fontSize={font.size.sm} fill={color.ink}>
                {k === "0" ? "No examples" : `${k} example${k === "1" ? "" : "s"}`}
              </text>
              <rect x={chart.labelWidth} y={y} width={Math.max(1, v * chart.barArea)} height={chart.bar * 2}
                rx={chart.barRadius} fill={k === "0" ? color.series.baseline : color.series.system} />
              <text x={chart.labelWidth + v * chart.barArea + chart.valueGap} y={y + chart.bar * 1.5}
                fontSize={font.size.sm} fill={color.ink}>{pct(v, 1)}</text>
            </g>
          );
        })}
      </svg>
      <p className="caption">
        Held-out customers only. A profile learns each customer's own labels ("Zchn.-Nr.", "Iss", "Matl") from the
        example drawings and their known values; accuracy is measured on that customer's other drawings.
      </p>
    </div>
  );
}
