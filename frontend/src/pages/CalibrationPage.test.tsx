import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  activateCalibrationProfile,
  createCalibrationProfile,
  getCalibrationMarkerSvg,
  getCalibrationOptions,
  getCalibrationProfile,
  listCalibrationProfiles,
  testCalibrationProfile,
} from "../api/calibration";
import type {
  CalibrationOptionsResponse,
  CalibrationProfileResponse,
  CalibrationTestResponse,
} from "../types/calibration";
import { CalibrationPage } from "./CalibrationPage";

vi.mock("../api/calibration", async () => {
  const actual = await vi.importActual<typeof import("../api/calibration")>("../api/calibration");
  return {
    ...actual,
    activateCalibrationProfile: vi.fn(),
    createCalibrationProfile: vi.fn(),
    getCalibrationMarkerSvg: vi.fn(),
    getCalibrationOptions: vi.fn(),
    getCalibrationProfile: vi.fn(),
    listCalibrationProfiles: vi.fn(),
    testCalibrationProfile: vi.fn(),
  };
});

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

const profile: CalibrationProfileResponse = {
  id: "profile-1",
  name: "Warehouse marker",
  ...options.defaults,
  border_bits: 1,
  is_active: false,
  created_at: "2026-07-18T10:00:00Z",
  activated_at: null,
};

const secondProfile: CalibrationProfileResponse = {
  ...profile,
  id: "profile-2",
  name: "Backup marker",
  marker_id: 49,
};

const result: CalibrationTestResponse = {
  profile_id: profile.id,
  dictionary: "DICT_4X4_50",
  marker_id: 0,
  marker_size_mm: 100,
  ordered_corners: [
    { label: "top_left", x_px: 10, y_px: 10 },
    { label: "top_right", x_px: 110, y_px: 10 },
    { label: "bottom_right", x_px: 110, y_px: 110 },
    { label: "bottom_left", x_px: 10, y_px: 110 },
  ],
  orientation_degrees: -2.5,
  edge_lengths_px: { top: 100, right: 101, bottom: 99, left: 100 },
  perspective_ratio: 1.02,
  image_to_marker_mm: [[1, 0, -10], [0, 1, -10], [0, 0, 1]],
  marker_mm_to_image: [[1, 0, 10], [0, 1, 10], [0, 0, 1]],
  homography_condition_number: 1.5,
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
  annotated_preview: { media_type: "image/png", width_px: 800, height_px: 600, data_base64: "aGVsbG8=" },
  rectified_preview: { media_type: "image/png", width_px: 400, height_px: 400, data_base64: "aGVsbG8=" },
};

function mockLoadedProfiles(items: CalibrationProfileResponse[] = [profile]) {
  vi.mocked(getCalibrationOptions).mockResolvedValue(options);
  vi.mocked(listCalibrationProfiles).mockResolvedValue({ items, total: items.length });
  vi.mocked(getCalibrationProfile).mockImplementation(async (id) => items.find((item) => item.id === id) ?? profile);
  vi.mocked(getCalibrationMarkerSvg).mockResolvedValue(new Blob(["<svg/>"] , { type: "image/svg+xml" }));
}

