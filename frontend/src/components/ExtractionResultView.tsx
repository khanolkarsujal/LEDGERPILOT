import { useState, useEffect } from 'react';
import {
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  Calendar,
  FileText,
  Hash,
  Activity,
  Image as ImageIcon,
  Maximize2,
  Minimize2,
  Tag,
  Sparkles,
  Calculator,
  Info,
  Pencil,
  Download,
  Loader2,
} from 'lucide-react';
import type {
  LedgerPageExtraction,
  ExtractedTransactionGroup,
  ExtractedLedgerEntry,
  ReviewStatus,
  JobEvent,
} from '../types/extraction';
import { downloadPDFReport } from '../api';
import { EntryReviewModal } from './EntryReviewModal';
import './ExtractionResultView.css';

interface ExtractionResultViewProps {
  extraction: LedgerPageExtraction;
  selectedFile?: File | null;
  previewUrl?: string | null;
  events?: JobEvent[];
  onReset: () => void;
  onUpdateExtraction?: (updated: LedgerPageExtraction) => void;
}

/**
 * Returns the effective Marathi description:
 * Uses human-corrected value if available; otherwise falls back to raw AI extraction.
 */
export function getEffectiveDescription(entry: ExtractedLedgerEntry): string | null {
  if (entry.review_status === 'human_reviewed' && entry.corrected_marathi_text !== undefined) {
    return entry.corrected_marathi_text;
  }
  return entry.raw_marathi_text;
}

/**
 * Returns the effective numerical amount:
 * Uses human-corrected amount if available; otherwise falls back to raw AI extraction.
 */
export function getEffectiveAmount(entry: ExtractedLedgerEntry): string | number | null {
  if (entry.review_status === 'human_reviewed' && entry.corrected_amount !== undefined) {
    return entry.corrected_amount;
  }
  return entry.amount;
}

/**
 * Determines whether an entry is unpriced (amount was not recorded on the document).
 * Respects human correction if reviewed; otherwise analyzes AI extraction.
 * Guarantees that missing amounts remain null/unpriced and are never assigned
 * a default value or converted to 0.
 */
export function isEntryUnpriced(entry: ExtractedLedgerEntry): boolean {
  // If human reviewed, check the corrected amount
  if (entry.review_status === 'human_reviewed' && entry.corrected_amount !== undefined) {
    const ca = entry.corrected_amount;
    if (ca === null || ca === undefined) return true;
    if (typeof ca === 'string') {
      const s = ca.trim().toLowerCase();
      if (
        s === '' ||
        s === 'null' ||
        s === 'none' ||
        s === '-' ||
        s === '—' ||
        s === 'n/a' ||
        s === 'not recorded'
      ) {
        return true;
      }
    }
    return false;
  }

  // Original AI extraction checks
  if (entry.amount === null || entry.amount === undefined) {
    return true;
  }
  if (typeof entry.amount === 'string') {
    const s = entry.amount.trim().toLowerCase();
    if (
      s === '' ||
      s === 'null' ||
      s === 'none' ||
      s === '-' ||
      s === '—' ||
      s === 'n/a' ||
      s === 'not recorded'
    ) {
      return true;
    }
  }
  // If flagged specifically for missing/unpriced amount, ensure it stays unpriced
  if (entry.flag_reason) {
    const r = entry.flag_reason.toLowerCase();
    if (
      (r.includes('no amount') ||
        r.includes('unpriced') ||
        r.includes('not recorded') ||
        r.includes('dash recorded') ||
        r.includes('amount not explicitly written') ||
        r.includes('amount not specified')) &&
      entry.uncertain_fields?.includes('amount')
    ) {
      return true;
    }
  }
  return false;
}

/**
 * Checks if an entry was originally flagged for review by the AI.
 */
export function isEntryFlagged(entry: ExtractedLedgerEntry): boolean {
  return entry.uncertain_fields.length > 0 || Boolean(entry.flag_reason);
}

/**
 * Returns the effective review status of an entry:
 * - 'human_reviewed' if explicitly confirmed/corrected by user
 * - 'needs_review' if flagged by AI and not yet confirmed by user
 * - 'ai_extracted' if not flagged and not yet confirmed
 */
export function getEntryStatus(entry: ExtractedLedgerEntry): ReviewStatus {
  if (entry.review_status === 'human_reviewed') {
    return 'human_reviewed';
  }
  if (isEntryFlagged(entry)) {
    return 'needs_review';
  }
  return 'ai_extracted';
}

/**
 * Computes the arithmetic sum of valid numeric line-item amounts in a group.
 * Uses effective amounts and strictly excludes unpriced entries.
 */
