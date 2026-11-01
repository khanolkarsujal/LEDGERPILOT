import type { JobStatusResponse, LedgerPageExtraction } from '../types/extraction';

export class ExtractionApiError extends Error {
  statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = 'ExtractionApiError';
    this.statusCode = statusCode;
  }
}

/**
 * Creates a background extraction job via POST /api/extract/jobs.
 */
export async function createExtractionJob(file: File): Promise<JobStatusResponse> {
  const formData = new FormData();
  formData.append('file', file, file.name);

  let response: Response;
  try {
    response = await fetch('/api/extract/jobs', {
      method: 'POST',
      body: formData,
    });
  } catch {
    throw new ExtractionApiError(
      'Could not connect to the backend server. Please verify FastAPI is running at http://127.0.0.1:8000.',
      0
    );
  }

  if (!response.ok) {
    let errorDetail = `Failed to create extraction job (HTTP ${response.status})`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // response was not JSON
    }
    throw new ExtractionApiError(errorDetail, response.status);
  }

  const data: JobStatusResponse = await response.json();
  return data;
}

/**
 * Polls the job status endpoint GET /api/extract/jobs/{jobId}.
 */
export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  let response: Response;
  try {
    response = await fetch(`/api/extract/jobs/${jobId}`);
  } catch {
    throw new ExtractionApiError(
      'Lost connection to backend server while polling extraction status.',
      0
    );
  }

  if (!response.ok) {
    let errorDetail = `Failed to fetch job status (HTTP ${response.status})`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // ignore
    }
    throw new ExtractionApiError(errorDetail, response.status);
  }

  const data: JobStatusResponse = await response.json();
  return data;
}

/**
 * Polls an extraction job until it completes or fails, notifying onUpdate with every new state.
 */
export async function pollExtractionJob(
  jobId: string,
  onUpdate: (job: JobStatusResponse) => void,
  pollIntervalMs = 800,
  maxTimeoutMs = 180000
): Promise<JobStatusResponse> {
  const startTime = Date.now();

  while (Date.now() - startTime < maxTimeoutMs) {
    const job = await getJobStatus(jobId);
    onUpdate(job);

    if (job.status === 'completed') {
      return job;
    }

    if (job.status === 'failed') {
      throw new ExtractionApiError(
        job.error || 'Extraction failed on the backend without specific error details.',
        500
      );
    }

    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  throw new ExtractionApiError('Extraction timed out after 3 minutes.', 504);
}

/**
 * Synchronous direct fallback if needed.
 */
export async function extractLedgerImage(file: File): Promise<LedgerPageExtraction> {
  const job = await createExtractionJob(file);
  const completedJob = await pollExtractionJob(job.job_id, () => {});
  if (!completedJob.result) {
    throw new ExtractionApiError('Job completed but returned no extraction payload.', 500);
  }
  return completedJob.result;
}
