import { afterEach, describe, expect, it, vi } from "vitest";

import {
  activateCalibrationProfile,
  buildCalibrationTestFormData,
  createCalibrationProfile,
  getCalibrationMarkerSvg,
  getCalibrationOptions,
  getCalibrationProfile,
  listCalibrationProfiles,
  testCalibrationProfile,
} from "./calibration";
import type {
  CalibrationOptionsResponse,
  CalibrationProfileCreateRequest,
  CalibrationProfileResponse,
  CalibrationTestResponse,
} from "../types/calibration";

const createRequest: CalibrationProfileCreateRequest = {
  name: "Warehouse 100 mm",
  dictionary: "DICT_4X4_50",
  marker_id: 0,
  marker_size_mm: 100,
  minimum_marker_side_px: 64,
  maximum_perspective_ratio: 3,
  maximum_homography_condition_number: 1_000_000,
  maximum_marker_edge_residual_px: 2,
  rectified_pixels_per_mm: 4,
};

const profile: CalibrationProfileResponse = {
  id: "profile-1",
  ...createRequest,
  border_bits: 1,
  is_active: false,
  created_at: "2026-07-18T10:00:00Z",
  activated_at: null,
};

const options: CalibrationOptionsResponse = {
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
    maximum_homography_condition_number: 1_000_000,
    maximum_marker_edge_residual_px: 2,
    rectified_pixels_per_mm: 4,
  },
};

export const calibrationResult: CalibrationTestResponse = {
  profile_id: "profile-1",
  dictionary: "DICT_4X4_50",
  marker_id: 0,
  marker_size_mm: 100,
  ordered_corners: [
    { label: "top_left", x_px: 10, y_px: 10 },
    { label: "top_right", x_px: 110, y_px: 10 },
    { label: "bottom_right", x_px: 110, y_px: 110 },
    { label: "bottom_left", x_px: 10, y_px: 110 },
  ],
  orientation_degrees: 0,
  edge_lengths_px: { top: 100, right: 100, bottom: 100, left: 100 },
  perspective_ratio: 1,
  image_to_marker_mm: [[1, 0, -10], [0, 1, -10], [0, 0, 1]],
  marker_mm_to_image: [[1, 0, 10], [0, 1, 10], [0, 0, 1]],
  homography_condition_number: 1,
  rectified_width_px: 400,
  rectified_height_px: 400,
  rectified_pixels_per_mm: 4,
  marker_edge_quality: {
    metric_name: "marker_edge_localization_residual",
    description: "Sampled marker-border localization residual in image pixels.",
    rms_px: 0.6,
    maximum_px: 1.2,
    sample_count: 64,
    per_edge_rms_px: { top: 0.5, right: 0.7, bottom: 0.6, left: 0.6 },
    threshold_px: 2,
    valid: true,
  },
  annotated_preview: { media_type: "image/png", width_px: 1280, height_px: 960, data_base64: "aGVsbG8=" },
  rectified_preview: { media_type: "image/png", width_px: 400, height_px: 400, data_base64: "aGVsbG8=" },
};

function jsonResponse(payload: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: vi.fn().mockResolvedValue(payload) };
}

afterEach(() => vi.unstubAllGlobals());

