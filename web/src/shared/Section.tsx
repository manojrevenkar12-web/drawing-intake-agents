import type { ReactNode } from "react";

export function Section({ id, title, lead, children }: { id: string; title: string; lead: ReactNode; children: ReactNode }) {
  return (
    <section className="section" id={id} aria-label={title}>
      <header>
        <h2>{title}</h2>
        <p>{lead}</p>
      </header>
      {children}
    </section>
  );
}
