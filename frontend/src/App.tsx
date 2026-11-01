import { StepHeader } from './components';
import { UploadView } from './components';
import './App.css';

function App() {
  return (
    <div className="app">
      {/* Top bar: app name only, with a bottom border */}
      <header className="app-header">
        <h1 className="app-header__title">LedgerPilot</h1>
      </header>

      {/* Step header: Upload -> Review -> Export */}
      <StepHeader currentStep="upload" />

      {/* Main content: Upload screen */}
      <main className="app-main">
        <div className="app-main__content">
          <UploadView />
        </div>
      </main>
    </div>
  );
}

export default App;
