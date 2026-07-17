import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, createScan, getScan, uploadScanImages } from "../api/scans";
import type { ScanDetailResponse } from "../types/scans";
import { NewScanPage } from "./NewScanPage";

vi.mock("../api/scans", async () => {
  const actual = await vi.importActual<typeof import("../api/scans")>("../api/scans");
  return { ...actual, createScan: vi.fn(), getScan: vi.fn(), uploadScanImages: vi.fn() };
});

const draftScan: ScanDetailResponse = {
  id: "scan-1",
  sku: "SKU-1",
  barcode: null,
  product_name: "Storage box",
  status: "draft",
  missing_required_views: ["top", "front", "side"],
  created_at: "2026-07-17T10:00:00Z",
  updated_at: "2026-07-17T10:00:00Z",
  images: [],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/scans/new"]}>
        <Routes>
          <Route path="/scans/new" element={<NewScanPage />} />
          <Route path="/scans/:scanId" element={<h1>Saved scan</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function completeForm() {
  fireEvent.change(screen.getByLabelText("SKU *"), { target: { value: " SKU-1 " } });
  fireEvent.change(screen.getByLabelText("Product name"), {
    target: { value: " Storage box " },
  });
  const file = (name: string) => new File([name], name, { type: "image/jpeg" });
  fireEvent.change(screen.getByLabelText("Top view from files"), {
    target: { files: [file("top.jpg")] },
  });
  fireEvent.change(screen.getByLabelText("Front view from files"), {
    target: { files: [file("front.jpg")] },
  });
  fireEvent.change(screen.getByLabelText("Side view from files"), {
    target: { files: [file("side.jpg")] },
  });
}

describe("NewScanPage", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((file: File) => `blob:${file.name}`),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  });

  afterEach(() => {
    vi.mocked(createScan).mockReset();
    vi.mocked(getScan).mockReset();
    vi.mocked(uploadScanImages).mockReset();
  });

  it("creates a scan, uploads the selected views, and opens its details", async () => {
    vi.mocked(createScan).mockResolvedValue(draftScan);
    vi.mocked(uploadScanImages).mockResolvedValue({
      scan: { ...draftScan, status: "ready_for_processing", missing_required_views: [] },
      uploaded_images: [],
    });
    renderPage();
    completeForm();

    fireEvent.click(screen.getByRole("button", { name: "Create scan and upload images" }));

    expect(await screen.findByRole("heading", { name: "Saved scan" })).toBeVisible();
    expect(createScan).toHaveBeenCalledWith({
      sku: "SKU-1",
      barcode: null,
      product_name: "Storage box",
    });
    expect(uploadScanImages).toHaveBeenCalledWith(
      "scan-1",
      expect.objectContaining({
        top: expect.objectContaining({ name: "top.jpg" }),
        front: expect.objectContaining({ name: "front.jpg" }),
        side: expect.objectContaining({ name: "side.jpg" }),
      }),
    );
  });

  it("retains the created scan ID and retries only the image batch", async () => {
    vi.mocked(createScan).mockResolvedValue(draftScan);
    vi.mocked(uploadScanImages)
      .mockRejectedValueOnce(
        new ApiRequestError(422, {
          code: "IMAGE_TOO_SMALL",
          message: "The top image is too small.",
          recoverable: true,
          suggested_action: "Choose a larger image.",
          view: "top",
        }),
      )
      .mockResolvedValueOnce({
        scan: { ...draftScan, status: "ready_for_processing", missing_required_views: [] },
        uploaded_images: [],
      });
    vi.mocked(getScan).mockResolvedValue(draftScan);
    renderPage();
    completeForm();

    fireEvent.click(screen.getByRole("button", { name: "Create scan and upload images" }));
    expect(await screen.findByText("The top image is too small.")).toBeVisible();
    expect(screen.getByText(/draft scan was created/i)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Retry image upload" }));
    expect(await screen.findByRole("heading", { name: "Saved scan" })).toBeVisible();
    expect(createScan).toHaveBeenCalledTimes(1);
    expect(uploadScanImages).toHaveBeenCalledTimes(2);
  });

  it("reconciles a lost upload response instead of resending committed views", async () => {
    vi.mocked(createScan).mockResolvedValue(draftScan);
    vi.mocked(uploadScanImages).mockRejectedValue(new Error("connection closed"));
    vi.mocked(getScan).mockResolvedValue({
      ...draftScan,
      status: "ready_for_processing",
      missing_required_views: [],
    });
    renderPage();
    completeForm();

    fireEvent.click(screen.getByRole("button", { name: "Create scan and upload images" }));

    expect(await screen.findByRole("heading", { name: "Saved scan" })).toBeVisible();
    expect(createScan).toHaveBeenCalledTimes(1);
    expect(uploadScanImages).toHaveBeenCalledTimes(1);
    expect(getScan).toHaveBeenCalledWith("scan-1");
  });

  it("blocks an unsafe create retry when the create outcome is unknown", async () => {
    vi.mocked(createScan).mockRejectedValue(new Error("connection closed"));
    renderPage();
    completeForm();

    fireEvent.click(screen.getByRole("button", { name: "Create scan and upload images" }));

    expect(await screen.findByText(/did not confirm whether the scan was created/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Check History" })).toHaveAttribute(
      "href",
      "/scans",
    );
    expect(screen.getByRole("button", { name: "Creation unconfirmed" })).toBeDisabled();
    expect(createScan).toHaveBeenCalledTimes(1);
    expect(uploadScanImages).not.toHaveBeenCalled();
  });

  it("does not create a scan until all required views are selected", async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText("SKU *"), { target: { value: "SKU-1" } });
    fireEvent.submit(screen.getByRole("button", { name: "Create scan and upload images" }).closest("form")!);

    expect(await screen.findByText(/top, front, and side images are required/i)).toBeVisible();
    expect(createScan).not.toHaveBeenCalled();
  });
});
