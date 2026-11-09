export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;
export const int = (x: number) => x.toLocaleString("en-GB");
export const label = (key: string) => key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
