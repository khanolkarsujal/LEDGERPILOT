import type { LedgerPageExtraction } from '../types/extraction';

export class ReportApiError extends Error {
  statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = 'ReportApiError';
    this.statusCode = statusCode;
  }
}

/**
 * Requests the backend to generate a professional Business Sales Statement PDF.
 * Uses the latest session state (including human corrections).
 *
 * @param extraction The current LedgerPageExtraction data.
 * @param businessName Optional business or trade name.
 * @param businessAddress Optional business physical address.
 * @param natureOfBusiness Optional nature/trade category of business.
 * @param statementReference Optional statement reference.
 * @returns Blob of the binary PDF file.
 */
export async function downloadPDFReport(
  extraction: LedgerPageExtraction,
  businessName?: string,
  businessAddress?: string,
  natureOfBusiness?: string,
  statementReference?: string
): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch('/api/reports/pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        extraction,
        business_name: businessName || null,
        business_address: businessAddress || null,
        nature_of_business: natureOfBusiness || null,
        statement_reference: statementReference || null,
      }),
    });
  } catch {
    throw new ReportApiError(
      'Could not connect to backend to generate PDF. Please ensure FastAPI is running.',
      0
    );
  }

  if (!response.ok) {
    let errorDetail = `Failed to generate PDF report (HTTP ${response.status})`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // response was not JSON
    }
    throw new ReportApiError(errorDetail, response.status);
  }

  return await response.blob();
}

