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
  Calculator,
  Info,
  Pencil,
  Download,
  Loader2,
  Trash2,
  X,
  AlertCircle,
  Check,
  Building2,
  ShieldCheck,
} from 'lucide-react';
import type {
  LedgerPageExtraction,
  ExtractedTransactionGroup,
  ExtractedLedgerEntry,
  ReviewStatus,
  JobEvent,
} from '../types/extraction';
import { downloadPDFReport, ReportApiError } from '../api';
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

const LOCAL_STORAGE_BIZ_KEY = 'ledgerpilot_business_details';

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
  return (entry.uncertain_fields && entry.uncertain_fields.length > 0) || Boolean(entry.flag_reason);
}

/**
 * Checks if an extracted entry has high confidence:
 * - Has non-empty description.
 * - Has valid numeric amount > 0.
 * - Has zero uncertainty flags and zero flag reasons.
 */
export function isEntryHighConfidence(entry: ExtractedLedgerEntry): boolean {
  const desc = getEffectiveDescription(entry);
  const amt = getEffectiveAmount(entry);
  const unpriced = isEntryUnpriced(entry);

  const hasDesc = Boolean(desc && desc.trim());
  const hasAmt = !unpriced && amt !== null && amt !== undefined && !isNaN(Number(amt)) && Number(amt) > 0;
  const hasNoFlags = !isEntryFlagged(entry);

  return hasDesc && hasAmt && hasNoFlags;
}

/**
 * Returns the effective review status of an entry:
 * - 'human_reviewed' if explicitly confirmed/corrected by user
 * - 'needs_review' if flagged by AI or unpriced without human confirmation
 * - 'auto_accepted' if high confidence (clean description, clean amount, zero flags)
 */
