import type {
  CalibrationTestResponse,
  EdgeName,
  Matrix3x3,
} from "../types/calibration";

const edges: EdgeName[] = ["top", "right", "bottom", "left"];

function formatNumber(value: number, maximumFractionDigits = 4): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

function MatrixTable({ label, matrix }: { label: string; matrix: Matrix3x3 }) {
  return (
    <div className="calibration-matrix">
      <h3>{label}</h3>
      <div className="calibration-table-scroll">
        <table aria-label={label}>
          <tbody>
            {matrix.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((value, columnIndex) => (
                  <td key={columnIndex}>{formatNumber(value, 6)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CalibrationEvidence({
  result,
  profileName,
}: {
  result: CalibrationTestResponse;
  profileName: string;
}) {
  const quality = result.marker_edge_quality;
  return (
    <section className="calibration-results" aria-labelledby="calibration-results-heading">
      <div className="form-section__heading">
        <p className="eyebrow">Deterministic marker evidence</p>
        <h2 id="calibration-results-heading">Calibration test result</h2>
        <p>
          This evidence describes the printed marker plane only. It is not a product measurement or
          certified camera calibration.
        </p>
      </div>

      <dl className="metadata-list metadata-list--calibration">
        <div><dt>Profile</dt><dd>{profileName}</dd></div>
        <div><dt>Profile ID</dt><dd>{result.profile_id}</dd></div>
        <div><dt>Dictionary</dt><dd>{result.dictionary}</dd></div>
        <div><dt>Marker ID</dt><dd>{result.marker_id}</dd></div>
        <div><dt>Physical marker side</dt><dd>{formatNumber(result.marker_size_mm)} mm</dd></div>
        <div><dt>Orientation</dt><dd>{formatNumber(result.orientation_degrees)} degrees</dd></div>
        <div><dt>Perspective ratio</dt><dd>{formatNumber(result.perspective_ratio)}</dd></div>
        <div><dt>Homography condition number</dt><dd>{formatNumber(result.homography_condition_number, 6)}</dd></div>
        <div><dt>Rectified output</dt><dd>{result.rectified_width_px} × {result.rectified_height_px} px</dd></div>
        <div><dt>Rectified scale</dt><dd>{formatNumber(result.rectified_pixels_per_mm)} px/mm</dd></div>
      </dl>

      <div className="calibration-evidence-grid">
        <section className="detail-card" aria-labelledby="ordered-corners-heading">
          <h3 id="ordered-corners-heading">Ordered marker corners</h3>
          <div className="calibration-table-scroll">
            <table>
              <thead><tr><th>Canonical label</th><th>X (px)</th><th>Y (px)</th></tr></thead>
              <tbody>
                {result.ordered_corners.map((corner) => (
                  <tr key={corner.label}>
                    <th scope="row">{corner.label.replaceAll("_", " ")}</th>
                    <td>{formatNumber(corner.x_px)}</td>
                    <td>{formatNumber(corner.y_px)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="detail-card" aria-labelledby="edge-lengths-heading">
          <h3 id="edge-lengths-heading">Marker edge lengths</h3>
          <dl className="calibration-edge-list">
            {edges.map((edge) => (
              <div key={edge}><dt>{edge}</dt><dd>{formatNumber(result.edge_lengths_px[edge])} px</dd></div>
            ))}
          </dl>
        </section>
      </div>

      <section className="detail-card" aria-labelledby="edge-quality-heading">
        <div className="detail-card__heading">
          <div>
            <h3 id="edge-quality-heading">Marker-edge localization quality</h3>
            <p>{quality.description}</p>
          </div>
          <span className={quality.valid ? "quality-badge quality-badge--valid" : "quality-badge"}>
            {quality.valid ? "Within threshold" : "Outside threshold"}
          </span>
        </div>
        <dl className="metadata-list metadata-list--calibration">
          <div><dt>Metric</dt><dd>{quality.metric_name}</dd></div>
          <div><dt>RMS residual</dt><dd>{formatNumber(quality.rms_px)} px</dd></div>
          <div><dt>Maximum residual</dt><dd>{formatNumber(quality.maximum_px)} px</dd></div>
          <div><dt>Threshold</dt><dd>{formatNumber(quality.threshold_px)} px</dd></div>
          <div><dt>Sample count</dt><dd>{quality.sample_count}</dd></div>
        </dl>
        <dl className="calibration-edge-list calibration-edge-list--quality">
          {edges.map((edge) => (
            <div key={edge}><dt>{edge} edge RMS</dt><dd>{formatNumber(quality.per_edge_rms_px[edge])} px</dd></div>
          ))}
        </dl>
      </section>

      <section className="detail-card" aria-labelledby="homography-heading">
        <h3 id="homography-heading">Marker-plane homographies</h3>
        <div className="calibration-matrix-grid">
          <MatrixTable label="Image pixels to marker millimetres" matrix={result.image_to_marker_mm} />
          <MatrixTable label="Marker millimetres to image pixels" matrix={result.marker_mm_to_image} />
        </div>
      </section>

      <div className="calibration-preview-grid">
        <figure className="detail-card">
          <img
            src={`data:${result.annotated_preview.media_type};base64,${result.annotated_preview.data_base64}`}
            alt="Annotated marker detection with canonical corners"
          />
          <figcaption>Annotated detection — {result.annotated_preview.width_px} × {result.annotated_preview.height_px} px</figcaption>
        </figure>
        <figure className="detail-card">
          <img
            src={`data:${result.rectified_preview.media_type};base64,${result.rectified_preview.data_base64}`}
            alt="Perspective-rectified marker preview"
          />
          <figcaption>Rectified marker — {result.rectified_preview.width_px} × {result.rectified_preview.height_px} px</figcaption>
        </figure>
      </div>
    </section>
  );
}
