import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

it("renders the Phase 0 shell without exposing later workflows", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        status: "ok",
        service: "Local AI SKU Dimensioner",
        version: "0.1.0",
        database: { status: "ok", revision: "0001_phase0" },
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
  expect(screen.queryByRole("button", { name: /upload/i })).not.toBeInTheDocument();
});

it("renders the Phase 0 shell at the direct status route", async () => {
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
        database: { status: "ok", revision: "0001_phase0" },
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
