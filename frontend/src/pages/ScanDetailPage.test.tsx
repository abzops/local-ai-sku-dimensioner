import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getScan } from "../api/scans";
import type { ScanDetailResponse } from "../types/scans";
import { ScanDetailPage } from "./ScanDetailPage";

vi.mock("../api/scans", async () => {
  const actual = await vi.importActual<typeof import("../api/scans")>("../api/scans");
  return { ...actual, getScan: vi.fn() };
});

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

afterEach(() => {
  vi.mocked(getScan).mockReset();
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
    expect(screen.getByText(/dimension calculation are not available/i)).toBeVisible();
    expect(document.body).not.toHaveTextContent(/localappdata|[a-z]:\\|\\scans\\/i);
  });

  it("renders a safe unavailable state", async () => {
    vi.mocked(getScan).mockRejectedValue(new Error("C:\\private\\scan.db"));
    renderPage();

    expect(await screen.findByRole("heading", { name: "Scan unavailable" })).toBeVisible();
    expect(screen.getByText("The local service could not be reached.")).toBeVisible();
    expect(document.body).not.toHaveTextContent("C:\\private");
  });
});
