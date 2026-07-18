import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import {
  activateCalibrationProfile,
  asCalibrationApiError,
  createCalibrationProfile,
  getCalibrationMarkerSvg,
  getCalibrationOptions,
  getCalibrationProfile,
  listCalibrationProfiles,
  testCalibrationProfile,
} from "../api/calibration";
import { CalibrationEvidence } from "../components/CalibrationEvidence";
import type {
  ArucoDictionary,
  CalibrationApiErrorResponse,
  CalibrationOptionsResponse,
  CalibrationProfileCreateRequest,
  CalibrationProfileResponse,
  CalibrationTestResponse,
} from "../types/calibration";

interface TestAttempt {
  profileId: string;
  image: File;
}

function ErrorPanel({ error }: { error: CalibrationApiErrorResponse | null }) {
  if (!error) return null;
  return (
    <section className="error-summary" role="alert">
      <p className="error-summary__code">{error.code}</p>
      <h2>{error.message}</h2>
      <p className="error-summary__action">{error.suggested_action}</p>
    </section>
  );
}

function initialRequest(options: CalibrationOptionsResponse): CalibrationProfileCreateRequest {
  return { name: "", ...options.defaults };
}

export function CalibrationPage() {
  const [options, setOptions] = useState<CalibrationOptionsResponse | null>(null);
  const [profiles, setProfiles] = useState<CalibrationProfileResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedProfile, setSelectedProfile] = useState<CalibrationProfileResponse | null>(null);
  const [createRequest, setCreateRequest] = useState<CalibrationProfileCreateRequest | null>(null);
  const [markerUrl, setMarkerUrl] = useState<string | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [result, setResult] = useState<CalibrationTestResponse | null>(null);
  const [testAttempt, setTestAttempt] = useState<TestAttempt | null>(null);
  const [error, setError] = useState<CalibrationApiErrorResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const selectedIdRef = useRef<string | null>(null);

  async function reloadProfiles(preferredId?: string) {
    const response = await listCalibrationProfiles();
    setProfiles(response.items);
    setSelectedId((current) => preferredId ?? current ?? response.items[0]?.id ?? null);
  }

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getCalibrationOptions(controller.signal), listCalibrationProfiles(controller.signal)])
      .then(([loadedOptions, loadedProfiles]) => {
        setOptions(loadedOptions);
        setCreateRequest(initialRequest(loadedOptions));
        setProfiles(loadedProfiles.items);
        setSelectedId(loadedProfiles.items[0]?.id ?? null);
      })
      .catch((caughtError) => setError(asCalibrationApiError(caughtError)))
      .finally(() => setIsLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    selectedIdRef.current = selectedId;
    setResult(null);
    setTestAttempt(null);
    setError(null);
    if (!selectedId) {
      setSelectedProfile(null);
      return;
    }
    const controller = new AbortController();
    getCalibrationProfile(selectedId, controller.signal)
      .then(setSelectedProfile)
      .catch((caughtError) => setError(asCalibrationApiError(caughtError)));
    return () => controller.abort();
  }, [selectedId]);

  useEffect(() => {
    if (!selectedProfile) {
      setMarkerUrl(null);
      return;
    }
    const controller = new AbortController();
    let url: string | null = null;
    getCalibrationMarkerSvg(selectedProfile.id, controller.signal)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setMarkerUrl(url);
      })
      .catch((caughtError) => {
        if (!controller.signal.aborted) setError(asCalibrationApiError(caughtError));
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [selectedProfile]);

  useEffect(() => {
    if (!image) {
      setImagePreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(image);
    setImagePreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const activeProfile = useMemo(() => profiles.find((profile) => profile.is_active) ?? null, [profiles]);

  function updateRequest<K extends keyof CalibrationProfileCreateRequest>(key: K, value: CalibrationProfileCreateRequest[K]) {
    setCreateRequest((current) => current ? { ...current, [key]: value } : current);
  }

  async function createProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createRequest) return;
    setIsCreating(true);
    setError(null);
    try {
      const created = await createCalibrationProfile({ ...createRequest, name: createRequest.name.trim() });
      await reloadProfiles(created.id);
      setCreateRequest(options ? initialRequest(options) : null);
    } catch (caughtError) {
      setError(asCalibrationApiError(caughtError));
    } finally {
      setIsCreating(false);
    }
  }

  async function activateSelected() {
    if (!selectedProfile) return;
    setIsActivating(true);
    setError(null);
    try {
      const activated = await activateCalibrationProfile(selectedProfile.id);
      setSelectedProfile(activated);
      await reloadProfiles(activated.id);
    } catch (caughtError) {
      setError(asCalibrationApiError(caughtError));
    } finally {
      setIsActivating(false);
    }
  }

  async function runCalibrationTest(attempt: TestAttempt) {
    setIsTesting(true);
    setError(null);
    setResult(null);
    setTestAttempt(attempt);
    try {
      const response = await testCalibrationProfile(attempt.profileId, attempt.image);
      if (selectedIdRef.current === attempt.profileId) setResult(response);
    } catch (caughtError) {
      if (selectedIdRef.current === attempt.profileId) {
        setError(asCalibrationApiError(caughtError));
      }
    } finally {
      setIsTesting(false);
    }
  }

  function submitTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProfile || !image) {
      setError({ code: "IMAGE_REQUIRED", message: "Choose one marker image before testing.", recoverable: true, suggested_action: "Capture or select one JPEG, PNG, or WebP image." });
      return;
    }
    void runCalibrationTest({ profileId: selectedProfile.id, image });
  }

  if (isLoading) {
    return <main className="page-shell"><section className="state-panel" role="status"><h1>Loading calibration tools</h1><p>Reading local marker options and profiles.</p></section></main>;
  }

  return (
    <main className="page-shell page-shell--form calibration-page">
      <header className="page-heading">
        <p className="eyebrow">Phase 2 - Reference marker</p>
        <h1>Calibrate the printed marker</h1>
        <p>Create an immutable marker profile, print it at actual size, and verify its detection from one local image before later geometry phases.</p>
      </header>

      <ErrorPanel error={error} />

      {createRequest && options && (
        <form className="form-section" onSubmit={createProfile}>
          <div className="form-section__heading"><h2>Create a calibration profile</h2><p>Profiles cannot be edited after creation. Activation is the only profile mutation.</p></div>
          <div className="form-card form-grid calibration-profile-form">
            <label className="form-grid__wide"><span>Profile name *</span><input required maxLength={100} value={createRequest.name} onChange={(event) => updateRequest("name", event.target.value)} /></label>
            <label><span>ArUco dictionary</span><select value={createRequest.dictionary} onChange={(event) => updateRequest("dictionary", event.target.value as ArucoDictionary)}>{options.dictionaries.map((dictionary) => <option key={dictionary}>{dictionary}</option>)}</select></label>
            <label><span>Marker ID</span><input type="number" min={options.marker_id_min} max={options.marker_id_max} value={createRequest.marker_id} onChange={(event) => updateRequest("marker_id", event.target.valueAsNumber)} /></label>
            <label><span>Marker side (mm)</span><input type="number" min="10" max="300" step="0.1" value={createRequest.marker_size_mm} onChange={(event) => updateRequest("marker_size_mm", event.target.valueAsNumber)} /></label>
            <label><span>Minimum marker side (px)</span><input type="number" min="24" max="4096" value={createRequest.minimum_marker_side_px} onChange={(event) => updateRequest("minimum_marker_side_px", event.target.valueAsNumber)} /></label>
            <label><span>Maximum perspective ratio</span><input type="number" min="1" max="10" step="0.1" value={createRequest.maximum_perspective_ratio} onChange={(event) => updateRequest("maximum_perspective_ratio", event.target.valueAsNumber)} /></label>
            <label><span>Maximum homography condition number</span><input type="number" min="10" max="1000000000000" step="1" value={createRequest.maximum_homography_condition_number} onChange={(event) => updateRequest("maximum_homography_condition_number", event.target.valueAsNumber)} /></label>
            <label><span>Maximum marker-edge residual (px)</span><input type="number" min="0.1" max="20" step="0.1" value={createRequest.maximum_marker_edge_residual_px} onChange={(event) => updateRequest("maximum_marker_edge_residual_px", event.target.valueAsNumber)} /></label>
            <label><span>Rectified pixels per millimetre</span><input type="number" min="1" max="6" step="0.1" value={createRequest.rectified_pixels_per_mm} onChange={(event) => updateRequest("rectified_pixels_per_mm", event.target.valueAsNumber)} /></label>
          </div>
          <button className="button button--primary" type="submit" disabled={isCreating}>{isCreating ? "Creating profile..." : "Create profile"}</button>
        </form>
      )}

      <section className="form-section" aria-labelledby="profiles-heading">
        <div className="form-section__heading"><h2 id="profiles-heading">Calibration profiles</h2><p>{activeProfile ? `Active: ${activeProfile.name}` : "No profile is active yet."}</p></div>
        {profiles.length === 0 ? <div className="state-panel"><h3>No calibration profiles</h3><p>Create the first immutable profile above.</p></div> : (
          <div className="calibration-profile-layout">
            <div className="calibration-profile-list" role="list" aria-label="Calibration profiles">
              {profiles.map((profile) => <button key={profile.id} type="button" className={profile.id === selectedId ? "profile-choice profile-choice--selected" : "profile-choice"} onClick={() => { setResult(null); setTestAttempt(null); setError(null); selectedIdRef.current = profile.id; setSelectedId(profile.id); }}><span>{profile.name}</span><small>{profile.dictionary} · ID {profile.marker_id}{profile.is_active ? " · Active" : ""}</small></button>)}
            </div>
            {selectedProfile && (
              <article className="detail-card calibration-profile-detail">
                <div className="detail-card__heading"><div><p className="eyebrow">Selected profile</p><h3>{selectedProfile.name}</h3></div>{selectedProfile.is_active && <span className="quality-badge quality-badge--valid">Active</span>}</div>
                <dl className="metadata-list">
                  <div><dt>Dictionary</dt><dd>{selectedProfile.dictionary}</dd></div><div><dt>Marker ID</dt><dd>{selectedProfile.marker_id}</dd></div><div><dt>Marker side</dt><dd>{selectedProfile.marker_size_mm} mm</dd></div><div><dt>Border bits</dt><dd>{selectedProfile.border_bits}</dd></div><div><dt>Minimum side</dt><dd>{selectedProfile.minimum_marker_side_px} px</dd></div><div><dt>Perspective limit</dt><dd>{selectedProfile.maximum_perspective_ratio}</dd></div><div><dt>Condition limit</dt><dd>{selectedProfile.maximum_homography_condition_number}</dd></div><div><dt>Residual limit</dt><dd>{selectedProfile.maximum_marker_edge_residual_px} px</dd></div><div><dt>Rectified scale</dt><dd>{selectedProfile.rectified_pixels_per_mm} px/mm</dd></div><div><dt>Created</dt><dd>{selectedProfile.created_at}</dd></div><div><dt>Activated</dt><dd>{selectedProfile.activated_at ?? "Never"}</dd></div>
                </dl>
                {!selectedProfile.is_active && <button className="button button--secondary" type="button" disabled={isActivating} onClick={() => void activateSelected()}>{isActivating ? "Activating..." : "Activate profile"}</button>}
              </article>
            )}
          </div>
        )}
      </section>

      {selectedProfile && (
        <section className="form-section" aria-labelledby="marker-heading">
          <div className="form-section__heading"><h2 id="marker-heading">Print the reference marker</h2><p>Print at 100% or actual size with fit-to-page scaling disabled. Measure the black square with a ruler and confirm it is exactly {selectedProfile.marker_size_mm} mm on each side.</p></div>
          <div className="marker-document detail-card">{markerUrl ? <img src={markerUrl} alt={`ArUco marker ${selectedProfile.marker_id} from ${selectedProfile.dictionary}`} /> : <p role="status">Loading marker preview...</p>}<a className="button button--secondary" href={markerUrl ?? undefined} download={`aruco-${selectedProfile.dictionary}-${selectedProfile.marker_id}.svg`} aria-disabled={!markerUrl}>Download SVG</a></div>
        </section>
      )}

      {selectedProfile && (
        <form className="form-section" onSubmit={submitTest}>
          <div className="form-section__heading"><h2>Test marker detection</h2><p>Capture or select exactly one JPEG, PNG, or WebP image. It is checked locally and is not persisted.</p></div>
          <div className="calibration-capture detail-card">
            <label className="button button--secondary" htmlFor="calibration-camera">Capture or choose marker image</label>
            <input className="visually-hidden" id="calibration-camera" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(event) => setImage(event.target.files?.[0] ?? null)} />
            {imagePreviewUrl ? <figure><img src={imagePreviewUrl} alt="Selected marker image preview" /><figcaption>{image?.name}</figcaption></figure> : <p>No image selected.</p>}
          </div>
          <div className="form-actions"><button className="button button--primary" type="submit" disabled={isTesting}>{isTesting ? "Testing marker..." : "Run calibration test"}</button>{testAttempt && testAttempt.profileId === selectedProfile.id && error?.recoverable && <button className="button button--secondary" type="button" disabled={isTesting} onClick={() => void runCalibrationTest(testAttempt)}>Retry same image</button>}<p>The test does not calculate product dimensions.</p></div>
        </form>
      )}

      {result && selectedProfile && result.profile_id === selectedProfile.id && <CalibrationEvidence result={result} profileName={selectedProfile.name} />}
    </main>
  );
}
