export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  database: {
    status: "ok";
    revision: string;
  };
}

interface ErrorResponse {
  message?: string;
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (!isRecord(value) || !isRecord(value.database)) {
    return false;
  }
  return (
    value.status === "ok" &&
    typeof value.service === "string" &&
    typeof value.version === "string" &&
    value.database.status === "ok" &&
    typeof value.database.revision === "string"
  );
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/health`, {
    headers: { Accept: "application/json" },
    signal,
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const error = isRecord(payload) ? (payload as ErrorResponse) : null;
    throw new Error(error?.message ?? `Health request failed with status ${response.status}`);
  }
  if (!isHealthResponse(payload)) {
    throw new Error("The health endpoint returned an invalid response.");
  }
  return payload;
}

