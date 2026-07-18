import { Link } from "react-router-dom";

import type { MeasurementAttemptSummaryResponse } from "../types/measurements";

export function MeasurementAttemptList({
  scanId,
  attempts,
  onReprocess,
}: {
  scanId: string;
  attempts: MeasurementAttemptSummaryResponse[];
  onReprocess?: (attempt: MeasurementAttemptSummaryResponse) => void;
}) {
  if (attempts.length === 0) {
    return <p>No measurement attempts yet.</p>;
  }
  return (
    <div className="history-list" aria-label="Immutable measurement attempts">
      {attempts.map((attempt) => (
        <article className="history-card" key={attempt.id}>
          <div className="history-card__title">
            <h3>
              {attempt.status === "succeeded"
                ? `${attempt.length_mm} x ${attempt.width_mm} x ${attempt.height_mm} mm`
                : attempt.status === "failed"
                  ? `Failed: ${attempt.failure_code}`
                  : "Processing"}
            </h3>
            <span
              className={`quality-badge ${
                attempt.status === "succeeded" ? "quality-badge--valid" : ""
              }`}
            >
              {attempt.status}
            </span>
          </div>
          <p>
            {new Date(attempt.created_at).toLocaleString()} - {attempt.calibration_profile_name}
          </p>
          {attempt.is_stale ? <p role="note">Stale: {attempt.stale_reasons.join(", ")}</p> : null}
          <div className="form-actions">
            <Link
              className="text-link"
              to={`/scans/${encodeURIComponent(scanId)}/measurements/${encodeURIComponent(attempt.id)}`}
            >
              View evidence
            </Link>
            {attempt.status !== "processing" && onReprocess ? (
              <button
                className="button button--secondary"
                type="button"
                onClick={() => onReprocess(attempt)}
              >
                Reprocess from this immutable attempt
              </button>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
