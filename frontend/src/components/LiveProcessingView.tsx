import { useState, useEffect } from 'react';
import {
  Loader2,
  CheckCircle2,
  Circle,
  AlertTriangle,
  Clock,
  Radio,
  FileText,
  Server,
  Layers,
} from 'lucide-react';
import { isGeminiDailyQuotaError } from '../api';
import type { JobStatusResponse, ProcessingStage, JobEvent } from '../types/extraction';
import './LiveProcessingView.css';

interface LiveProcessingViewProps {
  job: JobStatusResponse | null;
  selectedFile: File;
  previewUrl: string;
  errorMessage: string | null;
  onRetry: () => void;
  onCancel: () => void;
}

interface StageStep {
  id: ProcessingStage;
  label: string;
  description: string;
}

const STAGES: StageStep[] = [
  {
    id: 'upload_received',
    label: 'Upload Received',
    description: 'Image received and payload validated by backend',
  },
  {
    id: 'preprocessing',
    label: 'Image Preprocessing',
    description: 'EXIF orientation corrected and Pillow image normalized',
  },
  {
    id: 'gemini_request_started',
    label: 'API Request Started',
    description: 'Gemini 3 Flash Vision pipeline initialized with Pydantic schema',
  },
  {
    id: 'waiting_gemini',
    label: 'Waiting for Gemini',
    description: 'Transcribing Marathi text, entries, amounts, and subtotals',
  },
  {
    id: 'parsing_extraction',
    label: 'Parsing Extraction',
    description: 'Validating structured JSON response against ledger schemas',
  },
  {
    id: 'completed',
    label: 'Extraction Completed',
    description: 'Structured ledger records ready for verification',
  },
];

const STAGE_ORDER: Record<ProcessingStage, number> = {
  upload_received: 0,
  preprocessing: 1,
  gemini_request_started: 2,
  waiting_gemini: 3,
  parsing_extraction: 4,
  completed: 5,
  failed: -1,
};

