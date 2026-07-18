import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createAppQueryClient } from "../app/queryClient";
import { HealthStatus } from "./HealthStatus";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

function nonJsonResponse(status: number): Response {
  return {
    ok: false,
    status,
    json: vi.fn().mockRejectedValue(new SyntaxError("invalid JSON")),
  } as unknown as Response;
}

function renderStatus() {
  const client = createAppQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <HealthStatus />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HealthStatus", () => {
  it("shows the loading state while health is pending", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValue(new Promise<Response>(() => undefined)),
    );

    renderStatus();

    expect(screen.getByRole("heading", { name: /Checking local services/ })).toBeVisible();
  });

  it("shows application and database readiness", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          status: "ok",
          service: "Local AI SKU Dimensioner",
          version: "0.1.0",
          database: { status: "ok", revision: "0003_phase2_calibration_profiles" },
        }),
      ),
    );

    renderStatus();

    expect(await screen.findByRole("heading", { name: "Foundation ready" })).toBeVisible();
    expect(screen.getByText("Online · v0.1.0")).toBeVisible();
    expect(screen.getByText("Ready · 0003_phase2_calibration_profiles")).toBeVisible();
  });

  it("shows a safe backend failure message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            code: "DATABASE_UNAVAILABLE",
            message: "The local database is unavailable or has not been initialized.",
          },
          503,
        ),
      ),
    );

    renderStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent("Local service unavailable");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The local database is unavailable or has not been initialized.",
    );
  });

  it("shows a network rejection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("Local connection refused")),
    );

    renderStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent("Local connection refused");
  });

  it("rejects a malformed successful response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ status: "ok", database: null })),
    );

    renderStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The health endpoint returned an invalid response.",
    );
  });

  it("uses a safe status message for a non-JSON error response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(nonJsonResponse(502)));

    renderStatus();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Health request failed with status 502",
    );
  });
});
