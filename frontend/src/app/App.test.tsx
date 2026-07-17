import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

it("renders the Phase 1 shell and primary workflow navigation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        status: "ok",
        service: "Local AI SKU Dimensioner",
        version: "0.1.0",
        database: { status: "ok", revision: "0002_phase1_scans" },
      }),
    }),
  );

  render(<App />);

  expect(
    screen.getByRole("heading", {
      name: "Geometry-first measurement, built for accountable review.",
    }),
  ).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Foundation ready" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Start a new scan" })).toHaveAttribute(
    "href",
    "/scans/new",
  );
  expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
  expect(screen.queryByText(/processing progress/i)).not.toBeInTheDocument();
});

it("preserves the health shell at the direct status route", async () => {
  window.history.replaceState({}, "", "/status");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        status: "ok",
        service: "Local AI SKU Dimensioner",
        version: "0.1.0",
        database: { status: "ok", revision: "0002_phase1_scans" },
      }),
    }),
  );

  render(<App />);

  expect(
    screen.getByRole("heading", {
      name: "Geometry-first measurement, built for accountable review.",
    }),
  ).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Foundation ready" })).toBeVisible();
});

it("renders the new scan page at its direct route", () => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn((file: File) => `blob:${file.name}`),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  window.history.replaceState({}, "", "/scans/new");

  render(<App />);

  expect(screen.getByRole("heading", { name: "Start a new SKU scan" })).toBeVisible();
  expect(screen.getByLabelText("Top view from camera")).toHaveAttribute("capture", "environment");
});
