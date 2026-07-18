import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listCalibrationProfiles } from "../api/calibration";
import {
  getMeasurementOptions,
  getPendingMeasurementRequest,
  listMeasurementAttempts,
  MeasurementApiRequestError,
  processMeasurement,
} from "../api/measurements";
import { getScan } from "../api/scans";
import {
  measurementOptionsFixture,
  profileId,
  requestId,
  succeededSummaryFixture,
} from "../test/measurementFixtures";
import type { ScanDetailResponse } from "../types/scans";
import { ScanDetailPage } from "./ScanDetailPage";

vi.mock("../api/scans", async () => {
  const actual = await vi.importActual<typeof import("../api/scans")>("../api/scans");
  return { ...actual, getScan: vi.fn() };
});
vi.mock("../api/calibration", async () => {
  const actual = await vi.importActual<typeof import("../api/calibration")>("../api/calibration");
  return { ...actual, listCalibrationProfiles: vi.fn() };
});
vi.mock("../api/measurements", async () => {
  const actual = await vi.importActual<typeof import("../api/measurements")>("../api/measurements");
  return {
    ...actual,
    getMeasurementOptions: vi.fn(),
    listMeasurementAttempts: vi.fn(),
    processMeasurement: vi.fn(),
  };
});

const readyScan: ScanDetailResponse = {
  id: "scan-1",
  sku: "SKU-READY",
  barcode: null,
  product_name: "Rigid box",
  status: "ready_for_processing",
  missing_required_views: [],
  created_at: "2026-07-18T10:00:00Z",
  updated_at: "2026-07-18T10:00:00Z",
  images: [],
};

const pendingRequest = {
  request_id: requestId,
  expected_calibration_profile_id: profileId,
  expected_capture_setup_id: "rig-local-1",
  capture_contract_acknowledged: true,
  reprocess_of_measurement_id: null,
} as const;

function persistPendingRequest() {
  sessionStorage.setItem(
    "phase3-measurement-request:scan-1",
    JSON.stringify(pendingRequest),
  );
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/scans/scan-1"]}>
        <Routes><Route path="/scans/:scanId" element={<ScanDetailPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getScan).mockReset();
  vi.mocked(getMeasurementOptions).mockReset();
  vi.mocked(listCalibrationProfiles).mockReset();
  vi.mocked(listMeasurementAttempts).mockReset();
  vi.mocked(processMeasurement).mockReset();
  sessionStorage.clear();
  vi.mocked(getMeasurementOptions).mockResolvedValue(measurementOptionsFixture);
  vi.mocked(listCalibrationProfiles).mockResolvedValue({
    items: [
      {
        id: profileId,
        name: "Qualified marker",
        dictionary: "DICT_4X4_50",
        marker_id: 0,
        marker_size_mm: 100,
        border_bits: 1,
        minimum_marker_side_px: 64,
        maximum_perspective_ratio: 3,
        maximum_homography_condition_number: 1_000_000,
        maximum_marker_edge_residual_px: 2,
        rectified_pixels_per_mm: 4,
        is_active: true,
        created_at: "2026-07-18T10:00:00Z",
        activated_at: "2026-07-18T10:00:00Z",
      },
    ],
    total: 1,
  });
  vi.mocked(listMeasurementAttempts).mockResolvedValue({
    items: [],
    total: 0,
    offset: 0,
    limit: 50,
  });
});

