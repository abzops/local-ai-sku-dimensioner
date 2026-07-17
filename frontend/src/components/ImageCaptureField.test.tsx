import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImageCaptureField } from "./ImageCaptureField";

function Harness({ multiple = false }: { multiple?: boolean }) {
  const [files, setFiles] = useState<File[]>([]);
  return (
    <ImageCaptureField
      label="Top view"
      files={files}
      onFilesChange={setFiles}
      multiple={multiple}
    />
  );
}

describe("ImageCaptureField", () => {
  const createObjectUrl = vi.fn((file: File) => `blob:${file.name}`);
  const revokeObjectUrl = vi.fn();

  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
  });

  afterEach(() => {
    createObjectUrl.mockClear();
    revokeObjectUrl.mockClear();
  });

  it("provides separate gallery and rear-camera inputs", () => {
    render(<Harness multiple />);

    const gallery = screen.getByLabelText("Top view from files");
    const camera = screen.getByLabelText("Top view from camera");
    expect(gallery).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    expect(gallery).toHaveAttribute("multiple");
    expect(camera).toHaveAttribute("capture", "environment");
    expect(camera).not.toHaveAttribute("multiple");
  });

  it("creates a local preview and revokes its object URL after removal", async () => {
    render(<Harness />);
    const file = new File(["image"], "top.jpg", { type: "image/jpeg" });

    fireEvent.change(screen.getByLabelText("Top view from files"), { target: { files: [file] } });

    expect(await screen.findByAltText("Top view preview 1")).toHaveAttribute("src", "blob:top.jpg");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(screen.queryByAltText("Top view preview 1")).not.toBeInTheDocument());
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:top.jpg");
  });
});
