import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  ApiRequestError,
  asApiError,
  createScan,
  getScan,
  uploadScanImages,
} from "../api/scans";
import { ImageCaptureField } from "../components/ImageCaptureField";
import { UploadErrorSummary } from "../components/UploadErrorSummary";
import type { ApiErrorResponse, ScanCreateRequest } from "../types/scans";

const missingImagesError: ApiErrorResponse = {
  code: "MISSING_REQUIRED_IMAGES",
  message: "Top, front, and side images are required for this scan.",
  recoverable: true,
  suggested_action: "Select or capture all three required views and try again.",
};

const createOutcomeUnknownError: ApiErrorResponse = {
  code: "CREATE_OUTCOME_UNKNOWN",
  message: "The local service did not confirm whether the scan was created.",
  recoverable: true,
  suggested_action: "Check History before starting another scan to avoid a duplicate.",
};

export function NewScanPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [sku, setSku] = useState("");
  const [barcode, setBarcode] = useState("");
  const [productName, setProductName] = useState("");
  const [top, setTop] = useState<File[]>([]);
  const [front, setFront] = useState<File[]>([]);
  const [side, setSide] = useState<File[]>([]);
  const [additional, setAdditional] = useState<File[]>([]);
  const [createdScanId, setCreatedScanId] = useState<string | null>(null);
  const [createOutcomeUnknown, setCreateOutcomeUnknown] = useState(false);
  const [error, setError] = useState<ApiErrorResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function saveScan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (createOutcomeUnknown) {
      setError(createOutcomeUnknownError);
      return;
    }

    if (!top[0] || !front[0] || !side[0]) {
      setError(missingImagesError);
      return;
    }

    setIsSubmitting(true);
    let scanId = createdScanId;
    try {
      if (!scanId) {
        const request: ScanCreateRequest = {
          sku: sku.trim(),
          barcode: barcode.trim() || null,
          product_name: productName.trim() || null,
        };
        const scan = await createScan(request);
        scanId = scan.id;
        setCreatedScanId(scan.id);
      }

      await uploadScanImages(scanId, {
        top: top[0],
        front: front[0],
        side: side[0],
        additional,
      });
      await queryClient.invalidateQueries({ queryKey: ["scans"] });
      navigate(`/scans/${encodeURIComponent(scanId)}`);
    } catch (caughtError) {
      const publicError = asApiError(caughtError);
      if (
        !scanId &&
        !(
          caughtError instanceof ApiRequestError &&
          caughtError.status >= 400 &&
          caughtError.status < 500
        )
      ) {
        setCreateOutcomeUnknown(true);
        setError(createOutcomeUnknownError);
        return;
      }

      if (scanId) {
        try {
          const reconciled = await getScan(scanId);
          if (reconciled.missing_required_views.length === 0) {
            await queryClient.invalidateQueries({ queryKey: ["scans"] });
            navigate(`/scans/${encodeURIComponent(scanId)}`);
            return;
          }
        } catch {
          // Preserve the original upload error when reconciliation is unavailable.
        }
      }
      setError(publicError);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page-shell page-shell--form">
      <header className="page-heading">
        <p className="eyebrow">Phase 1 - Local image intake</p>
        <h1>Start a new SKU scan</h1>
        <p>
          Create the scan record, then upload clear top, front, and side images. Files remain on
          this computer and are validated by the local service before storage.
        </p>
      </header>

      {createdScanId && error && (
        <p className="retry-note" role="status">
          The draft scan was created. Retrying will reuse this scan instead of creating another.
        </p>
      )}
      {createOutcomeUnknown && error && (
        <p className="retry-note" role="status">
          Creation could not be confirmed. <Link to="/scans">Check History</Link> before starting
          another scan.
        </p>
      )}
      <UploadErrorSummary error={error} />

      <form className="scan-form" onSubmit={saveScan}>
        <fieldset className="form-card" disabled={isSubmitting || createdScanId !== null}>
          <legend>SKU details</legend>
          <div className="form-grid">
            <label>
              <span>SKU *</span>
              <input
                name="sku"
                value={sku}
                onChange={(event) => setSku(event.target.value)}
                required
                maxLength={100}
                autoComplete="off"
              />
            </label>
            <label>
              <span>Barcode</span>
              <input
                name="barcode"
                value={barcode}
                onChange={(event) => setBarcode(event.target.value)}
                maxLength={128}
                inputMode="numeric"
                autoComplete="off"
              />
            </label>
            <label className="form-grid__wide">
              <span>Product name</span>
              <input
                name="product_name"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
                maxLength={200}
                autoComplete="off"
              />
            </label>
          </div>
        </fieldset>

        <section className="form-section" aria-labelledby="required-images-heading">
          <div className="form-section__heading">
            <h2 id="required-images-heading">Required views</h2>
            <p>Use JPEG, PNG, or WebP. The server checks size, format, decoding, and resolution.</p>
          </div>
          <div className="capture-grid">
            <ImageCaptureField
              label="Top view"
              files={top}
              onFilesChange={setTop}
              required
              disabled={isSubmitting}
              helpText="Keep the complete product visible from directly above."
            />
            <ImageCaptureField
              label="Front view"
              files={front}
              onFilesChange={setFront}
              required
              disabled={isSubmitting}
              helpText="Capture the complete front face with the phone level."
            />
            <ImageCaptureField
              label="Side view"
              files={side}
              onFilesChange={setSide}
              required
              disabled={isSubmitting}
              helpText="Capture the complete side face with the phone level."
            />
          </div>
        </section>

        <section className="form-section" aria-labelledby="additional-images-heading">
          <div className="form-section__heading">
            <h2 id="additional-images-heading">Additional images</h2>
            <p>Optional supporting angles. The local service enforces the configured limit.</p>
          </div>
          <ImageCaptureField
            label="Additional views"
            files={additional}
            onFilesChange={setAdditional}
            multiple
            disabled={isSubmitting}
          />
        </section>

        <div className="form-actions">
          <button
            className="button button--primary"
            type="submit"
            disabled={isSubmitting || createOutcomeUnknown}
          >
            {isSubmitting
              ? "Saving scan..."
              : createOutcomeUnknown
                ? "Creation unconfirmed"
              : createdScanId
                ? "Retry image upload"
                : "Create scan and upload images"}
          </button>
          <p>Images are uploaded only when you submit this form.</p>
        </div>
      </form>
    </main>
  );
}
