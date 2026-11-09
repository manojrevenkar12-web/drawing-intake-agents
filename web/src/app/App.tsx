import { FieldPanel } from "../features/sheet/FieldPanel";
import { SheetViewer } from "../features/sheet/SheetViewer";
import { OnboardingChart } from "../features/onboarding/OnboardingChart";
import { RegionChart } from "../features/regions/RegionChart";
import { ResultsTable } from "../features/results/ResultsTable";
import { Revisions } from "../features/revisions/Revisions";
import { RoutingChart } from "../features/routing/RoutingChart";
import { int, pct } from "../shared/format";
import { Section } from "../shared/Section";
import { ErrorState, Skeleton } from "../shared/states";
import { space } from "../theme/tokens";
import type { Dashboard } from "./types";
import { useJson } from "./useData";

const REPO = "https://github.com/manojrevenkar12-web/drawing-intake-agents";

function Hero({ d }: { d: Dashboard }) {
  const r = d.heldout ?? d.dev;
  const scope = d.heldout ? "held-out customers" : "development customers";
  return (
    <>
      <div className="hero-head">
        <h1>Every customer draws differently. The desk reads them all, and says which values it is not sure of.</h1>
        <p className="lead">
          Engineering drawings from rail, machinery and lighting customers, as CAD PDFs or scanned paper, read into
          title-block data, dimensions with their ISO limits, parts lists and notes; compared with the previous
          revision, checked against what the plant can make, and exported to a legacy ERP from approved values only.
        </p>
      </div>
      <div className="hero-grid">
        <SheetViewer sheet={d.showcase} />
        <FieldPanel sheet={d.showcase} />
      </div>
      <dl className="facts">
        <div>
          <dt>{pct(r.fields.all ?? 0, 1)}</dt>
          <dd>of title-block fields read right on the {scope}, scans included.</dd>
        </div>
        <div>
          <dt>{pct(r.dimensions.all.recall_exact, 1)}</dt>
          <dd>of dimensions read exactly, with value, tolerance and count.</dd>
        </div>
        <div>
          <dt>{r.review.wrong_among_auto_accepted} of {int(Math.round(r.review.auto_accepted_share * r.review.fields))}</dt>
          <dd>fields sent straight to the ERP were wrong; the rest went to an engineer.</dd>
        </div>
        <div>
          <dt>{pct(r.onboarding["0"]?.field_accuracy ?? 0)} → {pct(r.onboarding["3"]?.field_accuracy ?? 0)}</dt>
          <dd>title-block accuracy for a new customer, before and after three of their drawings.</dd>
        </div>
      </dl>
    </>
  );
}

function Report({ d }: { d: Dashboard }) {
  const h = d.heldout ?? d.dev;
  return (
    <>
      <Hero d={d} />
      <Section id="results" title="Development and held-out customers"
        lead="Every number is a comparison with what the simulated customer actually drew. Nothing on the held-out side was tuned.">
        <ResultsTable dev={d.dev} heldout={d.heldout} />
      </Section>
      <Section id="regions" title="Finding the parts of a sheet"
        lead="A small U-Net, trained on the development layouts only, finds title block, parts list, revision table, notes and views on sheets it has never seen. The baseline assumes every sheet looks like the average one.">
        <div className="split">
          <RegionChart regions={h.regions} title={d.heldout ? "Held-out customers" : "Development customers"} />
          <OnboardingChart onboarding={h.onboarding} />
        </div>
      </Section>
      <Section id="routing" title="What reaches the ERP"
        lead="Each field carries a confidence from its label match, its value check, the OCR and agreement with the revision table. Only fields above the threshold go through without a person.">
        <RoutingChart routing={d.routing} />
      </Section>
      <Section id="revisions" title="Comparing revisions"
        lead="The two sheets are aligned on dimensions that read the same, then paired by position and kind; what is left over or altered is a change.">
        <Revisions changes={d.showcase.changes} />
      </Section>
      <section className="limits" aria-label="Limits">
        <h3>Limits</h3>
        <ul>
          <li>The drawings are generated: parametric parts drawn in eight invented customer layouts, some printed and scanned with skew, blur, noise and stamps. Real drawings have more views, sections, GD&amp;T frames and handwriting; none of those are read here.</li>
          <li>Tolerances follow ISO 286-1 (H, f, g, h, js classes up to 500 mm) and ISO 2768-1 (f, m, c). Anything else is reported as not resolvable rather than guessed.</li>
          <li>The note reader in the numbers is rule-based. An LLM reader exists, behind a validator that drops requirements whose quoted text is not in the notes; it is tested with recorded answers, not benchmarked.</li>
          <li>Minutes saved depend on assumptions in config/dia.toml (manual keying time per drawing, review time per field), stated as assumptions.</li>
        </ul>
        <p>
          {d.tests.python} Python and {d.tests.web} web tests. Source: <a href={REPO}>{REPO.replace("https://", "")}</a>
        </p>
      </section>
    </>
  );
}

export function App() {
  const load = useJson<Dashboard>("dashboard.json");
  return (
    <main className="page">
      <div className="top">
        <span>drawing-intake-agents</span>
        <nav aria-label="Sections">
          <a href="#results">Results</a>
          <a href="#regions">Sheet regions</a>
          <a href="#routing">Routing</a>
          <a href="#revisions">Revisions</a>
        </nav>
      </div>
      {load.state === "loading" && <Skeleton height={space[20] * 6} lines={4} label="Loading the report" />}
      {load.state === "error" && <ErrorState what="The report" message={load.message} onRetry={load.retry} />}
      {load.state === "ready" && <Report d={load.data} />}
    </main>
  );
}
