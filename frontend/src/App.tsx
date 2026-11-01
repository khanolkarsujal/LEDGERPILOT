import { useState } from 'react';
import { StepHeader, type Step, UploadView, ExtractionResultView } from './components';
import type { LedgerPageExtraction, JobEvent } from './types/extraction';
import './App.css';

interface ExtractionSession {
  result: LedgerPageExtraction;
  file: File;
  previewUrl: string;
  events: JobEvent[];
}

function App() {
  const [currentStep, setCurrentStep] = useState<Step>('upload');
  const [session, setSession] = useState<ExtractionSession | null>(null);

  const handleExtractionSuccess = (
    result: LedgerPageExtraction,
    file: File,
    previewUrl: string,
    events: JobEvent[]
  ) => {
    setSession({ result, file, previewUrl, events });
    setCurrentStep('review');
  };

  const handleReset = () => {
    setSession(null);
    setCurrentStep('upload');
  };

  return (
    <div className="app">
      {/* Top bar: app branding and SaaS header */}
      <header className="app-header">
        <div className="app-header__content">
          <div className="app-header__branding">
            <span className="app-header__badge">Pilot</span>
            <h1 className="app-header__title">LedgerPilot</h1>
          </div>
          <span className="app-header__tagline">
            Handwritten Marathi Ledger Digitization Platform
          </span>
        </div>
      </header>

      {/* Step header: Upload -> Review -> Export */}
      <StepHeader currentStep={currentStep} />

      {/* Main content */}
      <main className="app-main">
        <div
          className={`app-main__content ${
            currentStep === 'review' ? 'app-main__content--wide' : ''
          }`}
        >
          {currentStep === 'upload' || !session ? (
            <UploadView onExtractionSuccess={handleExtractionSuccess} />
          ) : (
            <ExtractionResultView
              extraction={session.result}
              selectedFile={session.file}
              previewUrl={session.previewUrl}
              events={session.events}
              onReset={handleReset}
              onUpdateExtraction={(updated) =>
                setSession((prev) => (prev ? { ...prev, result: updated } : null))
              }
            />
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
