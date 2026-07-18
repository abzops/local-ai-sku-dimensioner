import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearPendingMeasurementRequest,
  getPendingMeasurementRequest,
  MeasurementApiRequestError,
  prepareMeasurementRequest,
  processMeasurement,
} from "../api/measurements";
import {
  measurementId,
  measurementOptionsFixture,
  profileId,
  requestId,
  scanId,
  succeededDetailFixture,
} from "../test/measurementFixtures";
import type { MeasurementProcessRequest } from "../types/measurements";
import {
  MeasurementConfirmationDialog,
  type MeasurementConfirmationDialogProps,
} from "./MeasurementConfirmationDialog";

vi.mock("../api/measurements", async () => {
  const actual = await vi.importActual<typeof import("../api/measurements")>(
    "../api/measurements",
  );
  return {
    ...actual,
    clearPendingMeasurementRequest: vi.fn(),
    getPendingMeasurementRequest: vi.fn(),
    prepareMeasurementRequest: vi.fn(),
    processMeasurement: vi.fn(),
  };
});

const pendingRequest: MeasurementProcessRequest = {
  request_id: requestId,
  expected_calibration_profile_id: profileId,
  expected_capture_setup_id: "rig-local-1",
  capture_contract_acknowledged: true,
  reprocess_of_measurement_id: null,
};

function dialogProps(
  overrides: Partial<MeasurementConfirmationDialogProps> = {},
): MeasurementConfirmationDialogProps {
  return {
    open: true,
    scanId,
    activeCalibrationProfile: { id: profileId, name: "Profile" },
    options: measurementOptionsFixture,
    onCancel: vi.fn(),
    onCompleted: vi.fn(),
    onPendingRequestChange: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(clearPendingMeasurementRequest).mockReset();
  vi.mocked(getPendingMeasurementRequest).mockReset();
  vi.mocked(prepareMeasurementRequest).mockReset();
  vi.mocked(processMeasurement).mockReset();
  vi.mocked(prepareMeasurementRequest).mockReturnValue(pendingRequest);
  vi.mocked(getPendingMeasurementRequest).mockReturnValue(pendingRequest);
});

describe("MeasurementConfirmationDialog", () => {
  it("requires physical-contract acknowledgement", () => {
    render(<MeasurementConfirmationDialog {...dialogProps()} />);
    const button = screen.getByRole("button", { name: "Start measurement" });

    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(button).toBeEnabled();
  });

  it("resets acknowledgement when closed and reopened", () => {
    const props = dialogProps();
    const view = render(<MeasurementConfirmationDialog {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Start measurement" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    view.rerender(<MeasurementConfirmationDialog {...props} open={false} />);
    view.rerender(<MeasurementConfirmationDialog {...props} open />);

    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Start measurement" })).toBeDisabled();
  });

  it("resets acknowledgement after a successful submit and reopen", async () => {
    const onCompleted = vi.fn();
    vi.mocked(processMeasurement).mockResolvedValue(succeededDetailFixture);
    const props = dialogProps({ onCompleted });
    const view = render(<MeasurementConfirmationDialog {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start measurement" }));

    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(succeededDetailFixture));
    view.rerender(<MeasurementConfirmationDialog {...props} open={false} />);
    view.rerender(<MeasurementConfirmationDialog {...props} open />);

    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Start measurement" })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears a definite validation error before reopen", async () => {
    vi.mocked(processMeasurement).mockRejectedValue(new MeasurementApiRequestError(422, {
      code: "CAPTURE_SETUP_MISMATCH",
      message: "The capture setup no longer matches.",
      recoverable: true,
      suggested_action: "Refresh the measurement options.",
    }));
    const props = dialogProps();
    const view = render(<MeasurementConfirmationDialog {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start measurement" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("no longer matches");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    view.rerender(<MeasurementConfirmationDialog {...props} open={false} />);
    view.rerender(<MeasurementConfirmationDialog {...props} open />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(clearPendingMeasurementRequest).toHaveBeenCalledWith(scanId);
  });

  it("resets acknowledgement and stale errors when the reprocess source changes", async () => {
    vi.mocked(processMeasurement).mockRejectedValue(new MeasurementApiRequestError(422, {
      code: "SOURCE_IMAGES_CHANGED",
      message: "The source images changed.",
      recoverable: true,
      suggested_action: "Review the current scan images.",
    }));
    const props = dialogProps({ reprocessOfMeasurementId: measurementId });
    const view = render(<MeasurementConfirmationDialog {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reprocessing" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("source images changed");

    view.rerender(
      <MeasurementConfirmationDialog
        {...props}
        reprocessOfMeasurementId="55555555-5555-4555-8555-555555555555"
      />,
    );

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Confirm reprocessing" })).toBeDisabled();
  });

  it("does not clear an uncertain saved request when the dialog closes", async () => {
    const onPendingRequestChange = vi.fn();
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
    const props = dialogProps({ onPendingRequestChange });
    render(<MeasurementConfirmationDialog {...props} />);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Start measurement" }));

    expect(await screen.findByRole("button", { name: "Retry same request" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onPendingRequestChange).toHaveBeenCalledWith(pendingRequest);
    expect(clearPendingMeasurementRequest).not.toHaveBeenCalled();
  });
});
