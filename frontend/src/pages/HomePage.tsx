import { HealthStatus } from "../components/HealthStatus";
import { Link } from "react-router-dom";

export function HomePage() {
  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">Local AI SKU Dimensioner</p>
        <h1>Geometry-first measurement, built for accountable review.</h1>
        <p className="hero__copy">
          Create a local scan, capture three qualified orthogonal views, and inspect deterministic
          geometry, reconciliation, uncertainty, and annotated evidence without cloud services.
        </p>
        <div className="hero__actions">
          <Link className="button button--primary" to="/scans/new">Start a new scan</Link>
          <Link className="button button--secondary" to="/scans">View history</Link>
          <Link className="button button--secondary" to="/calibration">Calibrate marker</Link>
        </div>
      </header>

      <HealthStatus />

      <section className="scope-card" aria-labelledby="scope-heading">
        <p className="scope-card__index">Phase 3</p>
        <div>
          <h2 id="scope-heading">Experimental geometry-only measurement</h2>
          <p>
            Measurement is disabled by default and supports only an explicitly configured,
            physically qualified orthogonal rig with opaque rigid cuboids. Results are engineering
            estimates, not certified metrology. AI segmentation, review, exports, and Phase 4
            behavior remain intentionally unavailable.
          </p>
        </div>
      </section>
    </main>
  );
}
