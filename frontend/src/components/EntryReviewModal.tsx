import { useState, useEffect } from 'react';
import {
  X,
  AlertTriangle,
  CheckCircle2,
  Check,
  Sparkles,
  Pencil,
  Tag,
} from 'lucide-react';
import type { ExtractedLedgerEntry } from '../types/extraction';
import './EntryReviewModal.css';

interface EntryReviewModalProps {
  entry: ExtractedLedgerEntry | null;
  groupTitle: string;
  isOpen: boolean;
  onClose: () => void;
  onSave: (correction: {
    corrected_marathi_text: string | null;
    corrected_amount: string | number | null;
    review_note?: string | null;
  }) => void;
  onConfirmAsIs: () => void;
}

export function EntryReviewModal({
  entry,
  groupTitle,
  isOpen,
  onClose,
  onSave,
  onConfirmAsIs,
}: EntryReviewModalProps) {
  if (!isOpen || !entry) return null;

  // Initialize editable state
  // Check if entry was previously reviewed or fallback to raw AI values
  const initialDesc =
    entry.corrected_marathi_text !== undefined
      ? entry.corrected_marathi_text || ''
      : entry.raw_marathi_text || '';

  const initialAmountVal =
    entry.corrected_amount !== undefined
      ? entry.corrected_amount
      : entry.amount;

  const initialIsNotRecorded =
    initialAmountVal === null ||
    initialAmountVal === undefined ||
    initialAmountVal === '' ||
    String(initialAmountVal).trim().toLowerCase() === 'not recorded';

  const [description, setDescription] = useState<string>(initialDesc);
  const [isNotRecorded, setIsNotRecorded] = useState<boolean>(initialIsNotRecorded);
  const [amount, setAmount] = useState<string>(
    initialIsNotRecorded ? '' : String(initialAmountVal ?? '')
  );
  const [reviewNote, setReviewNote] = useState<string>(entry.review_note || '');
  const [error, setError] = useState<string | null>(null);

  // Sync state if entry changes
  useEffect(() => {
    if (entry) {
      const d =
        entry.corrected_marathi_text !== undefined
          ? entry.corrected_marathi_text || ''
          : entry.raw_marathi_text || '';
      const a =
        entry.corrected_amount !== undefined
          ? entry.corrected_amount
          : entry.amount;
      const unrecorded =
        a === null ||
        a === undefined ||
        a === '' ||
        String(a).trim().toLowerCase() === 'not recorded';

      setDescription(d);
      setIsNotRecorded(unrecorded);
      setAmount(unrecorded ? '' : String(a ?? ''));
      setReviewNote(entry.review_note || '');
      setError(null);
    }
  }, [entry]);

  // Handle keyboard Escape to cancel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    let parsedAmount: number | null = null;
    if (isNotRecorded) {
      parsedAmount = null;
    } else {
      const trimmed = amount.trim();
      if (trimmed === '') {
        // If left empty and not explicitly marked unrecorded, keep as null (Not recorded)
        parsedAmount = null;
      } else {
        const num = Number(trimmed);
        if (isNaN(num) || num < 0) {
          setError('Please enter a valid positive numerical amount (e.g. 40, 150), or select "Not Recorded".');
          return;
        }
        parsedAmount = num;
      }
    }

    onSave({
      corrected_marathi_text: description.trim() || null,
      corrected_amount: parsedAmount,
      review_note: reviewNote.trim() || null,
    });
  };

  const isFlagged = entry.uncertain_fields.length > 0 || Boolean(entry.flag_reason);
  const isOriginalUnpriced =
    entry.amount === null ||
    entry.amount === undefined ||
    entry.amount === '' ||
    (typeof entry.amount === 'string' &&
      ['null', 'none', '-', '—', 'n/a', 'not recorded'].includes(
        entry.amount.trim().toLowerCase()
      ));

  return (
    <div className="review-modal__backdrop" onClick={onClose} role="presentation">
      <div
        className="review-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <header className="review-modal__header">
          <div className="review-modal__title-wrap">
            <div className="review-modal__icon-badge">
              <Pencil size={18} aria-hidden="true" />
            </div>
            <div>
              <h2 id="review-modal-title" className="review-modal__title">
                Review & Correct Entry #{entry.entry_index}
              </h2>
              <span className="review-modal__subtitle marathi-font">{groupTitle}</span>
            </div>
          </div>
          <button
            type="button"
            className="review-modal__close-btn"
            onClick={onClose}
            aria-label="Close dialog without saving"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        {/* Modal Body */}
        <div className="review-modal__body">
          {/* Flag Context Banner (if flagged by AI) */}
          {isFlagged && (
            <div className="review-modal__flag-banner" role="alert">
              <AlertTriangle size={18} className="review-modal__flag-icon" aria-hidden="true" />
              <div className="review-modal__flag-content">
                <strong>Needs Review: {entry.flag_reason || 'Uncertain reading'}</strong>
                {entry.uncertain_fields.length > 0 && (
                  <span>Uncertain fields: {entry.uncertain_fields.join(', ')}</span>
                )}
              </div>
            </div>
          )}

          {/* Original AI Extraction Reference Card */}
          <div className="review-modal__original-card">
            <div className="review-modal__original-header">
              <Sparkles size={14} aria-hidden="true" />
              <span>Original AI Extraction (Preserved Reference)</span>
            </div>
            <div className="review-modal__original-grid">
              <div className="review-modal__original-item">
                <span className="review-modal__original-label">Marathi Text:</span>
                <strong className="review-modal__original-val marathi-font">
                  {entry.raw_marathi_text || <em className="text-muted">[Illegible / None]</em>}
                </strong>
              </div>
              <div className="review-modal__original-item">
                <span className="review-modal__original-label">Original Amount:</span>
                <strong className="review-modal__original-val tabular-nums">
                  {!isOriginalUnpriced ? (
                    `₹${entry.amount}`
                  ) : (
                    <span className="review-modal__not-recorded-tag">Not recorded (dash)</span>
                  )}
                </strong>
              </div>
            </div>
          </div>

          {/* Correction Form */}
          <form id="entry-review-form" onSubmit={handleSave} className="review-modal__form">
            {error && (
              <div className="review-modal__error-msg" role="alert">
                <AlertTriangle size={15} aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            {/* Field 1: Service / Description */}
            <div className="review-modal__field">
              <label htmlFor="review-desc-input" className="review-modal__label">
                <span>Description (Marathi / English)</span>
                <span className="review-modal__label-hint">Correct handwriting typos or ditto marks</span>
              </label>
              <input
                id="review-desc-input"
                type="text"
                className="review-modal__input marathi-font"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. आयब्रो , यु कट , फेशियल"
                autoFocus
              />
            </div>

            {/* Field 2: Amount (₹) */}
            <div className="review-modal__field">
              <div className="review-modal__field-header">
                <label htmlFor="review-amount-input" className="review-modal__label">
                  <span>Transaction Amount (₹)</span>
                </label>
                <button
                  type="button"
                  className={`review-modal__toggle-unpriced-btn ${
                    isNotRecorded ? 'review-modal__toggle-unpriced-btn--active' : ''
                  }`}
                  onClick={() => {
                    const next = !isNotRecorded;
                    setIsNotRecorded(next);
                    if (next) {
                      setAmount('');
                    }
                  }}
                >
                  <Tag size={13} aria-hidden="true" />
                  <span>{isNotRecorded ? '✓ Marked as Not Recorded' : 'Mark as Not Recorded'}</span>
                </button>
              </div>

              {!isNotRecorded ? (
                <div className="review-modal__amount-input-wrap">
                  <span className="review-modal__currency-symbol" aria-hidden="true">
                    ₹
                  </span>
                  <input
                    id="review-amount-input"
                    type="text"
                    inputMode="decimal"
                    className="review-modal__input review-modal__input--amount tabular-nums"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="Enter amount (e.g. 40, 150)"
                  />
                </div>
              ) : (
                <div className="review-modal__unpriced-notice">
                  <span className="review-modal__unpriced-badge">Not recorded</span>
                  <p className="review-modal__unpriced-desc">
                    This entry has no written price on the physical page. It is excluded from calculations
                    and will remain Not Recorded unless an amount is entered above.
                  </p>
                </div>
              )}
            </div>

            {/* Field 3: Review Note (Optional) */}
            <div className="review-modal__field">
              <label htmlFor="review-note-input" className="review-modal__label">
                <span>Reviewer Note</span>
                <span className="review-modal__label-hint">Optional confirmation notes</span>
              </label>
              <input
                id="review-note-input"
                type="text"
                className="review-modal__input"
                value={reviewNote}
                onChange={(e) => setReviewNote(e.target.value)}
                placeholder="e.g. Verified with shopkeeper price list, or Dit marks confirmed"
              />
            </div>
          </form>
        </div>

        {/* Modal Footer Actions */}
        <footer className="review-modal__footer">
          <button
            type="button"
            className="review-modal__cancel-btn"
            onClick={onClose}
          >
            Cancel
          </button>

          <div className="review-modal__footer-right">
            {/* If user checks and confirms AI extracted correctly without needing changes */}
            <button
              type="button"
              className="review-modal__confirm-asis-btn"
              onClick={onConfirmAsIs}
              title="Confirm that the AI extraction is correct without modifying fields"
            >
              <Check size={16} aria-hidden="true" />
              <span>Confirm As-Is</span>
            </button>

            {/* Save any corrections made */}
            <button
              type="submit"
              form="entry-review-form"
              className="review-modal__save-btn"
            >
              <CheckCircle2 size={16} aria-hidden="true" />
              <span>Save & Confirm</span>
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
