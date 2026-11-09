import type { Showcase } from "../../app/types";
import { label } from "../../shared/format";
import { EmptyState } from "../../shared/states";

export function Revisions({ changes }: { changes: Showcase["changes"] }) {
  if (changes.truth.length === 0 && changes.found.length === 0)
    return <EmptyState title="This drawing came without a previous revision.">Nothing to compare.</EmptyState>;
  return (
    <div className="split">
      <div className="figure">
        <h3>What the customer changed</h3>
        <ul className="side">
          {changes.truth.map((c, i) => (
            <li key={i}>{label(c.kind)}: {c.key} {c.before && `${c.before} → `}{c.after}</li>
          ))}
        </ul>
      </div>
      <div className="figure">
        <h3>What the compare reported</h3>
        {changes.found.length === 0 ? (
          <p className="ink2">No differences found.</p>
        ) : (
          <ul className="side">
            {changes.found.map((c, i) => (
              <li key={i}>
                {label(c.kind)}: {c.before || "—"} → {c.after || "—"}
                {!c.certain && <span className="muted"> (flagged: may be a reading error)</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
