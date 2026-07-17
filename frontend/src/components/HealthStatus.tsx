import { useQuery } from "@tanstack/react-query";

import { getHealth } from "../api/health";

export function HealthStatus() {
  const health = useQuery({
    queryKey: ["system-health"],
    queryFn: ({ signal }) => getHealth(signal),
    refetchInterval: 30_000,
  });

  if (health.isPending) {
    return (
      <section className="status-card status-card--checking" aria-live="polite">
        <span className="status-dot" aria-hidden="true" />
        <div>
          <p className="status-label">System status</p>
          <h2>Checking local services…</h2>
        </div>
      </section>
    );
  }

  if (health.isError) {
    return (
      <section className="status-card status-card--error" role="alert">
        <span className="status-dot" aria-hidden="true" />
        <div>
          <p className="status-label">System status</p>
          <h2>Local service unavailable</h2>
          <p>{health.error.message}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="status-card status-card--ok" aria-live="polite">
      <span className="status-dot" aria-hidden="true" />
      <div className="status-card__content">
        <div>
          <p className="status-label">System status</p>
          <h2>Foundation ready</h2>
        </div>
        <dl className="status-details">
          <div>
            <dt>API</dt>
            <dd>Online · v{health.data.version}</dd>
          </div>
          <div>
            <dt>Database</dt>
            <dd>Ready · {health.data.database.revision}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