describe("CalibrationPage", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn((value: Blob) => value.type === "image/svg+xml" ? "blob:marker" : "blob:image") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    mockLoadedProfiles();
  });

  afterEach(() => vi.clearAllMocks());

  it("loads profiles, exact-size printing guidance, marker preview, and mobile camera input", async () => {
    render(<CalibrationPage />);

    expect(await screen.findByRole("heading", { name: "Calibrate the printed marker" })).toBeVisible();
    expect(await screen.findByRole("heading", { name: "Warehouse marker" })).toBeVisible();
    expect(screen.getByText(/100% or actual size/i)).toBeVisible();
    expect(screen.getByText(/fit-to-page scaling disabled/i)).toBeVisible();
    expect(await screen.findByAltText(/ArUco marker 0/i)).toHaveAttribute("src", "blob:marker");
    expect(screen.getByRole("link", { name: "Download SVG" })).toHaveAttribute("download", "aruco-DICT_4X4_50-0.svg");
    expect(screen.getByLabelText("Capture or choose marker image")).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    expect(screen.getByLabelText("Capture or choose marker image")).toHaveAttribute("capture", "environment");
  });

  it("creates an immutable profile from the frozen request fields", async () => {
    vi.mocked(createCalibrationProfile).mockResolvedValue({ ...profile, id: "created-1", name: "Bench marker" });
    render(<CalibrationPage />);
    await screen.findByRole("heading", { name: "Warehouse marker" });

    fireEvent.change(screen.getByLabelText("Profile name *"), { target: { value: " Bench marker " } });
    fireEvent.click(screen.getByRole("button", { name: "Create profile" }));

    await waitFor(() => expect(createCalibrationProfile).toHaveBeenCalledWith({ name: "Bench marker", ...options.defaults }));
    expect(listCalibrationProfiles).toHaveBeenCalledTimes(2);
  });

  it("activates only the selected existing profile", async () => {
    const activated = { ...profile, is_active: true, activated_at: "2026-07-18T11:00:00Z" };
    vi.mocked(activateCalibrationProfile).mockResolvedValue(activated);
    render(<CalibrationPage />);
    await screen.findByRole("heading", { name: "Warehouse marker" });

    fireEvent.click(screen.getByRole("button", { name: "Activate profile" }));

    await waitFor(() => expect(activateCalibrationProfile).toHaveBeenCalledWith("profile-1"));
    expect(await screen.findByText("Active")).toBeVisible();
  });

  it("previews one local image and displays complete marker-plane evidence", async () => {
    vi.mocked(testCalibrationProfile).mockResolvedValue(result);
    render(<CalibrationPage />);
    await screen.findByRole("heading", { name: "Warehouse marker" });
    const image = new File(["marker"], "marker.png", { type: "image/png" });

    fireEvent.change(screen.getByLabelText("Capture or choose marker image"), { target: { files: [image] } });
    expect(await screen.findByAltText("Selected marker image preview")).toHaveAttribute("src", "blob:image");
    fireEvent.click(screen.getByRole("button", { name: "Run calibration test" }));

    expect(await screen.findByRole("heading", { name: "Calibration test result" })).toBeVisible();
    expect(testCalibrationProfile).toHaveBeenCalledWith("profile-1", image);
    expect(screen.getByText("profile-1")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Ordered marker corners" })).toBeVisible();
    expect(screen.getByText("marker_edge_localization_residual")).toBeVisible();
    expect(screen.getByRole("table", { name: "Image pixels to marker millimetres" })).toBeVisible();
    expect(screen.getByAltText("Annotated marker detection with canonical corners")).toHaveAttribute("src", "data:image/png;base64,aGVsbG8=");
    expect(screen.getByAltText("Perspective-rectified marker preview")).toBeVisible();
    expect(screen.getByText(/does not calculate product dimensions/i)).toBeVisible();
  });

  it("retries the same idempotent image while its profile remains selected", async () => {
    mockLoadedProfiles([profile, secondProfile]);
    vi.mocked(testCalibrationProfile)
      .mockRejectedValueOnce(new Error("connection closed"))
      .mockResolvedValueOnce(result);
    render(<CalibrationPage />);
    await screen.findByRole("heading", { name: "Warehouse marker" });
    const image = new File(["marker"], "marker.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Capture or choose marker image"), { target: { files: [image] } });
    fireEvent.click(screen.getByRole("button", { name: "Run calibration test" }));
    expect(await screen.findByText("The local service could not be reached.")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Retry same image" }));

    await screen.findByRole("heading", { name: "Calibration test result" });
    expect(testCalibrationProfile).toHaveBeenNthCalledWith(1, "profile-1", image);
    expect(testCalibrationProfile).toHaveBeenNthCalledWith(2, "profile-1", image);
  });

  it("clears profile-bound errors and retries when another profile is selected", async () => {
    mockLoadedProfiles([profile, secondProfile]);
    vi.mocked(testCalibrationProfile).mockRejectedValue(new Error("connection closed"));
    render(<CalibrationPage />);
    await screen.findByRole("heading", { name: "Warehouse marker" });
    const image = new File(["marker"], "marker.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Capture or choose marker image"), { target: { files: [image] } });
    fireEvent.click(screen.getByRole("button", { name: "Run calibration test" }));
    expect(await screen.findByRole("button", { name: "Retry same image" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Backup marker/ }));
    await screen.findByRole("heading", { name: "Backup marker" });

    expect(screen.queryByRole("button", { name: "Retry same image" })).not.toBeInTheDocument();
    expect(screen.queryByText("The local service could not be reached.")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Calibration test result" })).not.toBeInTheDocument();
  });

  it("clears successful evidence when another profile is selected", async () => {
    mockLoadedProfiles([profile, secondProfile]);
    vi.mocked(testCalibrationProfile).mockResolvedValue(result);
    render(<CalibrationPage />);
    await screen.findByRole("heading", { name: "Warehouse marker" });
    const image = new File(["marker"], "marker.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Capture or choose marker image"), { target: { files: [image] } });
    fireEvent.click(screen.getByRole("button", { name: "Run calibration test" }));
    expect(await screen.findByRole("heading", { name: "Calibration test result" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Backup marker/ }));
    await screen.findByRole("heading", { name: "Backup marker" });

    expect(screen.queryByRole("heading", { name: "Calibration test result" })).not.toBeInTheDocument();
    expect(screen.queryByText("profile-1")).not.toBeInTheDocument();
  });
});