describe("ScanDetailPage", () => {
  it("renders read-only image metadata without exposing storage paths", async () => {
    const scan: ScanDetailResponse = {
      id: "scan-1",
      sku: "SKU-1",
      barcode: null,
      product_name: "Storage box",
      status: "images_uploaded",
      missing_required_views: ["front", "side"],
      created_at: "2026-07-17T10:00:00Z",
      updated_at: "2026-07-17T10:00:00Z",
      images: [
        {
          id: "image-1",
          view_type: "top",
          media_type: "image/jpeg",
          size_bytes: 2_097_152,
          width_px: 1600,
          height_px: 1200,
          created_at: "2026-07-17T10:00:00Z",
        },
      ],
    };
    vi.mocked(getScan).mockResolvedValue(scan);
    renderPage();

    expect(await screen.findByRole("heading", { name: "SKU-1" })).toBeVisible();
    expect(screen.getByText("1600 x 1200px")).toBeVisible();
    expect(screen.getByText("2.0 MB")).toBeVisible();
    expect(screen.getByText(/upload valid top, front, and side images/i)).toBeVisible();
    expect(screen.getByText(/not certified metrology/i)).toBeVisible();
    expect(document.body).not.toHaveTextContent(/localappdata|[a-z]:\\|\\scans\\/i);
  });

  it("requires explicit confirmation before starting a qualified measurement", async () => {
    vi.mocked(getScan).mockResolvedValue(readyScan);
    renderPage();

    const measureButton = await screen.findByRole("button", { name: "Measure scan" });
    expect(measureButton).toBeEnabled();
    fireEvent.click(measureButton);

    const dialog = screen.getByRole("dialog", { name: "Confirm deterministic measurement" });
    expect(dialog).toBeVisible();
    expect(within(dialog).getByText(/not certified metrology/i)).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Start measurement" })).toBeDisabled();
  });

  it("keeps processing disabled for an unqualified capture setup", async () => {
    vi.mocked(getMeasurementOptions).mockResolvedValue({
      ...measurementOptionsFixture,
      capture_setup: {
        ...measurementOptionsFixture.capture_setup,
        qualified: false,
        processing_enabled: false,
      },
    });
    vi.mocked(getScan).mockResolvedValue({
      id: "scan-1",
      sku: "SKU-READY",
      barcode: null,
      product_name: null,
      status: "ready_for_processing",
      missing_required_views: [],
      created_at: "2026-07-18T10:00:00Z",
      updated_at: "2026-07-18T10:00:00Z",
      images: [],
    });
    renderPage();

    expect(await screen.findByRole("button", { name: "Measure scan" })).toBeDisabled();
    expect(screen.getByText(/disabled until an operator explicitly configures/i)).toBeVisible();
  });

  it("renders a safe unavailable state", async () => {
    vi.mocked(getScan).mockRejectedValue(new Error("C:\\private\\scan.db"));
    renderPage();

    expect(await screen.findByRole("heading", { name: "Scan unavailable" })).toBeVisible();
    expect(screen.getByText("The local service could not be reached.")).toBeVisible();
    expect(document.body).not.toHaveTextContent("C:\\private");
  });

  it("keeps an uncertain request available outside the closed dialog and retries its UUID", async () => {
    vi.mocked(getScan).mockResolvedValue(readyScan);
    vi.mocked(processMeasurement).mockRejectedValue(new MeasurementApiRequestError(
      503,
      {
        code: "DATABASE_UNAVAILABLE",
        message: "The local database is unavailable.",
        recoverable: true,
        suggested_action: "Retry the same request or refresh history.",
      },
      true,
    ));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Measure scan" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start measurement" }));
    const dialog = screen.getByRole("dialog", { name: "Confirm deterministic measurement" });
    expect(await within(dialog).findByRole("button", { name: "Retry same request" })).toBeVisible();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(await screen.findByRole("heading", {
      name: "Measurement outcome needs confirmation",
    })).toBeVisible();
    const saved = getPendingMeasurementRequest("scan-1");
    expect(saved).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Retry same request" }));
    await waitFor(() => expect(processMeasurement).toHaveBeenCalledTimes(2));

    const initialRequest = vi.mocked(processMeasurement).mock.calls[0]?.[1];
    const retryRequest = vi.mocked(processMeasurement).mock.calls[1]?.[1];
    expect(retryRequest).toEqual(initialRequest);
    expect(retryRequest?.request_id).toBe(saved?.request_id);
  });

  it("clears a saved request when refreshed history contains the matching UUID", async () => {
    vi.mocked(getScan).mockResolvedValue(readyScan);
    persistPendingRequest();
    vi.mocked(listMeasurementAttempts)
      .mockResolvedValueOnce({ items: [], total: 0, offset: 0, limit: 50 })
      .mockResolvedValueOnce({
        items: [{ ...succeededSummaryFixture, request_id: requestId }],
        total: 1,
        offset: 0,
        limit: 50,
      });
    renderPage();

    expect(await screen.findByRole("heading", {
      name: "Measurement outcome needs confirmation",
    })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Refresh attempt history" }));

    await waitFor(() => {
      expect(getPendingMeasurementRequest("scan-1")).toBeNull();
      expect(screen.queryByRole("heading", {
        name: "Measurement outcome needs confirmation",
      })).not.toBeInTheDocument();
    });
  });

  it("clears a saved request only when the operator abandons it", async () => {
    vi.mocked(getScan).mockResolvedValue(readyScan);
    persistPendingRequest();
    renderPage();

    expect(await screen.findByRole("heading", {
      name: "Measurement outcome needs confirmation",
    })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Abandon saved request" }));

    expect(getPendingMeasurementRequest("scan-1")).toBeNull();
    expect(screen.queryByRole("heading", {
      name: "Measurement outcome needs confirmation",
    })).not.toBeInTheDocument();
  });
});
