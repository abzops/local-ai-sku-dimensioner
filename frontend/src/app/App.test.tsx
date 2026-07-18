import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});
it("renders the Phase 2 shell and primary workflow navigation", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({
        status: "ok",
        service: "Local AI SKU Dimensioner",
        version: "0.1.0",
        database: { status: "ok", revision: "0003_phase2_calibration_profiles" },
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
  expect(screen.getByRole("link", { name: "Calibration" })).toHaveAttribute("href", "/calibration");
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
        database: { status: "ok", revision: "0003_phase2_calibration_profiles" },
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

it("renders the calibration page at its direct route", async () => {
  window.history.replaceState({}, "", "/calibration");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:marker") });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.stubGlobal(
    "fetch",
    vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue({
          dictionaries: ["DICT_4X4_50", "DICT_5X5_50", "DICT_6X6_50"],
          marker_id_min: 0,
          marker_id_max: 49,
          border_bits: 1,
          defaults: {
            dictionary: "DICT_4X4_50",
            marker_id: 0,
            marker_size_mm: 100,
            minimum_marker_side_px: 64,
            maximum_perspective_ratio: 3,
            maximum_homography_condition_number: 1000000,
            maximum_marker_edge_residual_px: 2,
            rectified_pixels_per_mm: 4,
          },
        }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: vi.fn().mockResolvedValue({ items: [], total: 0 }) }),
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Calibrate the printed marker" })).toBeVisible();
  expect(screen.getByLabelText("Profile name *")).toBeVisible();
  expect(screen.getByRole("link", { name: "Calibration" })).toHaveAttribute("aria-current", "page");
});
