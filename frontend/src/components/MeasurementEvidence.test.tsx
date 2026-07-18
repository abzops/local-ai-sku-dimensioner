import { render, screen } from "@testing-library/react"; import { MeasurementEvidence } from "./MeasurementEvidence"; import { failedDetailFixture, processingDetailFixture, succeededDetailFixture } from "../test/measurementFixtures";
vi.mock("./MeasurementPreview", () => ({ MeasurementPreview: () => <div>preview</div> }));
it("renders succeeded dimensions and evidence", () => { render(<MeasurementEvidence attempt={succeededDetailFixture} />); expect(screen.getByText("Deterministic dimensions")).toBeInTheDocument(); expect(screen.getAllByText(/100.0 mm/).length).toBeGreaterThan(0); });
it("renders honest processing and structured failure states", () => { const { rerender } = render(<MeasurementEvidence attempt={processingDetailFixture} />); expect(screen.getByText(/No estimated progress/)).toBeInTheDocument(); rerender(<MeasurementEvidence attempt={failedDetailFixture} />); expect(screen.getByRole("alert")).toHaveTextContent("cropped"); });
import { expect, it, vi } from "vitest";
