import { useEffect, useState } from "react";

import {
  clearPendingMeasurementRequest,
  getPendingMeasurementRequest,
  MeasurementApiRequestError,
  prepareMeasurementRequest,
  processMeasurement,
} from "../api/measurements";
import type {
  MeasurementApiErrorResponse,
  MeasurementAttemptDetailResponse,
  MeasurementOptionsResponse,
  MeasurementProcessRequest,
} from "../types/measurements";

export interface MeasurementConfirmationDialogProps {
  open: boolean;
  scanId: string;
  activeCalibrationProfile: { id: string; name: string } | null;
  options: MeasurementOptionsResponse | null;
  reprocessOfMeasurementId?: string | null;
  onCancel: () => void;
  onCompleted: (attempt: MeasurementAttemptDetailResponse) => void;
  onPendingRequestChange?: (request: MeasurementProcessRequest | null) => void;
}

export function MeasurementConfirmationDialog({
  open,
  scanId,
  activeCalibrationProfile,
  options,
  reprocessOfMeasurementId = null,
  onCancel,
  onCompleted,
  onPendingRequestChange,
}: MeasurementConfirmationDialogProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<MeasurementApiErrorResponse | null>(null);
  const [uncertain, setUncertain] = useState(false);

  useEffect(() => {
    setAcknowledged(false);
    setError(null);
    setUncertain(false);
  }, [
    open,
    scanId,
    activeCalibrationProfile?.id,
    options?.capture_setup.id,
    options?.capture_setup.version,
    reprocessOfMeasurementId,
  ]);

  if (!open) return null;
  const available = Boolean(activeCalibrationProfile && options?.capture_setup.processing_enabled);

  function closeDialog() {
    setAcknowledged(false);
    setError(null);
    setUncertain(false);
    onCancel();
  }

  async function submit() {
    if (!activeCalibrationProfile || !options || !acknowledged) return;
    setSubmitting(true);
    setError(null);
    try {
      const request = prepareMeasurementRequest(
        scanId,
        activeCalibrationProfile.id,
        options.capture_setup.id,
        reprocessOfMeasurementId,
      );
      const result = await processMeasurement(scanId, request);
      clearPendingMeasurementRequest(scanId);
      onPendingRequestChange?.(null);
      setAcknowledged(false);
      setUncertain(false);
      onCompleted(result);
    } catch (caught) {
      if (caught instanceof MeasurementApiRequestError) {
        setError(caught.payload);
        setUncertain(caught.outcomeUncertain);
        if (caught.outcomeUncertain) {
          onPendingRequestChange?.(getPendingMeasurementRequest(scanId));
        } else {
          clearPendingMeasurementRequest(scanId);
          onPendingRequestChange?.(null);
        }
      } else {
        setError({
          code: "NETWORK_ERROR",
          message: "The local service could not be reached.",
          recoverable: true,
          suggested_action: "Retry this same request or check measurement history.",
        });
        setUncertain(true);
        onPendingRequestChange?.(getPendingMeasurementRequest(scanId));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dialog-backdrop">
      <section
        className="detail-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="measurement-confirm-title"
      >
        <h2 id="measurement-confirm-title">Confirm deterministic measurement</h2>
        <p>
          This runs synchronously using the active marker profile and qualified physical rig. It
          is not certified metrology.
        </p>
        <dl className="metadata-list">
          <div><dt>Profile</dt><dd>{activeCalibrationProfile?.name ?? "No active profile"}</dd></div>
          <div>
            <dt>Capture setup</dt>
            <dd>{options ? `${options.capture_setup.id} v${options.capture_setup.version}` : "Unavailable"}</dd>
          </div>
          <div>
            <dt>Supported size</dt>
            <dd>{options ? `${options.capture_setup.minimum_object_mm}-${options.capture_setup.maximum_object_mm} mm` : "Unavailable"}</dd>
          </div>
        </dl>
        {options?.capture_setup.requirements.map((item) => <p key={item}>- {item}</p>)}
        <label>
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />{" "}
          I confirm the product and all three views satisfy this physical capture contract.
        </label>
        {error && (
          <section role="alert" className="state-panel state-panel--error">
            <strong>{error.message}</strong>
            <p>{error.suggested_action}</p>
            {uncertain && (
              <p>The same saved request ID will be reused. A new request will not be generated silently.</p>
            )}
          </section>
        )}
        <div className="form-actions">
          <button
            className="button button--primary"
            type="button"
            disabled={!available || !acknowledged || submitting}
            onClick={() => void submit()}
          >
            {submitting
              ? "Measuring..."
              : uncertain
                ? "Retry same request"
                : reprocessOfMeasurementId
                  ? "Confirm reprocessing"
                  : "Start measurement"}
          </button>
          <button
            className="button button--secondary"
            type="button"
            disabled={submitting}
            onClick={closeDialog}
          >
            Cancel
          </button>
        </div>
      </section>
    </div>
  );
}
