import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { listCalibrationProfiles } from "../api/calibration";
import {
  abandonPendingMeasurementRequest,
  asMeasurementApiError,
  clearPendingMeasurementRequest,
  getMeasurementOptions,
  getPendingMeasurementRequest,
  listMeasurementAttempts,
  MeasurementApiRequestError,
  processMeasurement,
  reconcilePendingMeasurementRequest,
} from "../api/measurements";
import { asApiError, getScan } from "../api/scans";
import { MeasurementAttemptList } from "../components/MeasurementAttemptList";
import { MeasurementConfirmationDialog } from "../components/MeasurementConfirmationDialog";
import { ScanStatusBadge } from "../components/ScanStatusBadge";
import type {
  MeasurementApiErrorResponse,
  MeasurementAttemptSummaryResponse,
  MeasurementProcessRequest,
} from "../types/measurements";

function formatBytes(value: number): string {
  return value < 1024 * 1024
    ? `${Math.round(value / 1024)} KB`
    : `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function ScanDetailPage() {
  const { scanId = "" } = useParams();
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reprocessAttempt, setReprocessAttempt] =
    useState<MeasurementAttemptSummaryResponse | null>(null);
  const [pendingRequest, setPendingRequest] = useState<MeasurementProcessRequest | null>(() =>
    getPendingMeasurementRequest(scanId),
  );
  const [pendingRequestError, setPendingRequestError] =
    useState<MeasurementApiErrorResponse | null>(null);
  const [retryingPendingRequest, setRetryingPendingRequest] = useState(false);
  const scan = useQuery({
    queryKey: ["scans", scanId],
    queryFn: ({ signal }) => getScan(scanId, signal),
    enabled: scanId.length > 0,
  });
  const options = useQuery({
    queryKey: ["measurement-options"],
    queryFn: ({ signal }) => getMeasurementOptions(signal),
  });
  const profiles = useQuery({
    queryKey: ["calibration-profiles"],
    queryFn: ({ signal }) => listCalibrationProfiles(signal),
  });
  const attempts = useQuery({
    queryKey: ["measurement-attempts", scanId],
    queryFn: ({ signal }) => listMeasurementAttempts(scanId, {}, signal),
    enabled: scanId.length > 0,
  });

  useEffect(() => {
    setPendingRequest(getPendingMeasurementRequest(scanId));
    setPendingRequestError(null);
  }, [scanId]);

  useEffect(() => {
    if (attempts.data) {
      setPendingRequest(reconcilePendingMeasurementRequest(scanId, attempts.data.items));
    }
  }, [attempts.data, scanId]);

  if (scan.isPending) {
    return <main className="page-shell"><p className="state-panel" role="status">Loading scan...</p></main>;
  }

  if (scan.isError) {
    return (
      <main className="page-shell">
        <section className="state-panel state-panel--error" role="alert">
          <h1>Scan unavailable</h1>
          <p>{asApiError(scan.error).message}</p>
          <Link className="text-link" to="/scans">Return to history</Link>
        </section>
      </main>
    );
  }

  const activeProfile = profiles.data?.items.find((profile) => profile.is_active) ?? null;
  const measurementReady =
    scan.data.status === "ready_for_processing" &&
    options.data?.capture_setup.processing_enabled === true &&
    activeProfile !== null;

  function openMeasurementDialog(attempt: MeasurementAttemptSummaryResponse | null = null) {
    setReprocessAttempt(attempt);
    setDialogOpen(true);
  }

  async function retryPendingRequest() {
    if (!pendingRequest) return;
    setRetryingPendingRequest(true);
    setPendingRequestError(null);
    try {
      const result = await processMeasurement(scanId, pendingRequest);
      clearPendingMeasurementRequest(scanId);
      setPendingRequest(null);
      void navigate(
        `/scans/${encodeURIComponent(scanId)}/measurements/${encodeURIComponent(result.id)}`,
      );
    } catch (caught) {
      if (caught instanceof MeasurementApiRequestError) {
        setPendingRequestError(caught.payload);
        if (!caught.outcomeUncertain) {
          clearPendingMeasurementRequest(scanId);
          setPendingRequest(null);
        }
      } else {
        setPendingRequestError({
          code: "NETWORK_ERROR",
          message: "The local service could not be reached.",
          recoverable: true,
          suggested_action: "Retry this same request or refresh measurement history.",
        });
      }
    } finally {
      setRetryingPendingRequest(false);
    }
  }

  async function refreshAttemptHistory() {
    setPendingRequestError(null);
    const result = await attempts.refetch();
    if (result.data) {
      setPendingRequest(reconcilePendingMeasurementRequest(scanId, result.data.items));
    }
  }

  function abandonPendingRequest() {
    abandonPendingMeasurementRequest(scanId);
    setPendingRequest(null);
    setPendingRequestError(null);
  }

  return (
    <main className="page-shell">
      <header className="page-heading page-heading--split">
        <div>
          <p className="eyebrow">Scan record</p>
          <h1>{scan.data.sku}</h1>
          <p>{scan.data.product_name || "Unnamed product"}</p>
        </div>
        <ScanStatusBadge status={scan.data.status} />
      </header>

      <section className="detail-card" aria-labelledby="scan-details-heading">
        <h2 id="scan-details-heading">Details</h2>
        <dl className="metadata-list metadata-list--detail">
          <div><dt>Barcode</dt><dd>{scan.data.barcode || "Not provided"}</dd></div>
          <div><dt>Created</dt><dd>{new Date(scan.data.created_at).toLocaleString()}</dd></div>
          <div><dt>Updated</dt><dd>{new Date(scan.data.updated_at).toLocaleString()}</dd></div>
          <div>
            <dt>Missing required views</dt>
            <dd>{scan.data.missing_required_views.join(", ") || "None"}</dd>
          </div>
        </dl>
      </section>

      <section className="detail-card" aria-labelledby="images-heading">
        <div className="detail-card__heading">
          <div>
            <p className="eyebrow">Validated metadata</p>
            <h2 id="images-heading">Stored images</h2>
          </div>
          <span>{scan.data.images.length} total</span>
        </div>
        {scan.data.images.length === 0 ? (
          <p>No images have been uploaded.</p>
        ) : (
          <ul className="image-records">
            {scan.data.images.map((image) => (
              <li key={image.id}>
                <strong>{image.view_type}</strong>
                <span>{image.width_px} x {image.height_px}px</span>
                <span>{image.media_type}</span>
                <span>{formatBytes(image.size_bytes)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail-card" aria-labelledby="measurement-heading">
        <div className="detail-card__heading">
          <div>
            <p className="eyebrow">Deterministic geometry</p>
            <h2 id="measurement-heading">Measurement attempts</h2>
          </div>
          <button
            className="button button--primary"
            type="button"
            disabled={!measurementReady || pendingRequest !== null}
            onClick={() => openMeasurementDialog()}
          >
            Measure scan
          </button>
        </div>

        {pendingRequest && (
          <section className="state-panel" role="status" aria-live="polite">
            <h3>Measurement outcome needs confirmation</h3>
            <p>
              The previous request may have reached the server. Retry that exact saved request or
              refresh history before starting another measurement.
            </p>
            {pendingRequestError && (
              <div className="state-panel state-panel--error" role="alert">
                <strong>{pendingRequestError.message}</strong>
                <p>{pendingRequestError.suggested_action}</p>
              </div>
            )}
            <div className="form-actions">
              <button
                className="button button--primary"
                type="button"
                disabled={retryingPendingRequest}
                onClick={() => void retryPendingRequest()}
              >
                {retryingPendingRequest ? "Retrying..." : "Retry same request"}
              </button>
              <button
                className="button button--secondary"
                type="button"
                disabled={attempts.isFetching}
                onClick={() => void refreshAttemptHistory()}
              >
                Refresh attempt history
              </button>
              <button
                className="button button--secondary"
                type="button"
                disabled={retryingPendingRequest}
                onClick={abandonPendingRequest}
              >
                Abandon saved request
              </button>
            </div>
          </section>
        )}

        {options.isError || profiles.isError || attempts.isError ? (
          <section className="state-panel state-panel--error" role="alert">
            <p>
              {asMeasurementApiError(options.error ?? profiles.error ?? attempts.error).message}
            </p>
          </section>
        ) : !options.data || profiles.isPending || attempts.isPending ? (
          <p role="status">Loading measurement configuration and history...</p>
        ) : !options.data.capture_setup.processing_enabled ? (
          <p>
            Measurement is disabled until an operator explicitly configures and qualifies the
            local orthogonal rig.
          </p>
        ) : !activeProfile ? (
          <p>Activate a tested calibration profile before measuring this scan.</p>
        ) : scan.data.status !== "ready_for_processing" ? (
          <p>Upload valid top, front, and side images before measuring this scan.</p>
        ) : null}

        {attempts.data ? (
          <MeasurementAttemptList
            scanId={scanId}
            attempts={attempts.data.items}
            onReprocess={pendingRequest ? undefined : (attempt) => openMeasurementDialog(attempt)}
          />
        ) : null}
      </section>

      <p className="phase-boundary">
        Measurements are deterministic engineering estimates for the configured qualified rig,
        not certified metrology. Phase 4 AI behavior is not included.
      </p>

      <MeasurementConfirmationDialog
        open={dialogOpen}
        scanId={scanId}
        activeCalibrationProfile={
          activeProfile ? { id: activeProfile.id, name: activeProfile.name } : null
        }
        options={options.data ?? null}
        reprocessOfMeasurementId={reprocessAttempt?.id ?? null}
        onCancel={() => {
          setDialogOpen(false);
          setReprocessAttempt(null);
        }}
        onCompleted={(attempt) => {
          setDialogOpen(false);
          void navigate(
            `/scans/${encodeURIComponent(scanId)}/measurements/${encodeURIComponent(attempt.id)}`,
          );
        }}
        onPendingRequestChange={(request) => {
          setPendingRequest(request);
          setPendingRequestError(null);
        }}
      />
    </main>
  );
}