export function LiveProcessingView({
  job,
  selectedFile,
  previewUrl,
  errorMessage,
  onRetry,
  onCancel,
}: LiveProcessingViewProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  // Live timer tick every 100ms for smooth feedback
  useEffect(() => {
    if (!job || job.status === 'completed' || job.status === 'failed') return;
    const interval = setInterval(() => {
      setElapsedSeconds((prev) => +(prev + 0.1).toFixed(1));
    }, 100);
    return () => clearInterval(interval);
  }, [job]);

  // Sync with backend reported elapsed time when available
  useEffect(() => {
    if (job?.elapsed_time_s !== undefined && job.elapsed_time_s > 0) {
      setElapsedSeconds(job.elapsed_time_s);
    }
  }, [job?.elapsed_time_s]);

  const currentStage: ProcessingStage = job?.current_stage || 'upload_received';
  const currentStageIndex = STAGE_ORDER[currentStage] ?? 0;
  const isFailed = job?.status === 'failed' || !!errorMessage;
  const isDailyQuota = isGeminiDailyQuotaError(
    errorMessage,
    errorMessage || job?.error,
    job?.error_code
  );
  const displayedError =
    errorMessage ||
    job?.error ||
    (isDailyQuota
      ? 'The daily Gemini quota has been reached. Existing extraction results have been preserved.'
      : 'Unknown extraction error');

  return (
    <div className="live-processing" aria-live="polite">
      {/* Top Header Card */}
      <div className="live-processing__header-card">
        <div className="live-processing__status-row">
          <div className="live-processing__connection-badge">
            <span className="live-processing__connection-dot" aria-hidden="true" />
            <Server size={14} aria-hidden="true" />
            <span>FastAPI Backend Active (127.0.0.1:8000)</span>
          </div>

          <div className="live-processing__timer-badge">
            <Clock size={14} aria-hidden="true" />
            <span>Elapsed: {elapsedSeconds.toFixed(1)}s</span>
          </div>
        </div>

        <div className="live-processing__headline">
          {isFailed ? (
            <div className="live-processing__title-wrap live-processing__title-wrap--failed">
              <AlertTriangle size={28} className="live-processing__icon-alert" aria-hidden="true" />
              <div>
                <h2 className="live-processing__title">
                  {isDailyQuota ? 'Daily Gemini quota reached' : 'Extraction Failed'}
                </h2>
                <p className="live-processing__subtitle">
                  {isDailyQuota
                    ? 'The daily Gemini quota has been reached. Existing extraction results have been preserved.'
                    : 'The backend encountered an error while processing this ledger photograph.'}
                </p>
              </div>
            </div>
          ) : (
            <div className="live-processing__title-wrap">
              <Loader2 size={28} className="live-processing__spinner" aria-hidden="true" />
              <div>
                <h2 className="live-processing__title">
                  {job?.stage_message || 'Processing Ledger Photograph...'}
                </h2>
                <p className="live-processing__subtitle">
                  Target: <strong>{selectedFile.name}</strong> • Live backend pipeline active
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Grid: Pipeline stages on left, Activity Panel on right */}
      <div className="live-processing__body-grid">
        {/* Left Column: Stages Timeline & Photo thumbnail */}
        <div className="live-processing__left-col">
          {/* Compact Photo Preview Card */}
          <div className="live-processing__thumb-card">
            <img
              src={previewUrl}
              alt={`Selected ledger: ${selectedFile.name}`}
              className="live-processing__thumb-img"
            />
            <div className="live-processing__thumb-info">
              <div className="live-processing__thumb-name" title={selectedFile.name}>
                <FileText size={16} aria-hidden="true" />
                <span>{selectedFile.name}</span>
              </div>
              <span className="live-processing__thumb-meta">
                {(selectedFile.size / 1024).toFixed(1)} KB • {selectedFile.type || 'image'}
              </span>
            </div>
          </div>

          {/* Sequential Stages List */}
          <div className="live-processing__stages-card">
            <h3 className="live-processing__stages-title">
              <Layers size={16} aria-hidden="true" />
              <span>Confirmed Backend Stages</span>
            </h3>

            <ol className="live-processing__stages-list">
              {STAGES.map((st, idx) => {
                let statusClass = 'pending';
                if (isFailed && idx === currentStageIndex) {
                  statusClass = 'failed';
                } else if (idx < currentStageIndex) {
                  statusClass = 'completed';
                } else if (idx === currentStageIndex) {
                  statusClass = 'active';
                }

                return (
                  <li
                    key={st.id}
                    className={`live-processing__stage-item live-processing__stage-item--${statusClass}`}
                  >
                    <div className="live-processing__stage-bullet">
                      {statusClass === 'completed' && (
                        <CheckCircle2 size={18} className="live-processing__icon-done" />
                      )}
                      {statusClass === 'active' && (
                        <Loader2 size={18} className="live-processing__spinner live-processing__icon-active" />
                      )}
                      {statusClass === 'pending' && (
                        <Circle size={18} className="live-processing__icon-pending" />
                      )}
                      {statusClass === 'failed' && (
                        <AlertTriangle size={18} className="live-processing__icon-failed" />
                      )}
                    </div>
                    <div className="live-processing__stage-content">
                      <div className="live-processing__stage-label-row">
                        <span className="live-processing__stage-label">{st.label}</span>
                        {statusClass === 'active' && (
                          <span className="live-processing__stage-tag">In Progress</span>
                        )}
                      </div>
                      <p className="live-processing__stage-desc">{st.description}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>

        {/* Right Column: Real Backend Activity Panel */}
        <div className="live-processing__right-col">
          <div className="live-processing__activity-card">
            <div className="live-processing__activity-header">
              <div className="live-processing__activity-title-group">
                <Radio size={16} className="live-processing__activity-live-icon" aria-hidden="true" />
                <h3 className="live-processing__activity-title">Live Backend Activity Events</h3>
              </div>
              <span className="live-processing__event-count">
                {job?.events.length || 0} events recorded
              </span>
            </div>

            <div className="live-processing__events-feed" role="log" aria-label="Backend events">
              {job?.events && job.events.length > 0 ? (
                job.events.map((ev: JobEvent, i: number) => {
                  const evDate = new Date(ev.timestamp * 1000);
                  const timeFormatted = evDate.toLocaleTimeString(undefined, {
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  });
                  const ms = String(evDate.getMilliseconds()).padStart(3, '0');

                  return (
                    <div key={i} className="live-processing__event-row">
                      <div className="live-processing__event-time">
                        {timeFormatted}.{ms}
                      </div>
                      <div className="live-processing__event-body">
                        <div className="live-processing__event-pill">
                          <span className="live-processing__event-stage">{ev.stage}</span>
                        </div>
                        <p className="live-processing__event-msg">{ev.message}</p>
                        {ev.details && (
                          <span className="live-processing__event-details">{ev.details}</span>
                        )}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="live-processing__events-empty">
                  <p>Awaiting initial events from FastAPI backend...</p>
                </div>
              )}
            </div>

            {/* Error Message Box if failed */}
            {isFailed && (
              <div className="live-processing__error-box" role="alert">
                <div className="live-processing__error-header">
                  <AlertTriangle size={18} aria-hidden="true" />
                  <strong>Backend Error Details</strong>
                </div>
                <p className="live-processing__error-text">{displayedError}</p>
                <div className="live-processing__error-actions">
                  {!isDailyQuota && (
                    <button
                      type="button"
                      className="live-processing__btn live-processing__btn--retry"
                      onClick={onRetry}
                    >
                      <span>Try Again</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className="live-processing__btn live-processing__btn--cancel"
                    onClick={onCancel}
                  >
                    <span>Cancel & Choose Another Photo</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
