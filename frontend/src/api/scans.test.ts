import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildUploadFormData,
  createScan,
  getScan,
  listScans,
  uploadScanImages,
} from "./scans";

const image = {
  id: "image-1",
  view_type: "top",
  media_type: "image/jpeg",
  size_bytes: 2048,
  width_px: 1600,
  height_px: 1200,
  created_at: "2026-07-17T10:00:00Z",
};

const detail = {
  id: "scan-1",
  sku: "SKU-1",
  barcode: null,
  product_name: "Box",
  status: "images_uploaded",
  missing_required_views: ["front", "side"],
  created_at: "2026-07-17T10:00:00Z",
  updated_at: "2026-07-17T10:00:00Z",
  images: [image],
};

function response(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(payload),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("scan API client", () => {
  it("creates, reads, and lists validated scan responses", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(detail, 201))
      .mockResolvedValueOnce(response(detail))
      .mockResolvedValueOnce(
        response({
          items: [{ ...detail, images: undefined, image_count: 1 }],
          total: 1,
          offset: 20,
          limit: 20,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(createScan({ sku: "SKU-1", barcode: null })).resolves.toEqual(detail);
    await expect(getScan("scan-1")).resolves.toEqual(detail);
    await expect(listScans({ offset: 20, limit: 20 })).resolves.toMatchObject({ total: 1 });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/scans",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ sku: "SKU-1", barcode: null }) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/scans?offset=20&limit=20",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("builds the frozen multipart field names without adding a content-type header", async () => {
    const top = new File(["top"], "top.jpg", { type: "image/jpeg" });
    const extraOne = new File(["one"], "one.png", { type: "image/png" });
    const extraTwo = new File(["two"], "two.webp", { type: "image/webp" });
    const form = buildUploadFormData({ top, additional: [extraOne, extraTwo] });

    expect(form.get("top")).toBe(top);
    expect(form.getAll("additional")).toEqual([extraOne, extraTwo]);

    const uploadResponse = { scan: detail, uploaded_images: [image] };
    const fetchMock = vi.fn().mockResolvedValue(response(uploadResponse, 201));
    vi.stubGlobal("fetch", fetchMock);
    await uploadScanImages("scan/with unsafe characters", { top, additional: [extraOne] });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/scans/scan%2Fwith%20unsafe%20characters/images",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("preserves a valid structured API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            code: "DUPLICATE_VIEW",
            message: "The top image already exists.",
            recoverable: true,
            suggested_action: "Upload only missing views.",
            view: "top",
          },
          409,
        ),
      ),
    );

    await expect(getScan("scan-1")).rejects.toMatchObject({
      status: 409,
      payload: { code: "DUPLICATE_VIEW", view: "top" },
    });
  });

  it("converts a non-JSON API failure into a safe fallback error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: vi.fn().mockRejectedValue(new SyntaxError("HTML response")),
      }),
    );

    await expect(getScan("scan-1")).rejects.toMatchObject({
      status: 503,
      payload: {
        code: "REQUEST_FAILED",
        message: "The local API request failed with status 503.",
      },
    });
  });

  it("rejects malformed successful responses with a safe client error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ id: "scan-1" })));

    await expect(getScan("scan-1")).rejects.toMatchObject({
      status: 502,
      payload: { code: "INVALID_API_RESPONSE" },
    });
  });
});
