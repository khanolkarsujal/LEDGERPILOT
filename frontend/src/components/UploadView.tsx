import { useState, useRef, useEffect, type ChangeEvent, type DragEvent } from 'react';
import { Upload, Camera, AlertTriangle, Loader2 } from 'lucide-react';
import { PhotoPreview } from './PhotoPreview';
import { LiveProcessingView } from './LiveProcessingView';
import { formatFileSize } from '../utils/format';
import { createExtractionJob, pollExtractionJob, ExtractionApiError } from '../api';
import type { LedgerPageExtraction, JobStatusResponse, JobEvent } from '../types/extraction';
import './UploadView.css';

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB limit
const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png'];
const ALLOWED_EXTENSIONS_REGEX = /\.(jpe?g|png)$/i;

interface UploadViewProps {
  onExtractionSuccess?: (
    result: LedgerPageExtraction,
    file: File,
    previewUrl: string,
    events: JobEvent[]
  ) => void;
}

export function UploadView({ onExtractionSuccess }: UploadViewProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [currentJob, setCurrentJob] = useState<JobStatusResponse | null>(null);
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
    setCurrentJob(null);
    setIsExtracting(false);
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

  const handleExtract = async () => {
    if (!selectedFile) return;
    setErrorMessage(null);
    setIsExtracting(true);

    try {
      // 1. Create job on backend
      const initialJob = await createExtractionJob(selectedFile);
      setCurrentJob(initialJob);

      // 2. Poll job status until completed, updating UI with real events
      const completedJob = await pollExtractionJob(
        initialJob.job_id,
        (updatedJob) => {
          setCurrentJob(updatedJob);
        }
      );

      if (completedJob.result) {
        setIsExtracting(false);
        if (onExtractionSuccess) {
          onExtractionSuccess(
            completedJob.result,
            selectedFile,
            previewUrl!,
            completedJob.events
          );
        }
      } else {
        throw new Error('Backend completed processing but returned an empty extraction result.');
      }
    } catch (err: unknown) {
      if (err instanceof ExtractionApiError) {
        setErrorMessage(err.message);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('An unexpected error occurred during extraction. Please try again.');
      }
    }
  };

  // If extraction is actively running or has failed in the live view, render LiveProcessingView
  if (isExtracting && selectedFile && previewUrl) {
    return (
      <LiveProcessingView
        job={currentJob}
        selectedFile={selectedFile}
        previewUrl={previewUrl}
        errorMessage={errorMessage}
        onRetry={handleExtract}
        onCancel={() => {
          setIsExtracting(false);
          setCurrentJob(null);
          setErrorMessage(null);
        }}
      />
    );
  }

  return (
    <section className="upload-view" aria-labelledby="upload-heading">
      <header className="upload-view__header">
        <h2 id="upload-heading" className="upload-view__title">
          Upload Ledger Page
        </h2>
        <p className="upload-view__subtitle">
          Take a photo of a handwritten Marathi ledger page or upload an image to convert
          it into structured digital financial records.
        </p>
      </header>

      {/* Hidden native file input */}
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
          onExtract={handleExtract}
          isExtracting={isExtracting}
        />
      )}

      {/* Empty / Initial Upload Dropzone */}
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