export function calculateGroupSum(group: ExtractedTransactionGroup): number {
  return group.entries
    .filter((entry) => !isEntryUnpriced(entry) && !isNaN(Number(getEffectiveAmount(entry))))
    .reduce((sum, entry) => sum + Number(getEffectiveAmount(entry)), 0);
}

export function ExtractionResultView({
  extraction,
  selectedFile,
  previewUrl,
  events = [],
  onReset,
  onUpdateExtraction,
}: ExtractionResultViewProps) {
  // Local state holding the extraction data so human edits update instantly
  const [currentExtraction, setCurrentExtraction] = useState<LedgerPageExtraction>(extraction);
  const [activeTab, setActiveTab] = useState<'records' | 'events'>('records');
  const [isImageExpanded, setIsImageExpanded] = useState<boolean>(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState<boolean>(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // Active entry being reviewed in modal
  const [activeReviewCoords, setActiveReviewCoords] = useState<{
    groupIndex: number;
    entryIndex: number;
  } | null>(null);

  // Keep local extraction state in sync if prop changes
  useEffect(() => {
    setCurrentExtraction(extraction);
  }, [extraction]);

  // Overall counts across all groups
  const totalEntries = currentExtraction.groups.reduce((acc, g) => acc + g.entries.length, 0);
  const unpricedEntries = currentExtraction.groups.reduce(
    (acc, g) => acc + g.entries.filter(isEntryUnpriced).length,
    0
  );
  const needsReviewCount = currentExtraction.groups.reduce(
    (acc, g) => acc + g.entries.filter((e) => getEntryStatus(e) === 'needs_review').length,
    0
  );
  const humanReviewedCount = currentExtraction.groups.reduce(
    (acc, g) => acc + g.entries.filter((e) => getEntryStatus(e) === 'human_reviewed').length,
    0
  );

  // Page-level financial totals distinction
  // 1. Sum of all individual priced entries (using effective amounts)
  const pageCalculatedEntriesSum = currentExtraction.groups.reduce(
    (acc, g) => acc + calculateGroupSum(g),
    0
  );

  // 2. Sum of group subtotals explicitly written on document
  const groupsWithWrittenSubtotal = currentExtraction.groups.filter(
    (g) =>
      g.recorded_group_total !== null &&
      g.recorded_group_total !== undefined &&
      g.recorded_group_total !== '' &&
      !isNaN(Number(g.recorded_group_total))
  );
  const sumOfGroupSubtotals = groupsWithWrittenSubtotal.reduce(
    (acc, g) => acc + Number(g.recorded_group_total),
    0
  );

  // 3. Written page grand total (if recorded at page bottom)
  const writtenPageTotal =
    currentExtraction.recorded_page_total !== null &&
    currentExtraction.recorded_page_total !== undefined &&
    currentExtraction.recorded_page_total !== '' &&
    !isNaN(Number(currentExtraction.recorded_page_total))
      ? Number(currentExtraction.recorded_page_total)
      : null;

  // Active entry for modal
  const activeEntry: ExtractedLedgerEntry | null =
    activeReviewCoords !== null &&
    currentExtraction.groups[activeReviewCoords.groupIndex]?.entries[activeReviewCoords.entryIndex]
      ? currentExtraction.groups[activeReviewCoords.groupIndex].entries[activeReviewCoords.entryIndex]
      : null;

  const activeGroupTitle: string =
    activeReviewCoords !== null &&
    currentExtraction.groups[activeReviewCoords.groupIndex]
      ? currentExtraction.groups[activeReviewCoords.groupIndex].date_raw ||
        `Date Group ${activeReviewCoords.groupIndex + 1}`
      : '';

  // Handler: Save corrections made by human reviewer
  const handleSaveCorrection = (correction: {
    corrected_marathi_text: string | null;
    corrected_amount: string | number | null;
    review_note?: string | null;
  }) => {
    if (!activeReviewCoords) return;
    const { groupIndex, entryIndex } = activeReviewCoords;

    const updatedGroups = currentExtraction.groups.map((group, gIdx) => {
      if (gIdx !== groupIndex) return group;

      const updatedEntries = group.entries.map((entry, eIdx) => {
        if (eIdx !== entryIndex) return entry;

        // Preserve all original AI extraction fields intact!
        // Record human review fields alongside them:
        return {
          ...entry,
          review_status: 'human_reviewed' as ReviewStatus,
          corrected_marathi_text: correction.corrected_marathi_text,
          corrected_amount: correction.corrected_amount,
          reviewed_at: new Date().toISOString(),
          review_note: correction.review_note || null,
        };
      });

      return { ...group, entries: updatedEntries };
    });

    const updatedExtraction: LedgerPageExtraction = {
      ...currentExtraction,
      groups: updatedGroups,
    };

    setCurrentExtraction(updatedExtraction);
    onUpdateExtraction?.(updatedExtraction);
    setActiveReviewCoords(null);
  };

  // Handler: Confirm AI extraction is already correct without changing values
  const handleConfirmAsIs = () => {
    if (!activeReviewCoords) return;
    const { groupIndex, entryIndex } = activeReviewCoords;
    const targetEntry = currentExtraction.groups[groupIndex]?.entries[entryIndex];
    if (!targetEntry) return;

    const updatedGroups = currentExtraction.groups.map((group, gIdx) => {
      if (gIdx !== groupIndex) return group;

      const updatedEntries = group.entries.map((entry, eIdx) => {
        if (eIdx !== entryIndex) return entry;

        return {
          ...entry,
          review_status: 'human_reviewed' as ReviewStatus,
          corrected_marathi_text: entry.raw_marathi_text,
          corrected_amount: entry.amount,
          reviewed_at: new Date().toISOString(),
          review_note: 'Confirmed existing AI transcription as accurate',
        };
      });

      return { ...group, entries: updatedEntries };
    });

    const updatedExtraction: LedgerPageExtraction = {
      ...currentExtraction,
      groups: updatedGroups,
    };

    setCurrentExtraction(updatedExtraction);
    onUpdateExtraction?.(updatedExtraction);
    setActiveReviewCoords(null);
  };

  // Handler: Generate and download the Business Sales Statement PDF
  const handleDownloadPdf = async () => {
    try {
      setIsGeneratingPdf(true);
      setPdfError(null);
      const blob = await downloadPDFReport(currentExtraction);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const dateStr = new Date().toISOString().slice(0, 10);
      link.setAttribute('download', `Business_Sales_Statement_${dateStr}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate Business Sales Statement.';
      setPdfError(msg);
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  return (
    <div className="extraction-dashboard" aria-label="Extracted ledger records dashboard">
      {/* Top Action & Navigation Bar */}
      <header className="extraction-dashboard__topbar">
        <div className="extraction-dashboard__topbar-left">
          <button
            type="button"
            className="extraction-dashboard__back-btn"
            onClick={onReset}
            aria-label="Upload another ledger photograph"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            <span>Upload Another Page</span>
          </button>
          <div className="extraction-dashboard__divider" aria-hidden="true" />
          <span
            className="extraction-dashboard__filename"
            title={selectedFile?.name || 'Ledger photograph'}
          >
            {selectedFile?.name || 'Handwritten Ledger'}
          </span>
        </div>

        <div className="extraction-dashboard__topbar-right">
          <div className="extraction-dashboard__tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'records'}
              className={`extraction-dashboard__tab ${
                activeTab === 'records' ? 'extraction-dashboard__tab--active' : ''
              }`}
              onClick={() => setActiveTab('records')}
            >
              <FileText size={16} aria-hidden="true" />
              <span>Extracted Records</span>
              <span className="extraction-dashboard__tab-badge">{totalEntries}</span>
            </button>

            {events.length > 0 && (
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'events'}
                className={`extraction-dashboard__tab ${
                  activeTab === 'events' ? 'extraction-dashboard__tab--active' : ''
                }`}
                onClick={() => setActiveTab('events')}
              >
                <Activity size={16} aria-hidden="true" />
                <span>Backend Events</span>
                <span className="extraction-dashboard__tab-badge">{events.length}</span>
              </button>
            )}
          </div>

          {/* Transparent Trust Label: AI Extracted, never misleadingly called 'Verified' */}
          <div
            className="extraction-dashboard__status-pill"
            title="Transcriptions produced by AI vision model. Review flagged entries below."
          >
            {humanReviewedCount > 0 ? (
              <>
                <CheckCircle2 size={15} aria-hidden="true" />
                <span>
                  {humanReviewedCount} Human Reviewed • {needsReviewCount} Pending
                </span>
              </>
            ) : (
              <>
                <Sparkles size={15} aria-hidden="true" />
                <span>AI Extracted • Pending Review</span>
              </>
            )}
          </div>

          {/* Download Business Sales Statement Action */}
          <button
            type="button"
            className="extraction-dashboard__download-btn"
            onClick={handleDownloadPdf}
            disabled={isGeneratingPdf}
            title="Download accountant-prepared Business Sales Statement PDF for loan documentation"
            aria-label="Download Business Sales Statement PDF"
          >
            {isGeneratingPdf ? (
              <>
                <Loader2 size={15} className="extraction-dashboard__spin" aria-hidden="true" />
                <span>Generating...</span>
              </>
            ) : (
              <>
                <Download size={15} aria-hidden="true" />
                <span>Sales Statement (PDF)</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Split Layout: Original Photo on Left, Extracted Data on Right */}
      <div
        className={`extraction-dashboard__layout ${
          isImageExpanded ? 'extraction-dashboard__layout--expanded-img' : ''
        }`}
      >
        {/* Left Pane: Original Uploaded Ledger Photo */}
        {previewUrl && (
          <aside className="extraction-dashboard__image-pane">
            <div className="extraction-dashboard__image-card">
              <div className="extraction-dashboard__image-card-header">
                <div className="extraction-dashboard__image-title-wrap">
                  <ImageIcon size={16} aria-hidden="true" />
                  <h3>Original Document</h3>
                </div>
                <button
                  type="button"
                  className="extraction-dashboard__expand-btn"
                  onClick={() => setIsImageExpanded(!isImageExpanded)}
                  title={isImageExpanded ? 'Collapse preview' : 'Expand preview'}
                  aria-label={isImageExpanded ? 'Collapse image preview' : 'Expand image preview'}
                >
                  {isImageExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
              </div>

              <div className="extraction-dashboard__image-container">
                <img
                  src={previewUrl}
                  alt={`Original handwritten ledger: ${selectedFile?.name || ''}`}
                  className="extraction-dashboard__image"
                />
              </div>

              <div className="extraction-dashboard__image-footer">
                <span>Handwritten Bahi-Khata (Devanagari)</span>
                {selectedFile && (
                  <span className="tabular-nums">{(selectedFile.size / 1024).toFixed(1)} KB</span>
                )}
              </div>
            </div>
          </aside>
        )}

        {/* Right Pane: Content (Records Table or Backend Activity Log) */}
        <main className="extraction-dashboard__content-pane">
          {activeTab === 'records' ? (
            <div className="extraction-dashboard__records-tab">
              {/* Page Overview Card */}
              <div className="extraction-dashboard__overview-card">
                <div className="extraction-dashboard__overview-header">
                  <FileText
                    size={18}
                    className="extraction-dashboard__overview-icon"
                    aria-hidden="true"
                  />
                  <h2 className="extraction-dashboard__overview-title">Page Summary</h2>
                </div>
                <p className="extraction-dashboard__overview-summary">
                  {currentExtraction.page_summary}
                </p>

                {currentExtraction.unreadable_sections_found && (
                  <div className="extraction-dashboard__alert-unreadable" role="alert">
                    <AlertTriangle size={16} aria-hidden="true" />
                    <span>Visual notes: faint, smudged, or torn sections noted on this page.</span>
                  </div>
                )}

                {/* Metrics Badges */}
                <div className="extraction-dashboard__metrics-row">
                  <div className="extraction-dashboard__metric">
                    <Calendar
                      size={16}
                      aria-hidden="true"
                      className="extraction-dashboard__metric-icon"
                    />
                    <span className="extraction-dashboard__metric-label">Date Groups:</span>
                    <strong className="extraction-dashboard__metric-value tabular-nums">
                      {currentExtraction.groups.length}
                    </strong>
                  </div>

                  <div className="extraction-dashboard__metric">
                    <Hash
                      size={16}
                      aria-hidden="true"
                      className="extraction-dashboard__metric-icon"
                    />
                    <span className="extraction-dashboard__metric-label">Total Entries:</span>
                    <strong className="extraction-dashboard__metric-value tabular-nums">
                      {totalEntries}
                    </strong>
                  </div>

                  {unpricedEntries > 0 && (
                    <div className="extraction-dashboard__metric extraction-dashboard__metric--unpriced">
                      <Tag size={16} aria-hidden="true" />
                      <span className="extraction-dashboard__metric-label">Not Recorded:</span>
                      <strong className="extraction-dashboard__metric-value tabular-nums">
                        {unpricedEntries}
                      </strong>
                    </div>
                  )}

                  {needsReviewCount > 0 && (
                    <div className="extraction-dashboard__metric extraction-dashboard__metric--flagged">
                      <AlertTriangle size={16} aria-hidden="true" />
                      <span className="extraction-dashboard__metric-label">Needs Review:</span>
                      <strong className="extraction-dashboard__metric-value tabular-nums">
                        {needsReviewCount}
                      </strong>
                    </div>
                  )}

                  {humanReviewedCount > 0 && (
                    <div className="extraction-dashboard__metric extraction-dashboard__metric--reviewed">
                      <CheckCircle2 size={16} aria-hidden="true" />
                      <span className="extraction-dashboard__metric-label">Human Reviewed:</span>
                      <strong className="extraction-dashboard__metric-value tabular-nums">
                        {humanReviewedCount}
                      </strong>
                    </div>
                  )}
                </div>
              </div>

              {/* Transaction Groups */}
              <div className="extraction-dashboard__groups">
                {currentExtraction.groups.map(
                  (group: ExtractedTransactionGroup, gIdx: number) => {
                    const calculatedSum = calculateGroupSum(group);
                    const hasWrittenSubtotal =
                      group.recorded_group_total !== null &&
                      group.recorded_group_total !== undefined &&
                      group.recorded_group_total !== '' &&
                      !isNaN(Number(group.recorded_group_total));
                    const writtenSubtotal = hasWrittenSubtotal
                      ? Number(group.recorded_group_total)
                      : null;

                    const hasDiscrepancy =
                      writtenSubtotal !== null &&
                      Math.abs(calculatedSum - writtenSubtotal) > 0.001;

                    const unpricedInGroup = group.entries.filter(isEntryUnpriced);

                    return (
                      <section
                        key={group.group_id || `group-${gIdx}`}
                        className="extraction-group"
                        aria-labelledby={`group-title-${gIdx}`}
                      >
                        {/* Group Header: Date, Written Subtotal & Calculated Line-Items Sum */}
                        <div className="extraction-group__header">
                          <div className="extraction-group__date-block">
                            <h3
                              id={`group-title-${gIdx}`}
                              className="extraction-group__title marathi-font"
                            >
                              {group.date_raw || `Date Group ${gIdx + 1}`}
                            </h3>
                            {group.date_iso && (
                              <span className="extraction-group__iso-tag tabular-nums">
                                ISO: {group.date_iso}
                              </span>
                            )}
                          </div>

                          {/* Separate display of Written Subtotal and Calculated Line-Items Sum */}
                          <div className="extraction-group__totals-row">
                            <div className="extraction-group__total-chip extraction-group__total-chip--written">
                              <span className="extraction-group__total-chip-label">
                                Written Subtotal:
                              </span>
                              <strong className="extraction-group__total-chip-val tabular-nums">
                                {hasWrittenSubtotal ? `₹${writtenSubtotal}` : 'Not recorded'}
                              </strong>
                            </div>

                            <div className="extraction-group__total-chip extraction-group__total-chip--calculated">
                              <span className="extraction-group__total-chip-label">
                                Calculated Sum:
                              </span>
                              <strong className="extraction-group__total-chip-val tabular-nums">
                                ₹{calculatedSum}
                              </strong>
                            </div>
                          </div>
                        </div>

                        {/* Arithmetic Feedback Card: Non-judgmental comparison */}
                        {hasWrittenSubtotal ? (
                          hasDiscrepancy ? (
                            <div
                              className="extraction-group__feedback-card extraction-group__feedback-card--discrepancy"
                              role="status"
                            >
                              <AlertTriangle
                                size={18}
                                className="extraction-group__feedback-icon"
                                aria-hidden="true"
                              />
                              <div className="extraction-group__feedback-text">
                                <p className="extraction-group__feedback-title">
                                  Possible totaling mismatch
                                </p>
                                <p className="extraction-group__feedback-msg">
                                  Your written total is <strong>₹{writtenSubtotal}</strong>, but
                                  the listed entries add up to <strong>₹{calculatedSum}</strong>{' '}
                                  (difference of ₹{Math.abs(writtenSubtotal - calculatedSum)}).
                                  Please review.
                                </p>
                                {unpricedInGroup.length > 0 && (
                                  <p className="extraction-group__feedback-note">
                                    Note: {unpricedInGroup.length}{' '}
                                    {unpricedInGroup.length === 1 ? 'entry' : 'entries'} (
                                    {unpricedInGroup
                                      .map((e) => getEffectiveDescription(e) || 'Item')
                                      .join(', ')}
                                    ) has no recorded price and is excluded from the calculated
                                    sum.
                                  </p>
                                )}
                              </div>
                            </div>
                          ) : (
                            <div
                              className="extraction-group__feedback-card extraction-group__feedback-card--match"
                              role="status"
                            >
                              <CheckCircle2
                                size={18}
                                className="extraction-group__feedback-icon"
                                aria-hidden="true"
                              />
                              <div className="extraction-group__feedback-text">
                                <p className="extraction-group__feedback-title">Totals match</p>
                                <p className="extraction-group__feedback-msg">
                                  Written subtotal (₹{writtenSubtotal}) equals calculated entry sum
                                  (₹{calculatedSum}).
                                </p>
                                {unpricedInGroup.length > 0 && (
                                  <p className="extraction-group__feedback-note">
                                    ({unpricedInGroup.length}{' '}
                                    {unpricedInGroup.length === 1
                                      ? 'unpriced entry is'
                                      : 'unpriced entries are'}{' '}
                                    excluded from the sum.)
                                  </p>
                                )}
                              </div>
                            </div>
                          )
                        ) : (
                          <div
                            className="extraction-group__feedback-card extraction-group__feedback-card--info"
                            role="status"
                          >
                            <Info
                              size={18}
                              className="extraction-group__feedback-icon"
                              aria-hidden="true"
                            />
                            <div className="extraction-group__feedback-text">
                              <p className="extraction-group__feedback-msg">
                                No subtotal was written on this section. Calculated entry sum is{' '}
                                <strong>₹{calculatedSum}</strong>.
                              </p>
                            </div>
                          </div>
                        )}

                        {group.notes && (
                          <p className="extraction-group__notes">
                            <em>Note: {group.notes}</em>
                          </p>
                        )}

                        {/* Entries Table */}
                        <div className="extraction-group__table-container">
                          <table className="extraction-table">
                            <thead>
                              <tr>
                                <th scope="col" className="extraction-table__th-idx">
                                  #
                                </th>
                                <th scope="col">Description (Marathi)</th>
                                <th scope="col" className="extraction-table__th-amt">
                                  Amount (₹)
                                </th>
                                <th scope="col" className="extraction-table__th-type">
                                  Type
                                </th>
                                <th scope="col" className="extraction-table__th-status">
                                  Status
                                </th>
                                <th scope="col" className="extraction-table__th-action">
                                  Action
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.entries.map((entry, eIdx) => {
                                const status = getEntryStatus(entry);
                                const isFlagged = status === 'needs_review';
                                const isReviewed = status === 'human_reviewed';
                                const unpriced = isEntryUnpriced(entry);

                                const effectiveDesc = getEffectiveDescription(entry);
                                const effectiveAmt = getEffectiveAmount(entry);

                                // Check if user corrected the text or amount
                                const isTextModified =
                                  isReviewed &&
                                  entry.corrected_marathi_text !== undefined &&
                                  entry.corrected_marathi_text !== entry.raw_marathi_text;

                                const isAmtModified =
                                  isReviewed &&
                                  entry.corrected_amount !== undefined &&
                                  entry.corrected_amount !== entry.amount;

                                return (
                                  <tr
                                    key={`entry-${gIdx}-${entry.entry_index || eIdx}`}
                                    className={`extraction-table__row ${
                                      isFlagged ? 'extraction-table__row--flagged' : ''
                                    } ${isReviewed ? 'extraction-table__row--reviewed' : ''} ${
                                      unpriced ? 'extraction-table__row--unpriced' : ''
                                    }`}
                                  >
                                    <td className="extraction-table__td-idx tabular-nums">
                                      {entry.entry_index || eIdx + 1}
                                    </td>
                                    <td className="extraction-table__td-desc">
                                      <div className="extraction-table__desc-wrap">
                                        <span className="extraction-table__marathi-text marathi-font">
                                          {effectiveDesc || (
                                            <span className="extraction-table__null">
                                              [Unreadable Text]
                                            </span>
                                          )}
                                        </span>
                                        {isTextModified && entry.raw_marathi_text && (
                                          <span
                                            className="extraction-table__orig-tag marathi-font"
                                            title={`AI raw extraction: ${entry.raw_marathi_text}`}
                                          >
                                            Orig: {entry.raw_marathi_text}
                                          </span>
                                        )}
                                      </div>
                                    </td>
                                    <td className="extraction-table__td-amt tabular-nums">
                                      <div className="extraction-table__amt-wrap">
                                        {!unpriced ? (
                                          `₹${effectiveAmt}`
                                        ) : (
                                          <span
                                            className="extraction-table__unpriced-badge"
                                            title="No numerical amount was written on the physical document"
                                          >
                                            Not recorded
                                          </span>
                                        )}
                                        {isAmtModified && (
                                          <span
                                            className="extraction-table__orig-tag"
                                            title={`AI raw extraction: ${
                                              entry.amount !== null ? `₹${entry.amount}` : 'Not recorded'
                                            }`}
                                          >
                                            Orig:{' '}
                                            {entry.amount !== null ? `₹${entry.amount}` : 'Not recorded'}
                                          </span>
                                        )}
                                      </div>
                                    </td>
                                    <td className="extraction-table__td-type">
                                      <span className="extraction-table__type-badge">
                                        {entry.entry_type}
                                      </span>
                                    </td>
                                    <td className="extraction-table__td-status">
                                      {isReviewed ? (
                                        <div className="extraction-table__reviewed-pill">
                                          <CheckCircle2 size={13} aria-hidden="true" />
                                          <span>Human reviewed</span>
                                        </div>
                                      ) : isFlagged ? (
                                        <div
                                          className="extraction-table__flag-pill"
                                          title={entry.flag_reason || 'Needs review'}
                                        >
                                          <AlertTriangle size={13} aria-hidden="true" />
                                          <span>Needs review</span>
                                        </div>
                                      ) : (
                                        <span
                                          className="extraction-table__ai-pill"
                                          title="Directly transcribed from document by AI vision model"
                                        >
                                          <Sparkles size={13} aria-hidden="true" />
                                          <span>AI extracted</span>
                                        </span>
                                      )}
                                      {!isReviewed && isFlagged && entry.flag_reason && (
                                        <span className="extraction-table__flag-reason">
                                          {entry.flag_reason}
                                        </span>
                                      )}
                                      {isReviewed && entry.review_note && (
                                        <span
                                          className="extraction-table__review-note"
                                          title={entry.review_note}
                                        >
                                          Note: {entry.review_note}
                                        </span>
                                      )}
                                    </td>
                                    <td className="extraction-table__td-action">
                                      <button
                                        type="button"
                                        className={`extraction-table__action-btn ${
                                          isFlagged
                                            ? 'extraction-table__action-btn--review'
                                            : isReviewed
                                            ? 'extraction-table__action-btn--reviewed'
                                            : 'extraction-table__action-btn--edit'
                                        }`}
                                        onClick={() =>
                                          setActiveReviewCoords({
                                            groupIndex: gIdx,
                                            entryIndex: eIdx,
                                          })
                                        }
                                        aria-label={`Review or edit entry #${
                                          entry.entry_index || eIdx + 1
                                        }`}
                                      >
                                        <Pencil size={13} aria-hidden="true" />
                                        <span>
                                          {isReviewed
                                            ? 'Edit'
                                            : isFlagged
                                            ? 'Review & Edit'
                                            : 'Edit'}
                                        </span>
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    );
                  }
                )}
              </div>

              {/* Page Financial Reconciliation & Grand Totals Distinction */}
              <section
                className="extraction-dashboard__reconciliation-card"
                aria-label="Page financial totals reconciliation"
              >
                <div className="extraction-dashboard__reconciliation-header">
                  <Calculator
                    size={20}
                    className="extraction-dashboard__reconciliation-icon"
                    aria-hidden="true"
                  />
                  <div>
                    <h3 className="extraction-dashboard__reconciliation-title">
                      Page Financial Reconciliation
                    </h3>
                    <p className="extraction-dashboard__reconciliation-subtitle">
                      Clear comparison of individual entries, written section subtotals, and
                      page grand total.
                    </p>
                  </div>
                </div>

                <div className="extraction-dashboard__reconciliation-grid">
                  {/* Total 1: Sum of Individual Line Items (Calculated from effective amounts) */}
                  <div className="extraction-dashboard__reconciliation-item">
                    <span className="extraction-dashboard__reconciliation-item-label">
                      Sum of Entries (Calculated)
                    </span>
                    <strong className="extraction-dashboard__reconciliation-item-val tabular-nums">
                      ₹{pageCalculatedEntriesSum}
                    </strong>
                    <span className="extraction-dashboard__reconciliation-item-desc">
                      Sum of {totalEntries - unpricedEntries} priced line items across all groups
                    </span>
                  </div>

                  {/* Total 2: Sum of Written Group Subtotals */}
                  <div className="extraction-dashboard__reconciliation-item">
                    <span className="extraction-dashboard__reconciliation-item-label">
                      Sum of Group Subtotals
                    </span>
                    <strong className="extraction-dashboard__reconciliation-item-val tabular-nums">
                      {groupsWithWrittenSubtotal.length > 0
                        ? `₹${sumOfGroupSubtotals}`
                        : 'None written'}
                    </strong>
                    <span className="extraction-dashboard__reconciliation-item-desc">
                      {groupsWithWrittenSubtotal.length} of {currentExtraction.groups.length}{' '}
                      groups have written subtotals
                    </span>
                  </div>

                  {/* Total 3: Written Page Grand Total */}
                  <div className="extraction-dashboard__reconciliation-item">
                    <span className="extraction-dashboard__reconciliation-item-label">
                      Written Page Grand Total
                    </span>
                    <strong className="extraction-dashboard__reconciliation-item-val tabular-nums">
                      {writtenPageTotal !== null ? `₹${writtenPageTotal}` : 'Not recorded'}
                    </strong>
                    <span className="extraction-dashboard__reconciliation-item-desc">
                      Explicit total written at bottom of physical page
                    </span>
                  </div>
                </div>

                {/* Final Reconciliation Status Note */}
                <div className="extraction-dashboard__reconciliation-footer">
                  {writtenPageTotal !== null ? (
                    Math.abs(writtenPageTotal - pageCalculatedEntriesSum) < 0.001 ? (
                      <span className="extraction-dashboard__reconciliation-status extraction-dashboard__reconciliation-status--match">
                        <CheckCircle2 size={16} aria-hidden="true" />
                        Page Reconciled: Written page grand total (₹{writtenPageTotal}) exactly
                        matches calculated entry sum.
                      </span>
                    ) : (
                      <span className="extraction-dashboard__reconciliation-status extraction-dashboard__reconciliation-status--discrepancy">
                        <AlertTriangle size={16} aria-hidden="true" />
                        Reconciliation Notice: Written page total is ₹{writtenPageTotal},
                        while calculated entries sum to ₹{pageCalculatedEntriesSum} (difference of
                        ₹{Math.abs(writtenPageTotal - pageCalculatedEntriesSum)}).
                      </span>
                    )
                  ) : (
                    <span className="extraction-dashboard__reconciliation-status extraction-dashboard__reconciliation-status--info">
                      <Info size={16} aria-hidden="true" />
                      No grand page total was written at the bottom of the page. Total
                      calculated across all groups is ₹{pageCalculatedEntriesSum}.
                    </span>
                  )}
                </div>
              </section>

              {/* Professional Business Sales Statement Export Card */}
              <section
                className="extraction-dashboard__export-card"
                aria-label="Export Business Sales Statement"
              >
                <div className="extraction-dashboard__export-info">
                  <div className="extraction-dashboard__export-title-wrap">
                    <FileText
                      size={20}
                      className="extraction-dashboard__export-icon"
                      aria-hidden="true"
                    />
                    <div>
                      <h3 className="extraction-dashboard__export-title">
                        Business Sales Statement (Loan Documentation)
                      </h3>
                      <p className="extraction-dashboard__export-desc">
                        Download a conventional, accountant-style Business Sales Statement and Daily Sales Register
                        suitable as supporting financial documentation for loan applications.
                      </p>
                    </div>
                  </div>
                  {pdfError && (
                    <div className="extraction-dashboard__export-error" role="alert">
                      <AlertTriangle size={15} aria-hidden="true" />
                      <span>{pdfError}</span>
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="extraction-dashboard__export-btn"
                  onClick={handleDownloadPdf}
                  disabled={isGeneratingPdf}
                  aria-label="Generate and download Business Sales Statement PDF"
                >
                  {isGeneratingPdf ? (
                    <>
                      <Loader2 size={16} className="extraction-dashboard__spin" aria-hidden="true" />
                      <span>Generating Statement...</span>
                    </>
                  ) : (
                    <>
                      <Download size={16} aria-hidden="true" />
                      <span>Download Sales Statement (PDF)</span>
                    </>
                  )}
                </button>
              </section>
            </div>
          ) : (
            /* Tab 2: Backend Activity Log */
            <div className="extraction-dashboard__events-tab">
              <div className="extraction-dashboard__events-card">
                <div className="extraction-dashboard__events-card-header">
                  <div className="extraction-dashboard__events-title-wrap">
                    <Activity size={18} aria-hidden="true" />
                    <h3>Backend Lifecycle Activity Log</h3>
                  </div>
                  <span className="extraction-dashboard__events-count">
                    {events.length} confirmed events
                  </span>
                </div>
                <p className="extraction-dashboard__events-desc">
                  Real-time events recorded by the FastAPI backend during image ingestion,
                  preprocessing, Gemini API interaction, and schema validation.
                </p>

                <div className="extraction-dashboard__events-timeline">
                  {events.map((ev: JobEvent, idx: number) => {
                    const evDate = new Date(ev.timestamp * 1000);
                    const timeFormatted = evDate.toLocaleTimeString(undefined, {
                      hour12: false,
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    });
                    const ms = String(evDate.getMilliseconds()).padStart(3, '0');

                    return (
                      <div key={idx} className="extraction-dashboard__event-item">
                        <div className="extraction-dashboard__event-marker">
                          <div className="extraction-dashboard__event-dot" />
                        </div>
                        <div className="extraction-dashboard__event-content">
                          <div className="extraction-dashboard__event-meta">
                            <span className="extraction-dashboard__event-time tabular-nums">
                              {timeFormatted}.{ms}
                            </span>
                            <span className="extraction-dashboard__event-stage">
                              {ev.stage}
                            </span>
                          </div>
                          <p className="extraction-dashboard__event-message">{ev.message}</p>
                          {ev.details && (
                            <span className="extraction-dashboard__event-details">
                              {ev.details}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Review & Edit Modal */}
      {activeReviewCoords && activeEntry && (
        <EntryReviewModal
          entry={activeEntry}
          groupTitle={activeGroupTitle}
          isOpen={Boolean(activeReviewCoords)}
          onClose={() => setActiveReviewCoords(null)}
          onSave={handleSaveCorrection}
          onConfirmAsIs={handleConfirmAsIs}
        />
      )}
    </div>
  );
}
