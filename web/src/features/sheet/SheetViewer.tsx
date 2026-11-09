import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import type { SheetDim, Showcase } from "../../app/types";
import { label } from "../../shared/format";
import { color, motion as m, stroke } from "../../theme/tokens";

type View = "received" | "read";
const BASE = `${import.meta.env.BASE_URL}data/`;
// Size of a dimension marker on the sheet, in millimetres per character and its height.
const MM_PER_CHAR = 1.9;
const MARK_H = 4.2;
const IMG_PX_PER_MM = 4; // intrinsic size hint for the sheet images, so the layout does not jump while they load

export const STATUS: Record<SheetDim["status"], { text: string; colour: string; dash?: string }> = {
  right: { text: "Read right", colour: color.read },
  wrong: { text: "Read wrong", colour: color.redline },
  missed: { text: "Missed", colour: color.redline, dash: "1.2 1" },
  extra: { text: "Not a dimension on the drawing", colour: color.review, dash: "1.2 1" },
};

export function markBox(d: SheetDim): [number, number, number, number] {
  const len = Math.max(3, (d.truth ?? d.text).length) * MM_PER_CHAR;
  return d.vertical ? [d.x - MARK_H / 2, d.y - len / 2, MARK_H, len] : [d.x - len / 2, d.y - MARK_H / 2, len, MARK_H];
}

export function SheetViewer({ sheet }: { sheet: Showcase }) {
  const [view, setView] = useState<View>("read");
  const [hover, setHover] = useState<SheetDim | null>(null);
  const reduce = useReducedMotion();
  const [W, H] = sheet.size_mm;
  const counts = sheet.dims.reduce<Record<string, number>>((a, d) => ({ ...a, [d.status]: (a[d.status] ?? 0) + 1 }), {});
  return (
    <figure className="board" aria-label={`Drawing ${sheet.id} as received and as read`}>
      <div className="board-bar">
        <span>
          {sheet.medium === "scan" ? "A scanned paper drawing" : "A CAD PDF"} from {label(sheet.layout)}, a held-out customer
        </span>
        <div className="toggle" role="group" aria-label="Sheet view">
          <button aria-pressed={view === "received"} onClick={() => setView("received")}>
            As received
          </button>
          <button aria-pressed={view === "read"} onClick={() => setView("read")}>
            As read
          </button>
        </div>
      </div>
      <div className="sheet-wrap">
        <img src={`${BASE}${view === "received" ? sheet.received : sheet.registered}`} alt="" width={W * IMG_PX_PER_MM} height={H * IMG_PX_PER_MM} />
        <AnimatePresence>
          {view === "read" && (
            <motion.svg key="overlay" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="What the reader found on the sheet"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: m.fast }}>
              {Object.entries(sheet.regions).flatMap(([cls, boxes]) =>
                boxes.map((b, i) => (
                  <rect key={`${cls}-${i}`} x={b[0]} y={b[1]} width={b[2] - b[0]} height={b[3] - b[1]} fill="none"
                    stroke={color.region[cls as keyof typeof color.region] ?? color.ink2} strokeWidth={0.6}
                    strokeDasharray="3 1.5" />
                )),
              )}
              {sheet.dims.map((d, i) => {
                const [x, y, w, h] = markBox(d);
                const s = STATUS[d.status];
                return (
                  <motion.rect key={i} x={x} y={y} width={w} height={h} rx={0.8} fill={s.colour} fillOpacity={0.12}
                    stroke={s.colour} strokeWidth={stroke.mark * 0.4} strokeDasharray={s.dash}
                    initial={reduce ? false : { opacity: 0, scale: 0.6 }} animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: reduce ? 0 : i * m.stagger * 4, duration: m.base, ease: m.ease }}
                    style={{ transformOrigin: `${d.x}px ${d.y}px`, transformBox: "fill-box" }}
                    tabIndex={0} aria-label={`${d.text || d.truth}: ${s.text}`}
                    onMouseEnter={() => setHover(d)} onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(d)} onBlur={() => setHover(null)} />
                );
              })}
            </motion.svg>
          )}
        </AnimatePresence>
        {hover && view === "read" && (
          <div className="tooltip" role="tooltip" style={{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%` }}>
            <strong>{hover.text || "nothing read"}</strong>
            <div>{STATUS[hover.status].text}{hover.status === "wrong" || hover.status === "missed" ? `; drawing says ${hover.truth}` : ""}</div>
            {hover.limits && <div>Limits {hover.limits}</div>}
          </div>
        )}
      </div>
      <div className="board-bar gap-top-sm">
        <div className="legend">
          {(Object.keys(STATUS) as SheetDim["status"][]).filter((k) => counts[k]).map((k) => (
            <span key={k}>
              <i className="outline" style={{ color: STATUS[k].colour }} />
              {STATUS[k].text} ({counts[k]})
            </span>
          ))}
        </div>
      </div>
    </figure>
  );
}
