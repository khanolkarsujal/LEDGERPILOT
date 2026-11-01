/**
 * Structured extraction types returned by the extraction API.
 * Mirrors the Pydantic schemas in backend/app/schemas/ledger.py
 * and backend/app/api/extract.py.
 */

export type EntryType = 'income' | 'expense' | 'credit' | 'debit' | 'unknown';

export type ReviewStatus = 'ai_extracted' | 'needs_review' | 'human_reviewed' | 'auto_accepted';

export interface ExtractedLedgerEntry {
  entry_index: number;
  // Immutable raw AI extraction values
  raw_marathi_text: string | null;
  amount: string | number | null;
  entry_type: EntryType;
  uncertain_fields: string[];
  flag_reason: string | null;

  // Human Review & Correction tracking
  review_status?: ReviewStatus;
  corrected_marathi_text?: string | null;
  corrected_amount?: string | number | null;
  reviewed_at?: string | null;
  review_note?: string | null;
}

export interface ExtractedTransactionGroup {
  group_id: string;
  date_raw: string | null;
  date_iso: string | null;
  entries: ExtractedLedgerEntry[];
  recorded_group_total: string | number | null;
  notes: string | null;
}

export interface LedgerPageExtraction {
  page_summary: string;
  groups: ExtractedTransactionGroup[];
  recorded_page_total: string | number | null;
  unreadable_sections_found: boolean;
}

export type ProcessingStage =
  | 'upload_received'
  | 'preprocessing'
  | 'gemini_request_started'
  | 'waiting_gemini'
  | 'parsing_extraction'
  | 'completed'
  | 'failed';

export interface JobEvent {
  timestamp: number;
  iso_time: string;
  stage: ProcessingStage;
  message: string;
  details?: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  filename: string;
  file_size_bytes: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  current_stage: ProcessingStage;
  stage_message: string;
  events: JobEvent[];
  elapsed_time_s: number;
  result: LedgerPageExtraction | null;
  error: string | null;
  error_code?: string | null;
}
