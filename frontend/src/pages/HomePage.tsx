import { HealthStatus } from "../components/HealthStatus";
import { Link } from "react-router-dom";

export function HomePage() {
  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">Local AI SKU Dimensioner</p>
        <h1>Geometry-first measurement, built for accountable review.</h1>
        <p className="hero__copy">
          Create a local scan record, capture its required views, and verify that each image is
          safely stored before later measurement phases begin.
        </p>
        <div className="hero__actions">
          <Link className="button button--primary" to="/scans/new">Start a new scan</Link>
          <Link className="button button--secondary" to="/scans">View history</Link>
          <Link className="button button--secondary" to="/calibration">Calibrate marker</Link>
        </div>
      </header>

      <HealthStatus />

      <section className="scope-card" aria-labelledby="scope-heading">
        <p className="scope-card__index">Phase 2</p>
        <div>
          <h2 id="scope-heading">Local marker calibration</h2>
          <p>
            Scan intake remains available. You can now create and test a deterministic printed
            ArUco reference profile. Product measurement, AI, processing, review, and exports remain
            intentionally unavailable.
          </p>
        </div>
      </section>
    </main>
  );
}
