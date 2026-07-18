import { useEffect, useState } from "react";

import { asMeasurementApiError, getMeasurementPreview } from "../api/measurements";
import type { PreviewDescriptorResponse } from "../types/measurements";

export function MeasurementPreview({ preview }: { preview: PreviewDescriptorResponse }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setUrl(null);
    setError(null);
    getMeasurementPreview(preview, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(asMeasurementApiError(caught).message);
        }
      });
    return () => {
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [preview]);

  return (
    <figure className="detail-card">
      {url ? (
        <img
          src={url}
          width={preview.width_px}
          height={preview.height_px}
          alt={`${preview.view} view annotated deterministic measurement evidence`}
        />
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <p role="status">Loading {preview.view} preview...</p>
      )}
      <figcaption>
        {preview.view} - annotated local preview - {preview.width_px} x {preview.height_px}px
      </figcaption>
    </figure>
  );
}
