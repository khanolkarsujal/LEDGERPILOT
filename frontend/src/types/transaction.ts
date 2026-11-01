/**
 * Transaction row extracted from a handwritten ledger page.
 *
 * Schema defined in architecture.md → Core Data Shape.
 * This is the single source of truth for the row type —
 * reused across every component and API call.
 */

/** Transaction classification */
export type TransactionType = 'credit' | 'debit';

/** Row review status */
export type RowStatus = 'ok' | 'flagged';

/** One row from a ledger page */
export interface TransactionRow {
  /** Date in ISO 8601 format (YYYY-MM-DD), or null if unreadable */
  date: string | null;

  /** Description of the transaction, or null if unreadable */
  description: string | null;

  /** Amount as a string (to avoid floating-point issues), or null if unreadable */
  amount: string | null;

  /** Credit or debit, or null if unreadable */
  type: TransactionType | null;

  /** Whether this row passed validation */
  status: RowStatus;

  /** Short reason for flagging, e.g. "amount unreadable" */
  flag_reason: string | null;

  /** Position on the original page for highlighting in the photo */
  source_row: number | null;
}
