import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { asApiError, listScans } from "../api/scans";
import { ScanStatusBadge } from "../components/ScanStatusBadge";

const pageSize = 20;

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function HistoryPage() {
  const [offset, setOffset] = useState(0);
  const scans = useQuery({
    queryKey: ["scans", { offset, limit: pageSize }],
    queryFn: ({ signal }) => listScans({ offset, limit: pageSize }, signal),
  });

  return (
    <main className="page-shell">
      <header className="page-heading page-heading--split">
        <div>
          <p className="eyebrow">Local scan history</p>
          <h1>Scans</h1>
          <p>Review saved scan records and their image intake status.</p>
        </div>
        <Link className="button button--primary" to="/scans/new">
          New scan
        </Link>
      </header>

      {scans.isPending && <p className="state-panel" role="status">Loading scans...</p>}
      {scans.isError && (
        <section className="state-panel state-panel--error" role="alert">
          <h2>History unavailable</h2>
          <p>{asApiError(scans.error).message}</p>
        </section>
      )}
      {scans.data && scans.data.items.length === 0 && (
        <section className="state-panel">
          <h2>No scans yet</h2>
          <p>Create a scan to start the local history.</p>
        </section>
      )}
      {scans.data && scans.data.items.length > 0 && (
        <>
          <div className="history-list" aria-label="Scan history">
            {scans.data.items.map((scan) => (
              <article className="history-card" key={scan.id}>
                <div className="history-card__title">
                  <div>
                    <p className="history-card__sku">{scan.sku}</p>
                    <h2>{scan.product_name || "Unnamed product"}</h2>
                  </div>
                  <ScanStatusBadge status={scan.status} />
                </div>
                <dl className="metadata-list">
                  <div><dt>Barcode</dt><dd>{scan.barcode || "Not provided"}</dd></div>
                  <div><dt>Images</dt><dd>{scan.image_count}</dd></div>
                  <div>
                    <dt>Missing views</dt>
                    <dd>{scan.missing_required_views.join(", ") || "None"}</dd>
                  </div>
                  <div><dt>Updated</dt><dd>{formatDate(scan.updated_at)}</dd></div>
                </dl>
                <Link className="text-link" to={`/scans/${encodeURIComponent(scan.id)}`}>
                  Open scan <span aria-hidden="true">-&gt;</span>
                </Link>
              </article>
            ))}
          </div>
          <nav className="pagination" aria-label="History pages">
            <button
              className="button button--secondary"
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
            >
              Previous
            </button>
            <p>
              Showing {offset + 1}-{Math.min(offset + scans.data.items.length, scans.data.total)} of{" "}
              {scans.data.total}
            </p>
            <button
              className="button button--secondary"
              type="button"
              disabled={offset + pageSize >= scans.data.total}
              onClick={() => setOffset(offset + pageSize)}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </main>
  );
}
