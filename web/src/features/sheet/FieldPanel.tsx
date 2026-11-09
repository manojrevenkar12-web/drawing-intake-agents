import type { Showcase } from "../../app/types";
import { label } from "../../shared/format";
import { color } from "../../theme/tokens";

export function FieldPanel({ sheet }: { sheet: Showcase }) {
  const d = sheet.decision;
  return (
    <aside className="figure" aria-label="Title block as read">
      <h3>Title block, as read</h3>
      <div className="side">
        {sheet.fields.map((f) => (
          <div className="row" key={f.field}>
            <span className="ink2">{label(f.field)}</span>
            <span style={{ color: f.right ? color.ink : color.redline }}>
              {f.value ?? "not found"}
              {!f.right && <span className="muted"> (drawing: {f.truth})</span>}
            </span>
            <span className="chip" style={{ color: f.routed === "accepted" ? color.ok : color.review }}>
              {f.routed === "accepted" ? "✓ to ERP" : "◐ review"}
            </span>
          </div>
        ))}
      </div>
      <h3 className="gap-top-sm">Can the plant make it?</h3>
      <p>
        <strong>{d.route === "in_house" ? "Yes, in house" : d.route === "with_partner" ? "Yes, with a partner" : "No"}</strong>
        {d.processes.length > 0 && <span className="ink2">: {d.processes.map(label).join(", ")}</span>}
      </p>
      {d.reasons.length > 0 && (
        <ul className="caption">
          {d.reasons.slice(0, 4).map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}
