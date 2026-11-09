import type { SplitResult } from "../../app/types";
import { pct } from "../../shared/format";

type Row = [string, (r: SplitResult) => string, boolean?];

const ROWS: Row[] = [
  ["Title-block fields read right", (r) => pct(r.fields.all ?? 0, 1), true],
  ["… on CAD PDFs", (r) => pct(r.fields["medium:vector"] ?? 0, 1)],
  ["… on scans", (r) => pct(r.fields["medium:scan"] ?? 0, 1)],
  ["Dimensions read exactly (value, tolerance, count)", (r) => pct(r.dimensions.all.recall_exact, 1), true],
  ["… on CAD PDFs", (r) => pct(r.dimensions.vector?.recall_exact ?? 0, 1)],
  ["… on scans", (r) => pct(r.dimensions.scan?.recall_exact ?? 0, 1)],
  ["Read dimensions that are right (precision)", (r) => pct(r.dimensions.all.precision_exact, 1)],
  ["Limits of size right (ISO 286 / ISO 2768)", (r) => pct(r.dimensions.all.limits_right, 1)],
  ["Parts-list cells right", (r) => pct(r.parts_list.cell_accuracy, 1)],
  ["Note requirements found (recall / precision)", (r) => `${pct(r.notes.recall)} / ${pct(r.notes.precision)}`],
  ["Revision changes found (recall / precision)", (r) => `${pct(r.revisions.recall)} / ${pct(r.revisions.precision)}`],
  ["Make-or-partner decision same as from the drawing", (r) => pct(r.feasibility.route_agreement, 1), true],
  ["Fields sent straight to the ERP", (r) => pct(r.review.auto_accepted_share, 1)],
  ["Wrong values among those", (r) => `${r.review.wrong_among_auto_accepted} (${pct(r.review.error_among_auto_accepted, 1)})`, true],
];

export function ResultsTable({ dev, heldout }: { dev: SplitResult; heldout: SplitResult | null }) {
  return (
    <div className="figure scroll-x">
      <table>
        <thead>
          <tr>
            <th scope="col">Measure</th>
            <th scope="col" className="num">Development customers ({dev.drawings} drawings)</th>
            <th scope="col" className="num">Held-out customers ({heldout ? heldout.drawings : "not run"})</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([name, f, em]) => (
            <tr key={name} className={em ? "em" : undefined}>
              <th scope="row">{name}</th>
              <td className="num">{f(dev)}</td>
              <td className="num">{heldout ? f(heldout) : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="caption">
        Development customers are the five layouts the reader was built on. The held-out customers' layouts (other
        labels, abbreviations, another sheet size) were written and pinned before the reader first saw them, and run
        once.
      </p>
    </div>
  );
}
