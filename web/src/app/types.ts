// The shape of public/data/dashboard.json, written by scripts/report.py from reports/*.json.

export type Box = [number, number, number, number];

export interface DimScore {
  truth: number;
  read: number;
  recall_exact: number;
  precision_exact: number;
  recall_nominal: number;
  limits_right: number;
}

export interface SplitResult {
  drawings: number;
  media: Record<string, number>;
  layouts: string[];
  fields: Record<string, number>;
  dimensions: { all: DimScore } & Partial<Record<"vector" | "scan", DimScore>>;
  parts_list: { cells: number; cell_accuracy: number };
  notes: { precision: number; recall: number; requirements: number };
  revisions: { changes: number; precision: number; recall: number };
  feasibility: { drawings: number; route_agreement: number; true_routes: Record<string, number> };
  onboarding: Record<string, { field_accuracy: number; fields: number }>;
  review: { threshold: number; fields: number; auto_accepted_share: number; wrong_among_auto_accepted: number;
    error_among_auto_accepted: number; minutes_per_drawing_manual_assumed: number;
    minutes_per_drawing_with_desk: number };
  regions: Record<"detector" | "template", Record<string, { mean_iou: number; found_iou50: number }>>;
}

export interface SheetDim {
  text: string;
  truth: string | null;
  x: number;
  y: number;
  vertical: boolean;
  status: "right" | "wrong" | "missed" | "extra";
  limits: string | null;
}

export interface SheetField {
  field: string;
  value: string | null;
  truth: string;
  right: boolean;
  conf: number;
  routed: "accepted" | "review";
}

export interface Showcase {
  id: string;
  layout: string;
  medium: string;
  size_mm: [number, number];
  received: string;
  registered: string;
  regions: Record<string, Box[]>;
  dims: SheetDim[];
  fields: SheetField[];
  decision: { route: string; reasons: string[]; partners: string[]; processes: string[] };
  changes: { found: { kind: string; what: string; before: string; after: string; certain: boolean }[];
    truth: { kind: string; key: string; before: string; after: string }[] };
}

export interface Dashboard {
  tests: { python: number; web: number };
  dev: SplitResult;
  heldout: SplitResult | null;
  routing: { threshold: number; max_error: number; curve: { threshold: number; accepted_share: number; error: number }[] };
  regions_loo: Record<string, Record<string, number>>;
  showcase: Showcase;
}
