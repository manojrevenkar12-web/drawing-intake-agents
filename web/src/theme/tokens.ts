// Every colour, size and duration the dashboard uses.
// The page borrows from a drawing checker's desk: a cool grey board, white sheets, the checker's blue for what the
// reader found and the red pen for where it disagrees with the drawing. Chart series use the validated dataviz slots
// (blue for the system, neutral grey for the baseline); status always carries a word as well as a colour.

export const color = {
  page: "#e9ecef",
  surface: "#fbfcfd",
  sheet: "#ffffff",
  ink: "#18212b",
  ink2: "#4a5563",
  muted: "#7d8794",
  grid: "#d9dee4",
  axis: "#b7c0ca",
  border: "rgba(24,33,43,0.12)",
  wash: "rgba(30,90,168,0.07)",
  accent: "#1e5aa8",
  read: "#1e5aa8",
  redline: "#c8372d",
  ok: "#2e7d4f",
  review: "#a96a12",
  series: { system: "#2a78d6", baseline: "#898781", error: "#eb6834" },
  region: {
    title_block: "#1e5aa8",
    parts_list: "#6b4fbb",
    revision_table: "#0f7c86",
    notes: "#a96a12",
    view: "#4a5563",
  },
} as const;

export const font = {
  body: "'Barlow', system-ui, -apple-system, 'Segoe UI', sans-serif",
  display: "'Barlow Condensed', 'Barlow', system-ui, sans-serif",
  // A modular scale (ratio 1.25) from a 16px body.
  size: { xs: 13, sm: 14, md: 16, lg: 20, xl: 25, xxl: 31, xxxl: 39, display: 56 },
  weight: { regular: 400, medium: 500, semibold: 600 },
  leading: { tight: 1.02, snug: 1.25, body: 1.55 },
} as const;

export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64, 20: 80 } as const;

export const radius = { sm: 3, md: 6 } as const;

export const stroke = { hair: 1, mark: 1.5, focus: 2.5 } as const;

export const layout = { maxWidth: 1200, measure: 70, gutter: 24, tooltip: 300 } as const;

export const motion = {
  fast: 0.15,
  base: 0.3,
  draw: 0.9,
  stagger: 0.012,
  ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
} as const;

export const chart = {
  height: 260,
  pad: { top: 20, right: 24, bottom: 40, left: 52 },
  ticks: 5,
  line: 2,
  dot: 4,
  bar: 12,
  barGap: 3,
  groupGap: 20,
  labelWidth: 150,
  barArea: 420,
  valueRoom: 64,
  valueGap: 6,
  baseline: 3,
  barRadius: 2,
  width: 720,
} as const;

export const breakpoint = { narrow: 820 } as const;