describe("calibration API client", () => {
  it("calls every profile endpoint and validates the exact public schemas", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(options))
      .mockResolvedValueOnce(jsonResponse(profile, 201))
      .mockResolvedValueOnce(jsonResponse({ items: [profile], total: 1 }))
      .mockResolvedValueOnce(jsonResponse(profile))
      .mockResolvedValueOnce(jsonResponse({ ...profile, is_active: true, activated_at: "2026-07-18T10:10:00Z" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getCalibrationOptions()).resolves.toEqual(options);
    await expect(createCalibrationProfile(createRequest)).resolves.toEqual(profile);
    await expect(listCalibrationProfiles()).resolves.toEqual({ items: [profile], total: 1 });
    await expect(getCalibrationProfile("profile/unsafe")).resolves.toEqual(profile);
    await expect(activateCalibrationProfile("profile/unsafe")).resolves.toMatchObject({ is_active: true });

    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/calibration/profiles", expect.objectContaining({ method: "POST", body: JSON.stringify(createRequest) }));
    expect(fetchMock).toHaveBeenNthCalledWith(4, "/api/calibration/profiles/profile%2Funsafe", expect.objectContaining({ method: "GET" }));
    expect(fetchMock).toHaveBeenNthCalledWith(5, "/api/calibration/profiles/profile%2Funsafe/activate", expect.objectContaining({ method: "POST" }));
  });

  it("downloads only an SVG marker response", async () => {
    const svg = new Blob(["<svg/>"] , { type: "image/svg+xml" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, headers: new Headers({ "content-type": "image/svg+xml; charset=utf-8" }), blob: vi.fn().mockResolvedValue(svg), json: vi.fn() }));
    await expect(getCalibrationMarkerSvg("profile-1")).resolves.toBe(svg);
  });

  it("builds exactly one image multipart field and validates the test response", async () => {
    const image = new File(["image"], "marker.png", { type: "image/png" });
    const form = buildCalibrationTestFormData(image);
    expect([...form.keys()]).toEqual(["image"]);
    expect(form.get("image")).toBe(image);

    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(calibrationResult));
    vi.stubGlobal("fetch", fetchMock);
    await expect(testCalibrationProfile("profile-1", image)).resolves.toEqual(calibrationResult);
    expect(fetchMock).toHaveBeenCalledWith("/api/calibration/profiles/profile-1/test", expect.objectContaining({ method: "POST", body: expect.any(FormData) }));
    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("rejects unknown nested fields and non-finite numbers recursively", async () => {
    const withUnknown = { ...calibrationResult, marker_edge_quality: { ...calibrationResult.marker_edge_quality, internal_path: "C:\\secret" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse(withUnknown)).mockResolvedValueOnce(jsonResponse({ ...calibrationResult, perspective_ratio: Number.NaN })));
    const image = new File(["image"], "marker.png", { type: "image/png" });
    await expect(testCalibrationProfile("profile-1", image)).rejects.toMatchObject({ status: 502, payload: { code: "INVALID_API_RESPONSE" } });
    await expect(testCalibrationProfile("profile-1", image)).rejects.toMatchObject({ status: 502, payload: { code: "INVALID_API_RESPONSE" } });
  });

  it("rejects invalid enum, corner order, matrix shape, and preview media type", async () => {
    const invalidPayloads = [
      { ...calibrationResult, dictionary: "DICT_7X7_50" },
      { ...calibrationResult, ordered_corners: [...calibrationResult.ordered_corners].reverse() },
      { ...calibrationResult, image_to_marker_mm: [[1, 0], [0, 1]] },
      { ...calibrationResult, annotated_preview: { ...calibrationResult.annotated_preview, media_type: "image/jpeg" } },
      { ...calibrationResult, marker_edge_quality: { ...calibrationResult.marker_edge_quality, valid: false } },
    ];
    const fetchMock = vi.fn();
    invalidPayloads.forEach((payload) => fetchMock.mockResolvedValueOnce(jsonResponse(payload)));
    vi.stubGlobal("fetch", fetchMock);
    const image = new File(["image"], "marker.png", { type: "image/png" });
    for (let index = 0; index < invalidPayloads.length; index += 1) {
      await expect(testCalibrationProfile("profile-1", image)).rejects.toMatchObject({ status: 502 });
    }
  });

  it("preserves a structured calibration error and sanitizes non-JSON failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse({ code: "REFERENCE_NOT_DETECTED", message: "No marker was detected.", recoverable: true, suggested_action: "Retake the image.", field: "image" }, 422)).mockResolvedValueOnce({ ok: false, status: 503, json: vi.fn().mockRejectedValue(new SyntaxError("html")) }));
    const image = new File(["image"], "marker.png", { type: "image/png" });
    await expect(testCalibrationProfile("profile-1", image)).rejects.toMatchObject({ status: 422, payload: { code: "REFERENCE_NOT_DETECTED", field: "image" } });
    await expect(getCalibrationOptions()).rejects.toMatchObject({ status: 503, payload: { code: "REQUEST_FAILED" } });
  });
});
