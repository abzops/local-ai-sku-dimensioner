import { HealthStatus } from "../components/HealthStatus";

export function HomePage() {
  return (
    <main className="page-shell">
      <header className="hero">
        <p className="eyebrow">Local AI SKU Dimensioner</p>
        <h1>Geometry-first measurement, built for accountable review.</h1>
        <p className="hero__copy">
          Phase 0 establishes the local application foundation. Measurement workflows are not
          enabled yet.
        </p>
      </header>

      <HealthStatus />

      <section className="scope-card" aria-labelledby="scope-heading">
        <p className="scope-card__index">Phase 0</p>
        <div>
          <h2 id="scope-heading">Repository foundation</h2>
          <p>
            The API, local database, configuration, Windows scripts, and responsive web shell are
            available. Image capture and dimension calculation begin only in later approved phases.
          </p>
        </div>
      </section>
    </main>
  );
}

