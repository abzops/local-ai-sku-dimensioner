import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { asMeasurementApiError, getMeasurementAttempt } from "../api/measurements";
import { MeasurementEvidence } from "../components/MeasurementEvidence";

export function MeasurementResultPage() {
  const { scanId = "", measurementId = "" } = useParams();
  const query = useQuery({
    queryKey: ["measurement", scanId, measurementId],
    queryFn: ({ signal }) => getMeasurementAttempt(scanId, measurementId, signal),
    enabled: Boolean(scanId && measurementId),
  });

  if (query.isPending) {
    return (
      <main className="page-shell">
        <p className="state-panel" role="status">Loading measurement evidence...</p>
      </main>
    );
  }
  if (query.isError) {
    const error = asMeasurementApiError(query.error);
    return (
      <main className="page-shell">
        <section className="state-panel state-panel--error" role="alert">
          <h1>Measurement unavailable</h1>
          <p>{error.message}</p>
          <p>{error.suggested_action}</p>
        </section>
      </main>
    );
  }

  const attempt = query.data;
  return (
    <main className="page-shell">
      <header className="page-heading page-heading--split">
        <div>
          <p className="eyebrow">Phase 3 - Immutable attempt</p>
          <h1>Measurement evidence</h1>
          <p>
            {attempt.calibration_profile_name} - rig {attempt.capture_setup_id} v
            {attempt.capture_setup_version}
          </p>
        </div>
        <Link className="text-link" to={`/scans/${encodeURIComponent(scanId)}`}>
          Return to scan
        </Link>
      </header>
      {attempt.is_stale ? (
        <section className="state-panel" role="note">
          <h2>This result is stale</h2>
          <p>
            {attempt.stale_reasons.join(", ")}. Earlier evidence remains immutable; explicitly
            reprocess from the scan page.
          </p>
        </section>
      ) : null}
      <MeasurementEvidence attempt={attempt} />
      <p className="phase-boundary">
        Deterministic engineering estimate only. No AI, review, approval, export, or certified
        metrology behavior is included.
      </p>
    </main>
  );
}
