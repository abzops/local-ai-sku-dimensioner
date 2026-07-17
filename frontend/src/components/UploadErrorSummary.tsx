import type { ApiErrorResponse } from "../types/scans";

interface UploadErrorSummaryProps {
  error: ApiErrorResponse | null;
}

export function UploadErrorSummary({ error }: UploadErrorSummaryProps) {
  if (!error) {
    return null;
  }

  return (
    <section className="error-summary" role="alert" aria-labelledby="upload-error-heading">
      <p className="error-summary__code">{error.code}</p>
      <h2 id="upload-error-heading">The scan could not be saved</h2>
      <p>{error.message}</p>
      <p className="error-summary__action">{error.suggested_action}</p>
    </section>
  );
}
