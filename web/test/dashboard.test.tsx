import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/app/App";
import type { Dashboard, SheetDim } from "../src/app/types";
import { markBox, SheetViewer } from "../src/features/sheet/SheetViewer";
import { Revisions } from "../src/features/revisions/Revisions";

const data = JSON.parse(readFileSync(resolve(__dirname, "../public/data/dashboard.json"), "utf8")) as Dashboard;

function serve(fail = { on: false }) {
  return vi.fn(async () => (fail.on ? new Response("no", { status: 503 }) : new Response(JSON.stringify(data), { status: 200 })));
}

describe("dashboard", () => {
  it("shows a skeleton, then the report with the held-out results", async () => {
    vi.stubGlobal("fetch", serve());
    render(<App />);
    expect(screen.getByRole("status", { name: "Loading the report" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Every customer draws differently");
    for (const name of ["Development and held-out customers", "Finding the parts of a sheet", "What reaches the ERP", "Comparing revisions"]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
    vi.unstubAllGlobals();
  });

  it("explains a failed load and loads again on retry", async () => {
    const fail = { on: true };
    vi.stubGlobal("fetch", serve(fail));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The report could not be loaded");
    fail.on = false;
    fireEvent.click(screen.getByRole("button", { name: "Load again" }));
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("switches between the sheet as received and as read, and explains a dimension on hover", async () => {
    render(<SheetViewer sheet={data.showcase} />);
    expect(screen.getByRole("img", { name: "What the reader found on the sheet" })).toBeInTheDocument();
    const first = data.showcase.dims.find((d) => d.status === "right")!;
    fireEvent.mouseEnter(screen.getByLabelText(`${first.text}: Read right`));
    expect(screen.getByRole("tooltip")).toHaveTextContent(first.text);
    fireEvent.click(screen.getByRole("button", { name: "As received" }));
    await waitFor(() => expect(screen.queryByRole("img", { name: "What the reader found on the sheet" })).not.toBeInTheDocument());
  });

  it("draws vertical markers tall and horizontal markers wide", () => {
    const d: SheetDim = { text: "120", truth: "120", x: 50, y: 50, vertical: true, status: "right", limits: null };
    const [, , w, h] = markBox(d);
    expect(h).toBeGreaterThan(w);
    const [, , w2, h2] = markBox({ ...d, vertical: false });
    expect(w2).toBeGreaterThan(h2);
  });

  it("says so when a drawing came without a previous revision", () => {
    render(<Revisions changes={{ found: [], truth: [] }} />);
    expect(screen.getByText("This drawing came without a previous revision.")).toBeInTheDocument();
  });
});
