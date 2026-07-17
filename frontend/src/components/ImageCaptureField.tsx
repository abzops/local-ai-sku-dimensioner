import { useEffect, useId, useState, type ChangeEvent } from "react";

const acceptedImages = "image/jpeg,image/png,image/webp";

interface ImageCaptureFieldProps {
  label: string;
  files: File[];
  onFilesChange: (files: File[]) => void;
  required?: boolean;
  multiple?: boolean;
  disabled?: boolean;
  helpText?: string;
}

interface Preview {
  file: File;
  url: string;
}

export function ImageCaptureField({
  label,
  files,
  onFilesChange,
  required = false,
  multiple = false,
  disabled = false,
  helpText,
}: ImageCaptureFieldProps) {
  const inputId = useId();
  const [previews, setPreviews] = useState<Preview[]>([]);

  useEffect(() => {
    const nextPreviews = files.map((file) => ({ file, url: URL.createObjectURL(file) }));
    setPreviews(nextPreviews);
    return () => nextPreviews.forEach((preview) => URL.revokeObjectURL(preview.url));
  }, [files]);

  function selectFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    if (selected.length === 0) return;
    onFilesChange(multiple ? [...files, ...selected] : [selected[0]]);
    event.target.value = "";
  }

  function removeFile(index: number) {
    onFilesChange(files.filter((_, fileIndex) => fileIndex !== index));
  }

  return (
    <fieldset className="capture-field" disabled={disabled}>
      <legend>
        {label} {required && <span aria-label="required">*</span>}
      </legend>
      {helpText && <p className="field-help">{helpText}</p>}

      <div className="capture-field__actions">
        <label className="button button--secondary" htmlFor={`${inputId}-gallery`}>
          Choose {multiple ? "images" : "image"}
        </label>
        <input
          className="visually-hidden"
          id={`${inputId}-gallery`}
          type="file"
          accept={acceptedImages}
          multiple={multiple}
          onChange={selectFiles}
          aria-label={`${label} from files`}
        />

        <label className="button button--secondary" htmlFor={`${inputId}-camera`}>
          Use camera
        </label>
        <input
          className="visually-hidden"
          id={`${inputId}-camera`}
          type="file"
          accept={acceptedImages}
          capture="environment"
          onChange={selectFiles}
          aria-label={`${label} from camera`}
        />
      </div>

      {previews.length > 0 ? (
        <ul className="preview-grid" aria-label={`${label} previews`}>
          {previews.map((preview, index) => (
            <li key={`${preview.file.name}-${preview.file.lastModified}-${index}`}>
              <img src={preview.url} alt={`${label} preview ${index + 1}`} />
              <div className="preview-grid__details">
                <span>{preview.file.name}</span>
                <button type="button" className="text-button" onClick={() => removeFile(index)}>
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="capture-field__empty">No image selected.</p>
      )}
    </fieldset>
  );
}
