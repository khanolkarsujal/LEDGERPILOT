import type { LedgerPageExtraction } from '../types/extraction';

export class ReportApiError extends Error {
  statusCode: number;
  errorData?: any;

  constructor(message: string, statusCode: number, errorData?: any) {
    super(message);
    this.name = 'ReportApiError';
    this.statusCode = statusCode;
    this.errorData = errorData;
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
 * @param acknowledgeDiscrepancies Whether the user has explicitly acknowledged totaling discrepancies.
 * @returns Blob of the binary PDF file.
 */
export async function downloadPDFReport(
  extraction: LedgerPageExtraction,
  businessName?: string,
  businessAddress?: string,
  natureOfBusiness?: string,
  statementReference?: string,
  acknowledgeDiscrepancies: boolean = false
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
        acknowledge_discrepancies: acknowledgeDiscrepancies,
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
    let parsedData: any = null;
    try {
      const errJson = await response.json();
      if (errJson) {
        parsedData = errJson.detail || errJson;
        if (typeof errJson.detail === 'string') {
          errorDetail = errJson.detail;
        } else if (errJson.detail && errJson.detail.message) {
          errorDetail = errJson.detail.message;
        }
      }
    } catch {
      // response was not JSON
    }
    throw new ReportApiError(errorDetail, response.status, parsedData);
  }

  return await response.blob();
}
