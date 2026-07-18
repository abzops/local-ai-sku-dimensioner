import { afterEach, describe, expect, it, vi } from "vitest";

import {
  abandonPendingMeasurementRequest,
  clearPendingMeasurementRequest,
  getMeasurementAttempt,
  getMeasurementOptions,
  getMeasurementPreview,
  getPendingMeasurementRequest,
  MeasurementApiRequestError,
  prepareMeasurementRequest,
  processMeasurement,
  reconcilePendingMeasurementRequest,
} from "./measurements";
import {
  cloneFixture,
  measurementId,
  measurementOptionsFixture,
  previewPngBytes,
  profileId,
  scanId,
  succeededDetailFixture,
  succeededSummaryFixture,
} from "../test/measurementFixtures";

const generatedRequestId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const structuredFailure = {
  code: "DATABASE_UNAVAILABLE",
  message: "The local database is unavailable.",
  recoverable: true,
  suggested_action: "Check the local service and retry the same request.",
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

it("validates options and complete succeeded evidence", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(measurementOptionsFixture), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))
    .mockResolvedValueOnce(new Response(JSON.stringify(succeededDetailFixture), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

  expect((await getMeasurementOptions()).required_views).toEqual(["top", "front", "side"]);
  expect((await getMeasurementAttempt(scanId, measurementId)).final_dimensions?.length_mm).toBe(100);
});

it("accepts a capture setup version at exactly fifty characters", async () => {
  const fixture = cloneFixture(measurementOptionsFixture);
  fixture.capture_setup.version = "v".repeat(50);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(fixture), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));

  expect((await getMeasurementOptions()).capture_setup.version).toBe("v".repeat(50));
});

it.each(["v".repeat(51), "", "   "])(
  "rejects an invalid capture setup version %j",
  async (version) => {
    const fixture = cloneFixture(measurementOptionsFixture);
    fixture.capture_setup.version = version;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(fixture), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await expect(getMeasurementOptions()).rejects.toMatchObject({ status: 502 });
  },
);

it("rejects recursive unknown fields", async () => {
  const invalid = cloneFixture(succeededDetailFixture) as unknown as Record<string, unknown>;
  (invalid.final_dimensions as Record<string, unknown>).path = "C:\\private";
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(invalid), {
    status: 200,
  }));

  await expect(getMeasurementAttempt(scanId, measurementId)).rejects.toMatchObject({ status: 502 });
});

it("reuses a pending request after uncertain network rejection", async () => {
  vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
  const request = prepareMeasurementRequest(scanId, profileId, "rig-local-1");
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));

  await expect(processMeasurement(scanId, request)).rejects.toMatchObject({
    outcomeUncertain: true,
  });
  expect(prepareMeasurementRequest(scanId, profileId, "rig-local-1").request_id).toBe(
    request.request_id,
  );
  clearPendingMeasurementRequest(scanId);
});

describe.each([500, 503])("late measurement POST status %i", (status) => {
  it("keeps the canonical request and marks the outcome uncertain", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
    const request = prepareMeasurementRequest(scanId, profileId, "rig-local-1");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify(structuredFailure),
      { status, headers: { "Content-Type": "application/json" } },
    ));

    await expect(processMeasurement(scanId, request)).rejects.toMatchObject({
      status,
      outcomeUncertain: true,
      payload: structuredFailure,
    });
    expect(getPendingMeasurementRequest(scanId)).toEqual(request);
  });
});

it("retries an uncertain POST with the identical request UUID and body", async () => {
  vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
  const request = prepareMeasurementRequest(scanId, profileId, "rig-local-1");
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
    JSON.stringify(structuredFailure),
    { status: 503, headers: { "Content-Type": "application/json" } },
  ));

  await expect(processMeasurement(scanId, request)).rejects.toBeInstanceOf(
    MeasurementApiRequestError,
  );
  const retry = prepareMeasurementRequest(scanId, profileId, "rig-local-1");
  await expect(processMeasurement(scanId, retry)).rejects.toBeInstanceOf(
    MeasurementApiRequestError,
  );

  expect(retry.request_id).toBe(request.request_id);
  const firstBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
  const secondBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
  expect(secondBody).toEqual(firstBody);
  expect(secondBody.request_id).toBe(generatedRequestId);
});

it("clears a pending request when history contains its request UUID", () => {
  vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
  prepareMeasurementRequest(scanId, profileId, "rig-local-1");
  const matchingAttempt = { ...succeededSummaryFixture, request_id: generatedRequestId };

  expect(reconcilePendingMeasurementRequest(scanId, [matchingAttempt])).toBeNull();
  expect(getPendingMeasurementRequest(scanId)).toBeNull();
});

it("clears a pending request only after the user explicitly abandons it", () => {
  vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
  prepareMeasurementRequest(scanId, profileId, "rig-local-1");

  abandonPendingMeasurementRequest(scanId);

  expect(getPendingMeasurementRequest(scanId)).toBeNull();
});

it("treats a definite validation response as non-uncertain", async () => {
  vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
  const request = prepareMeasurementRequest(scanId, profileId, "rig-local-1");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    code: "CAPTURE_SETUP_MISMATCH",
    message: "The capture setup no longer matches.",
    recoverable: true,
    suggested_action: "Refresh the measurement options.",
  }), { status: 422, headers: { "Content-Type": "application/json" } }));

  await expect(processMeasurement(scanId, request)).rejects.toMatchObject({
    status: 422,
    outcomeUncertain: false,
  });
});

it("keeps the request when a successful response belongs to a different UUID", async () => {
  vi.stubGlobal("crypto", { randomUUID: () => generatedRequestId });
  const request = prepareMeasurementRequest(scanId, profileId, "rig-local-1");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
    JSON.stringify(succeededDetailFixture),
    { status: 200, headers: { "Content-Type": "application/json" } },
  ));

  await expect(processMeasurement(scanId, request)).rejects.toMatchObject({
    status: 502,
    outcomeUncertain: true,
  });
  expect(getPendingMeasurementRequest(scanId)).toEqual(request);
});

it("validates PNG signature, dimensions, and exact byte size", async () => {
  const descriptor = succeededDetailFixture.previews[0];
  const bytes = previewPngBytes();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(bytes, {
    status: 200,
    headers: { "Content-Type": "image/png", "Content-Length": "24" },
  }));

  expect((await getMeasurementPreview(descriptor)).size).toBe(24);
  bytes[0] = 0;
  vi.mocked(fetch).mockResolvedValue(new Response(bytes, {
    status: 200,
    headers: { "Content-Type": "image/png", "Content-Length": "24" },
  }));
  await expect(getMeasurementPreview(descriptor)).rejects.toBeInstanceOf(
    MeasurementApiRequestError,
  );
});
