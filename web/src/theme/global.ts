import { breakpoint, color, font, layout, radius, space } from "./tokens";

// The stylesheet is generated from the tokens, so no value in it is typed twice.
export const globalCss = `
:root { color-scheme: light; }
* { box-sizing: border-box; }
html, body { margin: 0; background: ${color.page}; color: ${color.ink}; }
body { font-family: ${font.body}; font-size: ${font.size.md}px; line-height: ${font.leading.body}; -webkit-font-smoothing: antialiased; }
h1, h2, h3 { margin: 0; font-family: ${font.display}; font-weight: ${font.weight.semibold}; line-height: ${font.leading.snug}; }
h2 { font-size: ${font.size.xxl}px; }
h3 { font-size: ${font.size.lg}px; font-weight: ${font.weight.medium}; }
p { margin: 0; max-width: ${layout.measure}ch; }
a { color: ${color.accent}; text-underline-offset: 3px; }
:focus-visible { outline: 2px solid ${color.accent}; outline-offset: 2px; border-radius: ${radius.sm}px; }
button { font: inherit; color: inherit; }
figure { margin: 0; }
.page { max-width: ${layout.maxWidth}px; margin: 0 auto; padding: ${space[8]}px ${layout.gutter}px ${space[20]}px; }
.top { display: flex; justify-content: space-between; gap: ${space[4]}px; flex-wrap: wrap; font-size: ${font.size.sm}px;
  color: ${color.ink2}; padding-bottom: ${space[8]}px; }
.top nav { display: flex; gap: ${space[5]}px; flex-wrap: wrap; }
.hero-head { display: grid; grid-template-columns: minmax(0, 7fr) minmax(0, 5fr); gap: ${space[10]}px; align-items: end;
  margin-bottom: ${space[6]}px; }
.hero-head h1 { font-size: ${font.size.display}px; line-height: ${font.leading.tight}; letter-spacing: -0.005em; }
.lead { color: ${color.ink2}; font-size: ${font.size.lg}px; }
.facts { margin: ${space[8]}px 0 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: ${space[6]}px; }
.facts div { border-top: 2px solid ${color.ink}; padding-top: ${space[3]}px; }
.facts dt { font-family: ${font.display}; font-size: ${font.size.xxxl}px; font-weight: ${font.weight.semibold};
  line-height: ${font.leading.tight}; font-variant-numeric: tabular-nums; }
.facts dd { margin: ${space[2]}px 0 0; color: ${color.ink2}; font-size: ${font.size.sm}px; }
.board { background: ${color.surface}; border: 1px solid ${color.border}; border-radius: ${radius.md}px; padding: ${space[4]}px; }
.board-bar { display: flex; justify-content: space-between; align-items: center; gap: ${space[4]}px; flex-wrap: wrap;
  margin-bottom: ${space[3]}px; font-size: ${font.size.sm}px; color: ${color.ink2}; }
.sheet-wrap { position: relative; background: ${color.sheet}; border: 1px solid ${color.grid}; }
.sheet-wrap img { display: block; width: 100%; height: auto; }
.sheet-wrap svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.toggle { display: inline-flex; border: 1px solid ${color.axis}; border-radius: ${radius.sm}px; overflow: hidden; }
.toggle button { border: 0; background: transparent; padding: ${space[1]}px ${space[3]}px; cursor: pointer; font-size: ${font.size.sm}px; }
.toggle button[aria-pressed="true"] { background: ${color.ink}; color: ${color.surface}; }
.legend { display: flex; gap: ${space[4]}px; flex-wrap: wrap; font-size: ${font.size.sm}px; color: ${color.ink2}; }
.legend span { display: inline-flex; align-items: center; gap: ${space[2]}px; }
.swatch { width: ${space[3]}px; height: ${space[3]}px; border-radius: 2px; display: inline-block; }
.outline { width: ${space[3]}px; height: ${space[3]}px; border: 2px solid currentColor; display: inline-block; }
.section { margin-top: ${space[20]}px; }
.section > header { margin-bottom: ${space[6]}px; display: grid; gap: ${space[2]}px; }
.section > header p { color: ${color.ink2}; }
.split { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: ${space[8]}px; align-items: start; }
.gap-top { margin-top: ${space[8]}px; }
.gap-top-sm { margin-top: ${space[4]}px; }
.figure { background: ${color.surface}; border: 1px solid ${color.border}; border-radius: ${radius.md}px; padding: ${space[5]}px; }
.figure h3 { margin-bottom: ${space[2]}px; }
.caption { color: ${color.ink2}; font-size: ${font.size.sm}px; margin-top: ${space[3]}px; }
table { border-collapse: collapse; width: 100%; font-size: ${font.size.sm}px; }
th { text-align: left; font-weight: ${font.weight.medium}; color: ${color.ink2}; padding: ${space[2]}px ${space[3]}px; border-bottom: 1px solid ${color.axis}; }
td { padding: ${space[2]}px ${space[3]}px; border-bottom: 1px solid ${color.grid}; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.em td { font-weight: ${font.weight.semibold}; }
.chip { display: inline-flex; align-items: center; gap: ${space[1]}px; font-size: ${font.size.xs}px; font-weight: ${font.weight.medium}; white-space: nowrap; }
.muted { color: ${color.muted}; }
.ink2 { color: ${color.ink2}; }
.side { display: grid; gap: ${space[2]}px; font-size: ${font.size.sm}px; }
.side .row { display: grid; grid-template-columns: 9.5em 1fr auto; gap: ${space[2]}px; align-items: baseline;
  border-bottom: 1px solid ${color.grid}; padding: ${space[1]}px 0; }
.tooltip { position: absolute; pointer-events: none; background: ${color.surface}; border: 1px solid ${color.border};
  border-radius: ${radius.sm}px; padding: ${space[2]}px ${space[3]}px; font-size: ${font.size.xs}px; box-shadow: 0 2px 8px ${color.border};
  z-index: 3; max-width: ${layout.tooltip}px; }
.tooltip strong { font-size: ${font.size.sm}px; }
.chart-wrap { position: relative; }
.state { padding: ${space[8]}px; border: 1px dashed ${color.axis}; border-radius: ${radius.md}px; display: grid; gap: ${space[3]}px; justify-items: start; }
.btn { border: 1px solid ${color.accent}; color: ${color.accent}; background: transparent; border-radius: ${radius.sm}px;
  padding: ${space[2]}px ${space[4]}px; cursor: pointer; }
.btn:hover { background: ${color.wash}; }
.skeleton { background: linear-gradient(90deg, ${color.grid}, ${color.surface}, ${color.grid}); background-size: 200% 100%;
  border-radius: ${radius.sm}px; animation: shimmer 1.4s ease-in-out infinite; }
@keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .skeleton { animation: none; } }
.limits { margin-top: ${space[20]}px; border-top: 1px solid ${color.axis}; padding-top: ${space[6]}px; color: ${color.ink2};
  font-size: ${font.size.sm}px; display: grid; gap: ${space[3]}px; }
.limits ul { margin: 0; padding-left: ${space[5]}px; display: grid; gap: ${space[2]}px; max-width: 90ch; }
.scroll-x { overflow-x: auto; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.hero-grid { display: grid; grid-template-columns: minmax(0, 8fr) minmax(0, 4fr); gap: ${space[6]}px; align-items: start; }
@media (max-width: ${breakpoint.narrow}px) {
  .hero-head, .split, .hero-grid { grid-template-columns: 1fr; }
  .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero-head h1 { font-size: ${font.size.xxxl}px; }
  .page { padding-top: ${space[5]}px; }
}
`;
