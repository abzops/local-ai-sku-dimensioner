import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { listScans } from "../api/scans";
import type { ScanListResponse } from "../types/scans";
import { HistoryPage } from "./HistoryPage";

vi.mock("../api/scans", async () => {
  const actual = await vi.importActual<typeof import("../api/scans")>("../api/scans");
  return { ...actual, listScans: vi.fn() };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><HistoryPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.mocked(listScans).mockReset();
});

describe("HistoryPage", () => {
  it("shows a loading state while local history is pending", () => {
    vi.mocked(listScans).mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading scans");
  });

  it("shows an empty state", async () => {
    vi.mocked(listScans).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 20 });
    renderPage();
    expect(await screen.findByRole("heading", { name: "No scans yet" })).toBeVisible();
  });

  it("shows a safe error state", async () => {
    vi.mocked(listScans).mockRejectedValue(new Error("socket details that should stay hidden"));
    renderPage();
    expect(await screen.findByRole("heading", { name: "History unavailable" })).toBeVisible();
    expect(screen.getByText("The local service could not be reached.")).toBeVisible();
    expect(screen.queryByText(/socket details/)).not.toBeInTheDocument();
  });

  it("renders persisted scan summaries and missing views", async () => {
    const data: ScanListResponse = {
      items: [
        {
          id: "scan-1",
          sku: "SKU-1",
          barcode: "12345",
          product_name: "Storage box",
          status: "images_uploaded",
          image_count: 1,
          missing_required_views: ["front", "side"],
          created_at: "2026-07-17T10:00:00Z",
          updated_at: "2026-07-17T10:00:00Z",
        },
      ],
      total: 1,
      offset: 0,
      limit: 20,
    };
    vi.mocked(listScans).mockResolvedValue(data);
    renderPage();

    expect(await screen.findByRole("heading", { name: "Storage box" })).toBeVisible();
    expect(screen.getByText("Images uploaded")).toBeVisible();
    expect(screen.getByText("front, side")).toBeVisible();
    expect(screen.getByRole("link", { name: /open scan/i })).toHaveAttribute("href", "/scans/scan-1");
  });
});
