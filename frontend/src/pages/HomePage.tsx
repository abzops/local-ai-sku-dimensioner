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
        </div>
      </header>

      <HealthStatus />

      <section className="scope-card" aria-labelledby="scope-heading">
        <p className="scope-card__index">Phase 1</p>
        <div>
          <h2 id="scope-heading">Scan and image intake</h2>
          <p>
            Scan metadata and validated images persist locally. Measurement, marker detection, AI,
            processing, review, and exports remain intentionally unavailable.
          </p>
        </div>
      </section>
    </main>
  );
}
