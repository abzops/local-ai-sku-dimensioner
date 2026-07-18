import type { MeasurementAttemptDetailResponse } from "../types/measurements";
import { MeasurementPreview } from "./MeasurementPreview";

const mm = (value: number | null) => (value === null ? "Unavailable" : `${value.toFixed(1)} mm`);

export function MeasurementEvidence({ attempt }: { attempt: MeasurementAttemptDetailResponse }) {
  if (attempt.status === "processing") {
    return (
      <section className="state-panel" role="status">
        <h2>Measurement is processing</h2>
        <p>This is the actual persisted state. No estimated progress or fake timer is shown.</p>
      </section>
    );
  }
  if (attempt.status === "failed") {
    return (
      <section className="state-panel state-panel--error" role="alert">
        <h2>Measurement failed safely</h2>
        <p>{attempt.failure?.message}</p>
        <p>{attempt.failure?.suggested_action}</p>
        {attempt.failure?.view ? <p>Required view: {attempt.failure.view}</p> : null}
        {attempt.warnings.map((warning) => <p key={warning}>{warning}</p>)}
      </section>
    );
  }

  return (
    <div>
      <section className="detail-card" aria-labelledby="final-dimensions">
        <h2 id="final-dimensions">Deterministic dimensions</h2>
        <dl className="metadata-list metadata-list--detail">
          <div><dt>Length</dt><dd>{mm(attempt.final_dimensions?.length_mm ?? null)}</dd></div>
          <div><dt>Width</dt><dd>{mm(attempt.final_dimensions?.width_mm ?? null)}</dd></div>
          <div><dt>Height</dt><dd>{mm(attempt.final_dimensions?.height_mm ?? null)}</dd></div>
          <div><dt>Overall uncertainty</dt><dd>{mm(attempt.overall_uncertainty_mm)}</dd></div>
          <div><dt>Engineering quality</dt><dd>{attempt.overall_quality?.score.toFixed(2)}</dd></div>
        </dl>
        <p>Quality is engineering evidence, not a probability or certified accuracy claim.</p>
      </section>

      {attempt.dimension_results.map((result) => (
        <article className="detail-card" key={result.dimension}>
          <h3>{result.dimension}</h3>
          <p>
            {mm(result.value_mm)} - uncertainty {mm(result.uncertainty_mm)} - {result.validation_status}
          </p>
          <p>
            Views: {result.contributing_views.join(" + ")} - disagreement {result.absolute_disagreement_mm.toFixed(1)} mm / {result.relative_disagreement_percent.toFixed(1)}%
          </p>
          <p>Reconciliation: {result.reconciliation_rule.replaceAll("_", " ")}</p>
          {result.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </article>
      ))}

      <section aria-labelledby="view-evidence">
        <h2 id="view-evidence">Per-view evidence</h2>
        {attempt.per_view_measurements.map((view) => (
          <details className="detail-card" key={view.view}>
            <summary>
              {view.view} - quality {view.quality.score.toFixed(2)} - uncertainty {view.uncertainty.total_mm.toFixed(1)} mm
            </summary>
            <dl className="metadata-list">
              <div><dt>Marker</dt><dd>{view.marker.dictionary} ID {view.marker.marker_id}</dd></div>
              <div><dt>Perspective ratio</dt><dd>{view.marker.perspective_ratio.toFixed(2)}</dd></div>
              <div><dt>Rectified plane</dt><dd>{view.rectification.physical_width_mm} x {view.rectification.physical_height_mm} mm</dd></div>
              <div><dt>Foreground area</dt><dd>{view.foreground.contour_area_mm2.toFixed(1)} mm2</dd></div>
              <div><dt>Mask stability</dt><dd>{view.foreground.mask_stability.toFixed(2)}</dd></div>
            </dl>
            {view.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </details>
        ))}
      </section>

      <section aria-labelledby="previews">
        <h2 id="previews">Annotated local previews</h2>
        {attempt.previews.map((preview) => (
          <MeasurementPreview preview={preview} key={preview.view} />
        ))}
      </section>
    </div>
  );
}
