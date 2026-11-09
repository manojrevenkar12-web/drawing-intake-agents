import type { ReactNode } from "react";
import { space } from "../theme/tokens";

export function Skeleton({ height, lines = 0, label }: { height: number; lines?: number; label: string }) {
  return (
    <div role="status" aria-label={label} aria-busy="true">
      <div className="skeleton" style={{ height }} />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: space[3], marginTop: space[3], width: `${80 - i * 15}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ what, message, onRetry }: { what: string; message: string; onRetry: () => void }) {
  return (
    <div className="state" role="alert">
      <strong>{what} could not be loaded.</strong>
      <span className="ink2">{message}. The file is written by scripts/report.py; check that it exists, then try again.</span>
      <button className="btn" onClick={onRetry}>
        Load again
      </button>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      <span className="ink2">{children}</span>
    </div>
  );
}
