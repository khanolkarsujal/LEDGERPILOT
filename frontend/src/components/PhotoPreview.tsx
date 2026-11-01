import { Trash2, RefreshCw, CheckCircle2, Image as ImageIcon } from 'lucide-react';
import { formatFileSize } from '../utils/format';
import './PhotoPreview.css';

interface PhotoPreviewProps {
  file: File;
  previewUrl: string;
  onRemove: () => void;
  onReplace: () => void;
}

export function PhotoPreview({
  file,
  previewUrl,
  onRemove,
  onReplace,
}: PhotoPreviewProps) {
  return (
    <div className="photo-preview" aria-label="Selected ledger photo preview">
      <div className="photo-preview__image-container">
        <img
          src={previewUrl}
          alt={`Handwritten ledger preview: ${file.name}`}
          className="photo-preview__image"
        />
      </div>

      <div className="photo-preview__details">
        <div className="photo-preview__file-info">
          <div className="photo-preview__badge" aria-label="Image status">
            <CheckCircle2 size={16} aria-hidden="true" />
            <span>Ready for processing</span>
          </div>

          <div className="photo-preview__meta">
            <div className="photo-preview__filename-row">
              <ImageIcon size={18} aria-hidden="true" className="photo-preview__meta-icon" />
              <span className="photo-preview__filename" title={file.name}>
                {file.name}
              </span>
            </div>
            <span className="photo-preview__filesize tabular-nums">
              {formatFileSize(file.size)}
            </span>
          </div>
        </div>

        <div className="photo-preview__actions">
          <button
            type="button"
            className="photo-preview__btn photo-preview__btn--replace"
            onClick={onReplace}
            aria-label="Replace selected photo"
          >
            <RefreshCw size={18} aria-hidden="true" />
            <span>Replace Photo</span>
          </button>

          <button
            type="button"
            className="photo-preview__btn photo-preview__btn--remove"
            onClick={onRemove}
            aria-label="Remove selected photo"
          >
            <Trash2 size={18} aria-hidden="true" />
            <span>Remove</span>
          </button>
        </div>
      </div>
    </div>
  );
}