export function getEntryStatus(entry: ExtractedLedgerEntry): ReviewStatus {
  if (entry.review_status === 'human_reviewed') {
    return 'human_reviewed';
  }
  if (entry.review_status === 'auto_accepted') {
    return 'auto_accepted';
  }
  if (isEntryFlagged(entry) || isEntryUnpriced(entry)) {
    return 'needs_review';
  }
  if (isEntryHighConfidence(entry)) {
    return 'auto_accepted';
  }
  return 'needs_review';
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
  // Local state holding the extraction data so human edits and deletions update instantly
  const [currentExtraction, setCurrentExtraction] = useState<LedgerPageExtraction>(extraction);
  const [activeTab, setActiveTab] = useState<'records' | 'events'>('records');
  const [isImageExpanded, setIsImageExpanded] = useState<boolean>(false);
  const [isGeneratingPdf, setIsGeneratingPdf] = useState<boolean>(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  // Active entry being reviewed/edited in modal
  const [activeReviewCoords, setActiveReviewCoords] = useState<{
    groupIndex: number;
    entryIndex: number;
  } | null>(null);

  // Entry pending deletion confirmation
  const [entryToDelete, setEntryToDelete] = useState<{
    groupIndex: number;
    entryIndex: number;
  } | null>(null);

  // Business Information Collection & Persistence
  const [businessName, setBusinessName] = useState<string>(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_BIZ_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.businessName || '';
      }
    } catch {
      // ignore
    }
    return '';
  });

  const [businessAddress, setBusinessAddress] = useState<string>(() => {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_BIZ_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.businessAddress || '';
      }
    } catch {
      // ignore
    }
    return '';
  });

  const [rememberBusinessDetails, setRememberBusinessDetails] = useState<boolean>(true);
  const [showBusinessInfoModal, setShowBusinessInfoModal] = useState<boolean>(false);

  // Temp form state for business info modal
  const [tempBizName, setTempBizName] = useState<string>(businessName);
  const [tempBizAddress, setTempBizAddress] = useState<string>(businessAddress);

  // Discrepancy Acknowledgment Modal state
  const [showDiscrepancyModal, setShowDiscrepancyModal] = useState<boolean>(false);
  const [discrepancyAcknowledged, setDiscrepancyAcknowledged] = useState<boolean>(false);
  const [hasAcknowledgedDiscrepancies, setHasAcknowledgedDiscrepancies] = useState<boolean>(false);

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

  // High-confidence entries are automatically accepted; only genuinely uncertain entries require review!
  const needsReviewCount = currentExtraction.groups.reduce(
    (acc, g) => acc + g.entries.filter((e) => getEntryStatus(e) === 'needs_review').length,
    0
  );
  const autoAcceptedCount = currentExtraction.groups.reduce(
    (acc, g) => acc + g.entries.filter((e) => getEntryStatus(e) === 'auto_accepted').length,
    0
  );
  const humanReviewedCount = currentExtraction.groups.reduce(
    (acc, g) => acc + g.entries.filter((e) => getEntryStatus(e) === 'human_reviewed').length,
    0
  );

  // Review Gate: PDF is blocked ONLY if there are unresolved flagged entries
  const isExportBlocked = needsReviewCount > 0 || totalEntries === 0;

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

  // Check for arithmetic discrepancies across all sections
  const groupDiscrepancies = currentExtraction.groups
    .map((g, idx) => {
      const calcSum = calculateGroupSum(g);
      const hasRec =
        g.recorded_group_total !== null &&
        g.recorded_group_total !== undefined &&
        g.recorded_group_total !== '' &&
        !isNaN(Number(g.recorded_group_total));
      if (!hasRec) return null;
      const recVal = Number(g.recorded_group_total);
      if (Math.abs(calcSum - recVal) > 0.001) {
        return {
          sectionIndex: idx + 1,
          sectionLabel: g.date_raw || `Section ${idx + 1}`,
          writtenSubtotal: recVal,
          calculatedTotal: calcSum,
          difference: recVal - calcSum,
        };
      }
      return null;
    })
    .filter((d): d is NonNullable<typeof d> => d !== null);

  const hasAnyDiscrepancies = groupDiscrepancies.length > 0;

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

  // Entry details for delete confirmation modal
  const targetDeleteEntry: ExtractedLedgerEntry | null =
    entryToDelete !== null &&
    currentExtraction.groups[entryToDelete.groupIndex]?.entries[entryToDelete.entryIndex]
      ? currentExtraction.groups[entryToDelete.groupIndex].entries[entryToDelete.entryIndex]
      : null;

  const targetDeleteGroupTitle: string =
    entryToDelete !== null &&
    currentExtraction.groups[entryToDelete.groupIndex]
      ? currentExtraction.groups[entryToDelete.groupIndex].date_raw ||
        `Section ${entryToDelete.groupIndex + 1}`
      : '';

  // Handler: Save corrections made by user
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
    setPdfError(null);
  };

  // Handler: Confirm an entry as accurate as-is
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
          review_note: 'Confirmed transcription as accurate',
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
    setPdfError(null);
  };

  // Handler: Find and review next unresolved flagged entry
  const handleReviewNextFlagged = () => {
    for (let gIdx = 0; gIdx < currentExtraction.groups.length; gIdx++) {
      const group = currentExtraction.groups[gIdx];
      for (let eIdx = 0; eIdx < group.entries.length; eIdx++) {
        const entry = group.entries[eIdx];
        if (getEntryStatus(entry) === 'needs_review') {
          setActiveReviewCoords({ groupIndex: gIdx, entryIndex: eIdx });
          return;
        }
      }
    }
  };

  // Handler: Confirm deletion of an unwanted/incorrect transaction
  const handleExecuteDelete = () => {
    if (!entryToDelete) return;
    const { groupIndex, entryIndex } = entryToDelete;

    const updatedGroups = currentExtraction.groups.map((group, gIdx) => {
      if (gIdx !== groupIndex) return group;

      // Filter out deleted entry
      const remainingEntries = group.entries.filter((_, eIdx) => eIdx !== entryIndex);
      // Re-index remaining entries sequentially
      const reindexedEntries = remainingEntries.map((e, idx) => ({
        ...e,
        entry_index: idx + 1,
      }));

      return {
        ...group,
        entries: reindexedEntries,
      };
    });

    const updatedExtraction: LedgerPageExtraction = {
      ...currentExtraction,
      groups: updatedGroups,
    };

    setCurrentExtraction(updatedExtraction);
    onUpdateExtraction?.(updatedExtraction);
    setEntryToDelete(null);
    setPdfError(null);
  };

  // Handler: Initiate download of PDF statement
  const executeDownload = async (bizName: string, bizAddr: string, acknowledged: boolean) => {
    try {
      setIsGeneratingPdf(true);
      setPdfError(null);
      const blob = await downloadPDFReport(
        currentExtraction,
        bizName.trim() || undefined,
        bizAddr.trim() || undefined,
        undefined,
        undefined,
        acknowledged
      );
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const dateStr = new Date().toISOString().slice(0, 10);
      link.setAttribute('download', `Business_Sales_Statement_${dateStr}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setShowDiscrepancyModal(false);
      setShowBusinessInfoModal(false);
    } catch (err: unknown) {
      if (err instanceof ReportApiError && err.errorData?.error === 'discrepancy_not_acknowledged') {
        setShowDiscrepancyModal(true);
      } else {
        const msg = err instanceof Error ? err.message : 'Failed to generate Business Sales Statement.';
        setPdfError(msg);
      }
    } finally {
      setIsGeneratingPdf(false);
    }
  };

  // Click handler for PDF generation button
  const handleDownloadPdfClick = () => {
    if (isExportBlocked) {
      setPdfError(
        `Step 2 Review Required: ${needsReviewCount} transaction(s) have unresolved issues. Please review, edit, or delete them before generating the statement.`
      );
      return;
    }

    // If business details are missing, prompt user to enter them
    if (!businessName.trim() && !businessAddress.trim()) {
      setTempBizName(businessName);
      setTempBizAddress(businessAddress);
      setShowBusinessInfoModal(true);
      return;
    }

    if (hasAnyDiscrepancies && !hasAcknowledgedDiscrepancies) {
      setShowDiscrepancyModal(true);
      return;
    }

    executeDownload(businessName, businessAddress, hasAcknowledgedDiscrepancies);
  };

  // Handler when business info modal is saved
  const handleSaveBusinessInfo = (e: React.FormEvent) => {
    e.preventDefault();
    const finalName = tempBizName.trim();
    const finalAddr = tempBizAddress.trim();

    setBusinessName(finalName);
    setBusinessAddress(finalAddr);

    if (rememberBusinessDetails) {
      try {
        localStorage.setItem(
          LOCAL_STORAGE_BIZ_KEY,
          JSON.stringify({ businessName: finalName, businessAddress: finalAddr })
        );
      } catch {
        // ignore
      }
    } else {
      try {
        localStorage.removeItem(LOCAL_STORAGE_BIZ_KEY);
      } catch {
        // ignore
      }
    }

    setShowBusinessInfoModal(false);

    if (hasAnyDiscrepancies && !hasAcknowledgedDiscrepancies) {
      setShowDiscrepancyModal(true);
      return;
    }

    executeDownload(finalName, finalAddr, hasAcknowledgedDiscrepancies);
  };

  const handleAcknowledgeAndDownload = () => {
    setHasAcknowledgedDiscrepancies(true);
    executeDownload(businessName, businessAddress, true);
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

          {/* Transparent Status Pill */}
          <div
            className={`extraction-dashboard__status-pill ${
              isExportBlocked
                ? 'extraction-dashboard__status-pill--pending'
                : 'extraction-dashboard__status-pill--ready'
            }`}
            title={
              isExportBlocked
                ? `${needsReviewCount} transaction(s) require review before statement export`
                : 'All transactions verified. Ready for statement export.'
            }
          >
            {isExportBlocked ? (
              <>
                <AlertTriangle size={15} aria-hidden="true" />
                <span>{needsReviewCount} Requires Review</span>
              </>
            ) : (
              <>
                <ShieldCheck size={15} aria-hidden="true" />
                <span>All {totalEntries} Entries Verified</span>
              </>
            )}
          </div>

          {/* Download Business Sales Statement Action */}
          <button
            type="button"
            className={`extraction-dashboard__download-btn ${
              isExportBlocked ? 'extraction-dashboard__download-btn--blocked' : ''
            }`}
            onClick={handleDownloadPdfClick}
            disabled={isGeneratingPdf}
            title={
              isExportBlocked
                ? `Review Required: Please resolve ${needsReviewCount} flagged transaction(s) in Step 2 first.`
                : 'Download accountant-prepared Business Sales Statement PDF for loan documentation'
            }
            aria-label="Download Business Sales Statement PDF"
          >
            {isGeneratingPdf ? (
              <>
                <Loader2 size={15} className="extraction-dashboard__spin" aria-hidden="true" />
                <span>Generating...</span>
              </>
            ) : isExportBlocked ? (
              <>
                <AlertTriangle size={15} aria-hidden="true" />
                <span>Resolve {needsReviewCount} Issue(s)</span>
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
              {/* Only show review banner if genuine issues exist */}
              {needsReviewCount > 0 && (
                <div className="extraction-dashboard__gate-banner" role="alert">
                  <div className="extraction-dashboard__gate-icon-wrap">
                    <AlertTriangle size={22} aria-hidden="true" />
                  </div>
                  <div className="extraction-dashboard__gate-text">
                    <h3 className="extraction-dashboard__gate-title">
                      Action Required: {needsReviewCount} Transaction(s) Need Attention
                    </h3>
                    <p className="extraction-dashboard__gate-desc">
                      High-confidence entries were automatically accepted. Please review the highlighted
                      items with missing amounts or uncertain readings before generating the statement.
                    </p>
                    <div className="extraction-dashboard__gate-actions">
                      <button
                        type="button"
                        className="extraction-dashboard__gate-btn extraction-dashboard__gate-btn--primary"
                        onClick={handleReviewNextFlagged}
                      >
                        <Pencil size={14} aria-hidden="true" />
                        <span>Review Flagged Entry</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

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

                  {autoAcceptedCount > 0 && (
                    <div className="extraction-dashboard__metric extraction-dashboard__metric--auto">
                      <Check size={16} aria-hidden="true" />
                      <span className="extraction-dashboard__metric-label">Auto Verified:</span>
                      <strong className="extraction-dashboard__metric-value tabular-nums">
                        {autoAcceptedCount}
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

                  {needsReviewCount > 0 && (
                    <div className="extraction-dashboard__metric extraction-dashboard__metric--flagged">
                      <AlertTriangle size={16} aria-hidden="true" />
                      <span className="extraction-dashboard__metric-label">Needs Review:</span>
                      <strong className="extraction-dashboard__metric-value tabular-nums">
                        {needsReviewCount}
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
                        {/* Group Header */}
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

                          {/* Written Subtotal and Calculated Sum */}
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

                        {/* Arithmetic Feedback Card */}
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
                                  Totaling mismatch detected
                                </p>
                                <p className="extraction-group__feedback-msg">
                                  Your written total is <strong>₹{writtenSubtotal}</strong>, but
                                  the listed entries add up to <strong>₹{calculatedSum}</strong>{' '}
                                  (difference of ₹{Math.abs(writtenSubtotal - calculatedSum)}).
                                </p>
                                {unpricedInGroup.length > 0 && (
                                  <p className="extraction-group__feedback-note">
                                    Note: {unpricedInGroup.length}{' '}
                                    {unpricedInGroup.length === 1 ? 'entry' : 'entries'} has no recorded price.
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
                              </div>
                            </div>
                          )
                        ) : null}

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
                                  Actions
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.entries.length === 0 ? (
                                <tr>
                                  <td colSpan={6} className="extraction-table__empty-cell">
                                    All entries in this section were deleted.
                                  </td>
                                </tr>
                              ) : (
                                group.entries.map((entry, eIdx) => {
                                  const status = getEntryStatus(entry);
                                  const isFlagged = status === 'needs_review';
                                  const isReviewed = status === 'human_reviewed';
                                  const isAuto = status === 'auto_accepted';
                                  const unpriced = isEntryUnpriced(entry);

                                  const effectiveDesc = getEffectiveDescription(entry);
                                  const effectiveAmt = getEffectiveAmount(entry);

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
                                                entry.amount !== null
                                                  ? `₹${entry.amount}`
                                                  : 'Not recorded'
                                              }`}
                                            >
                                              Orig:{' '}
                                              {entry.amount !== null
                                                ? `₹${entry.amount}`
                                                : 'Not recorded'}
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
                                            <span>Reviewed</span>
                                          </div>
                                        ) : isFlagged ? (
                                          <div
                                            className="extraction-table__flag-pill"
                                            title={entry.flag_reason || 'Needs review'}
                                          >
                                            <AlertTriangle size={13} aria-hidden="true" />
                                            <span>Needs Review</span>
                                          </div>
                                        ) : isAuto ? (
                                          <span
                                            className="extraction-table__auto-pill"
                                            title="High confidence transcription"
                                          >
                                            <Check size={13} aria-hidden="true" />
                                            <span>Accepted</span>
                                          </span>
                                        ) : null}
                                        {!isReviewed && isFlagged && entry.flag_reason && (
                                          <span className="extraction-table__flag-reason">
                                            {entry.flag_reason}
                                          </span>
                                        )}
                                      </td>
                                      <td className="extraction-table__td-action">
                                        <div className="extraction-table__actions-group">
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
                                            aria-label={`Edit entry #${
                                              entry.entry_index || eIdx + 1
                                            }`}
                                          >
                                            <Pencil size={13} aria-hidden="true" />
                                            <span>{isFlagged ? 'Review' : 'Edit'}</span>
                                          </button>

                                          <button
                                            type="button"
                                            className="extraction-table__delete-btn"
                                            onClick={() =>
                                              setEntryToDelete({
                                                groupIndex: gIdx,
                                                entryIndex: eIdx,
                                              })
                                            }
                                            title="Delete this transaction"
                                            aria-label={`Delete entry #${
                                              entry.entry_index || eIdx + 1
                                            }`}
                                          >
                                            <Trash2 size={13} aria-hidden="true" />
                                          </button>
                                        </div>
                                      </td>
                                    </tr>
                                  );
                                })
                              )}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    );
                  }
                )}
              </div>

              {/* Page Financial Reconciliation */}
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
                      Sales Total Overview
                    </h3>
                    <p className="extraction-dashboard__reconciliation-subtitle">
                      Summary of individual entries and written section subtotals.
                    </p>
                  </div>
                </div>

                <div className="extraction-dashboard__reconciliation-grid">
                  <div className="extraction-dashboard__reconciliation-item">
                    <span className="extraction-dashboard__reconciliation-item-label">
                      Sum of Entries
                    </span>
                    <strong className="extraction-dashboard__reconciliation-item-val tabular-nums">
                      ₹{pageCalculatedEntriesSum}
                    </strong>
                    <span className="extraction-dashboard__reconciliation-item-desc">
                      Sum of {totalEntries - unpricedEntries} priced items across all sections
                    </span>
                  </div>

                  <div className="extraction-dashboard__reconciliation-item">
                    <span className="extraction-dashboard__reconciliation-item-label">
                      Sum of Written Subtotals
                    </span>
                    <strong className="extraction-dashboard__reconciliation-item-val tabular-nums">
                      {groupsWithWrittenSubtotal.length > 0
                        ? `₹${sumOfGroupSubtotals}`
                        : 'None written'}
                    </strong>
                    <span className="extraction-dashboard__reconciliation-item-desc">
                      {groupsWithWrittenSubtotal.length} of {currentExtraction.groups.length}{' '}
                      sections have written subtotals
                    </span>
                  </div>

                  <div className="extraction-dashboard__reconciliation-item">
                    <span className="extraction-dashboard__reconciliation-item-label">
                      Written Page Total
                    </span>
                    <strong className="extraction-dashboard__reconciliation-item-val tabular-nums">
                      {writtenPageTotal !== null ? `₹${writtenPageTotal}` : 'Not recorded'}
                    </strong>
                    <span className="extraction-dashboard__reconciliation-item-desc">
                      Total written at bottom of physical page
                    </span>
                  </div>
                </div>
              </section>

              {/* Export Business Sales Statement Card */}
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
                        Download a formal, accountant-prepared Business Sales Statement and Daily Sales Register
                        suitable as supporting financial records for loan applications.
                      </p>
                    </div>
                  </div>

                  {/* Business Details Preview Card with Edit Action */}
                  <div className="extraction-dashboard__biz-preview-card">
                    <Building2 size={16} className="extraction-dashboard__biz-icon" aria-hidden="true" />
                    <div className="extraction-dashboard__biz-text">
                      <span className="extraction-dashboard__biz-label">Business Information on Statement:</span>
                      <strong className="extraction-dashboard__biz-val">
                        {businessName ? (
                          <>
                            {businessName}
                            {businessAddress && ` • ${businessAddress}`}
                          </>
                        ) : (
                          <span className="extraction-dashboard__biz-empty">
                            No business details entered (Click edit to add)
                          </span>
                        )}
                      </strong>
                    </div>
                    <button
                      type="button"
                      className="extraction-dashboard__biz-edit-btn"
                      onClick={() => {
                        setTempBizName(businessName);
                        setTempBizAddress(businessAddress);
                        setShowBusinessInfoModal(true);
                      }}
                    >
                      <Pencil size={13} aria-hidden="true" />
                      <span>{businessName ? 'Edit Details' : 'Add Details'}</span>
                    </button>
                  </div>

                  {/* Warning if export is blocked by unresolved flags */}
                  {isExportBlocked && (
                    <div className="extraction-dashboard__gate-callout" role="alert">
                      <AlertTriangle size={16} aria-hidden="true" />
                      <span>
                        Statement generation blocked: <strong>{needsReviewCount}</strong> transaction(s) require review in Step 2.
                      </span>
                    </div>
                  )}

                  {pdfError && (
                    <div className="extraction-dashboard__export-error" role="alert">
                      <AlertTriangle size={15} aria-hidden="true" />
                      <span>{pdfError}</span>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className={`extraction-dashboard__export-btn ${
                    isExportBlocked ? 'extraction-dashboard__export-btn--blocked' : ''
                  }`}
                  onClick={handleDownloadPdfClick}
                  disabled={isGeneratingPdf}
                  aria-label="Generate and download Business Sales Statement PDF"
                >
                  {isGeneratingPdf ? (
                    <>
                      <Loader2 size={16} className="extraction-dashboard__spin" aria-hidden="true" />
                      <span>Generating Statement...</span>
                    </>
                  ) : isExportBlocked ? (
                    <>
                      <AlertTriangle size={16} aria-hidden="true" />
                      <span>Review Required ({needsReviewCount})</span>
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
          onDelete={() => {
            const coords = activeReviewCoords;
            setActiveReviewCoords(null);
            setEntryToDelete(coords);
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {entryToDelete && targetDeleteEntry && (
        <div
          className="review-modal__backdrop"
          onClick={() => setEntryToDelete(null)}
          role="presentation"
        >
          <div
            className="review-modal review-modal--confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="review-modal__header">
              <div className="review-modal__title-wrap">
                <div className="review-modal__icon-badge review-modal__icon-badge--danger">
                  <Trash2 size={18} aria-hidden="true" />
                </div>
                <div>
                  <h2 id="delete-modal-title" className="review-modal__title">
                    Delete Transaction
                  </h2>
                  <span className="review-modal__subtitle marathi-font">
                    {targetDeleteGroupTitle}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="review-modal__close-btn"
                onClick={() => setEntryToDelete(null)}
                aria-label="Cancel deletion"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </header>

            <div className="review-modal__body">
              <p className="extraction-dashboard__confirm-msg">
                Are you sure you want to delete this transaction from the records?
              </p>

              <div className="review-modal__confirm-entry-card">
                <div>
                  <strong className="marathi-font">
                    {getEffectiveDescription(targetDeleteEntry) || 'Transaction Item'}
                  </strong>
                  <span className="extraction-dashboard__confirm-entry-meta">
                    Row #{targetDeleteEntry.entry_index}
                  </span>
                </div>
                <strong className="tabular-nums">
                  {!isEntryUnpriced(targetDeleteEntry)
                    ? `₹${getEffectiveAmount(targetDeleteEntry)}`
                    : 'Not Recorded'}
                </strong>
              </div>

              <p className="extraction-dashboard__confirm-warning">
                <AlertCircle size={15} aria-hidden="true" />
                <span>
                  This transaction will be completely excluded from all calculated totals and will not appear in the generated statement.
                </span>
              </p>
            </div>

            <footer className="review-modal__footer">
              <button
                type="button"
                className="review-modal__cancel-btn"
                onClick={() => setEntryToDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="review-modal__delete-btn"
                onClick={handleExecuteDelete}
              >
                <Trash2 size={15} aria-hidden="true" />
                <span>Confirm Delete</span>
              </button>
            </footer>
          </div>
        </div>
      )}

      {/* Business Information Collection Modal */}
      {showBusinessInfoModal && (
        <div
          className="review-modal__backdrop"
          onClick={() => setShowBusinessInfoModal(false)}
          role="presentation"
        >
          <div
            className="review-modal review-modal--biz-info"
            role="dialog"
            aria-modal="true"
            aria-labelledby="biz-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="review-modal__header">
              <div className="review-modal__title-wrap">
                <div className="review-modal__icon-badge">
                  <Building2 size={18} aria-hidden="true" />
                </div>
                <div>
                  <h2 id="biz-modal-title" className="review-modal__title">
                    Business Information
                  </h2>
                  <span className="review-modal__subtitle">
                    Enter details to appear on your official Sales Statement
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="review-modal__close-btn"
                onClick={() => setShowBusinessInfoModal(false)}
                aria-label="Close dialog"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </header>

            <form onSubmit={handleSaveBusinessInfo}>
              <div className="review-modal__body">
                <div className="review-modal__field">
                  <label htmlFor="biz-name-input" className="review-modal__label">
                    <span>Business / Trade Name</span>
                    <span className="review-modal__label-hint">As registered or known locally</span>
                  </label>
                  <input
                    id="biz-name-input"
                    type="text"
                    className="review-modal__input"
                    value={tempBizName}
                    onChange={(e) => setTempBizName(e.target.value)}
                    placeholder="e.g. Asha Beauty Parlour"
                    autoFocus
                  />
                </div>

                <div className="review-modal__field">
                  <label htmlFor="biz-addr-input" className="review-modal__label">
                    <span>Business Address</span>
                    <span className="review-modal__label-hint">Shop number, street, city</span>
                  </label>
                  <input
                    id="biz-addr-input"
                    type="text"
                    className="review-modal__input"
                    value={tempBizAddress}
                    onChange={(e) => setTempBizAddress(e.target.value)}
                    placeholder="e.g. Shop No. 4, Shivaji Chowk, Pune"
                  />
                </div>

                <label className="extraction-dashboard__discrepancy-checkbox-label">
                  <input
                    type="checkbox"
                    checked={rememberBusinessDetails}
                    onChange={(e) => setRememberBusinessDetails(e.target.checked)}
                  />
                  <span>
                    Remember business details for future statements on this browser
                  </span>
                </label>
              </div>

              <footer className="review-modal__footer">
                <button
                  type="button"
                  className="review-modal__cancel-btn"
                  onClick={() => setShowBusinessInfoModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="review-modal__save-btn"
                >
                  <CheckCircle2 size={16} aria-hidden="true" />
                  <span>Save & Continue to PDF</span>
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}

      {/* Discrepancy Acknowledgment Modal */}
      {showDiscrepancyModal && (
        <div
          className="review-modal__backdrop"
          onClick={() => setShowDiscrepancyModal(false)}
          role="presentation"
        >
          <div
            className="review-modal review-modal--discrepancy"
            role="dialog"
            aria-modal="true"
            aria-labelledby="discrepancy-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="review-modal__header">
              <div className="review-modal__title-wrap">
                <div className="review-modal__icon-badge review-modal__icon-badge--warning">
                  <AlertTriangle size={18} aria-hidden="true" />
                </div>
                <div>
                  <h2 id="discrepancy-modal-title" className="review-modal__title">
                    Acknowledge Subtotal Difference
                  </h2>
                  <span className="review-modal__subtitle">
                    Handwritten subtotal differs from sum of entries
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="review-modal__close-btn"
                onClick={() => setShowDiscrepancyModal(false)}
                aria-label="Close dialog"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </header>

            <div className="review-modal__body">
              <p className="extraction-dashboard__discrepancy-intro">
                The handwritten subtotals on the notebook differ from the arithmetic sum of the listed items:
              </p>

              <div className="extraction-dashboard__discrepancy-list">
                {groupDiscrepancies.map((d, idx) => (
                  <div key={idx} className="extraction-dashboard__discrepancy-item">
                    <div className="extraction-dashboard__discrepancy-item-header">
                      <strong className="marathi-font">{d.sectionLabel}</strong>
                      <span className="extraction-dashboard__discrepancy-diff tabular-nums">
                        Difference: ₹{Math.abs(d.difference).toFixed(2)}
                      </span>
                    </div>
                    <div className="extraction-dashboard__discrepancy-details">
                      <span>Written: <strong>₹{d.writtenSubtotal.toFixed(2)}</strong></span>
                      <span>Sum: <strong>₹{d.calculatedTotal.toFixed(2)}</strong></span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="extraction-dashboard__discrepancy-note">
                <Info size={16} aria-hidden="true" />
                <p>
                  The sales statement will report the verified line-item sales total. Please acknowledge that you have reviewed this arithmetic difference before continuing.
                </p>
              </div>

              <label className="extraction-dashboard__discrepancy-checkbox-label">
                <input
                  type="checkbox"
                  checked={discrepancyAcknowledged}
                  onChange={(e) => setDiscrepancyAcknowledged(e.target.checked)}
                />
                <span>
                  I acknowledge this difference and confirm the sales entries are accurate.
                </span>
              </label>
            </div>

            <footer className="review-modal__footer">
              <button
                type="button"
                className="review-modal__cancel-btn"
                onClick={() => setShowDiscrepancyModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="review-modal__save-btn"
                disabled={!discrepancyAcknowledged || isGeneratingPdf}
                onClick={handleAcknowledgeAndDownload}
              >
                {isGeneratingPdf ? (
                  <>
                    <Loader2 size={16} className="extraction-dashboard__spin" />
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <Download size={16} />
                    <span>Acknowledge & Download PDF</span>
                  </>
                )}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
