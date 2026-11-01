import { useState, useRef, useEffect, type ChangeEvent, type DragEvent } from 'react';
import { Upload, Camera, AlertTriangle, Loader2 } from 'lucide-react';
import { PhotoPreview } from './PhotoPreview';
import { formatFileSize } from '../utils/format';
import './UploadView.css';

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB limit
const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png'];
const ALLOWED_EXTENSIONS_REGEX = /\.(jpe?g|png)$/i;

export function UploadView() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Clean up object URLs to prevent browser memory leaks
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const validateAndProcessFile = (file: File) => {
    setErrorMessage(null);

    // 1. Validate file format (JPEG, JPG, PNG)
    const isAllowedType =
      ALLOWED_MIME_TYPES.includes(file.type) ||
      ALLOWED_EXTENSIONS_REGEX.test(file.name);

    if (!isAllowedType) {
      setErrorMessage(
        'Unsupported file format. Please select a JPEG or PNG image (.jpg, .jpeg, or .png).'
      );
      return;
    }

    // 2. Validate maximum file size (10 MB)
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setErrorMessage(
        `File size exceeds the 10 MB limit (selected file is ${formatFileSize(
          file.size
        )}). Please select a smaller photo.`
      );
      return;
    }

    // 3. Process and create preview
    setIsLoading(true);

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    try {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      setSelectedFile(file);
    } catch {
      setErrorMessage('Could not generate a preview for this image. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      validateAndProcessFile(files[0]);
    }
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);

    const files = event.dataTransfer.files;
    if (files && files.length > 0) {
      validateAndProcessFile(files[0]);
    }
  };

  const handleRemove = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleReplace = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  };

  const handleTriggerUpload = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  return (
    <section className="upload-view" aria-labelledby="upload-heading">
      <header className="upload-view__header">
        <h2 id="upload-heading" className="upload-view__title">
          Upload Ledger Page
        </h2>
        <p className="upload-view__subtitle">
          Take a photo of a handwritten ledger page or upload an image to convert
          it into digital records.
        </p>
      </header>

      {/* Hidden native file input supporting both mobile camera & gallery */}
      <input
        ref={fileInputRef}
        type="file"
        id="ledger-file-input"
        accept="image/jpeg,image/png,.jpg,.jpeg,.png"
        className="upload-view__file-input"
        onChange={handleFileInputChange}
        aria-label="Upload handwritten ledger photo"
      />

      {/* Validation / Error Message */}
      {errorMessage && (
        <div className="upload-view__alert upload-view__alert--error" role="alert">
          <AlertTriangle size={20} className="upload-view__alert-icon" aria-hidden="true" />
          <div className="upload-view__alert-content">
            <span className="upload-view__alert-title">Cannot use this file</span>
            <p className="upload-view__alert-text">{errorMessage}</p>
          </div>
          <button
            type="button"
            className="upload-view__alert-close"
            onClick={() => setErrorMessage(null)}
            aria-label="Dismiss error message"
          >
            &times;
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="upload-view__loading" role="status" aria-live="polite">
          <Loader2 size={32} className="upload-view__spinner" aria-hidden="true" />
          <p>Loading photo preview...</p>
        </div>
      )}

      {/* Preview State */}
      {!isLoading && selectedFile && previewUrl && (
        <PhotoPreview
          file={selectedFile}
          previewUrl={previewUrl}
          onRemove={handleRemove}
          onReplace={handleReplace}
        />
      )}

      {/* Empty / Initial Upload State */}
      {!isLoading && !selectedFile && (
        <div
          className={`upload-view__dropzone ${
            isDragging ? 'upload-view__dropzone--active' : ''
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={handleTriggerUpload}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleTriggerUpload();
            }
          }}
          aria-label="Select a handwritten ledger photo or drop file here"
        >
          <div className="upload-view__icon-group">
            <div className="upload-view__icon-circle upload-view__icon-circle--primary">
              <Camera size={28} aria-hidden="true" />
            </div>
            <div className="upload-view__icon-circle upload-view__icon-circle--secondary">
              <Upload size={24} aria-hidden="true" />
            </div>
          </div>

          <div className="upload-view__dropzone-text">
            <span className="upload-view__dropzone-prompt">
              Take a photo or choose an image
            </span>
            <span className="upload-view__dropzone-sub">
              Tap here to open camera or browse files
            </span>
          </div>

          <div className="upload-view__btn upload-view__btn--select">
            <Upload size={20} aria-hidden="true" />
            <span>Select Ledger Photo</span>
          </div>

          <div className="upload-view__specs">
            <span>Supports JPEG and PNG</span>
            <span className="upload-view__specs-dot" aria-hidden="true">
              •
            </span>
            <span>Maximum file size: 10 MB</span>
          </div>
        </div>
      )}
    </section>
  );
}
