import './StepHeader.css';

export type Step = 'upload' | 'review' | 'export';

interface StepHeaderProps {
  currentStep: Step;
}

const STEPS: { id: Step; label: string; number: number }[] = [
  { id: 'upload', label: 'Upload', number: 1 },
  { id: 'review', label: 'Review', number: 2 },
  { id: 'export', label: 'Export', number: 3 },
];

export function StepHeader({ currentStep }: StepHeaderProps) {
  return (
    <nav className="step-header" aria-label="Workflow progress">
      <ol className="step-header__list">
        {STEPS.map((step, index) => {
          const isActive = step.id === currentStep;
          const isPassed =
            (currentStep === 'review' && step.id === 'upload') ||
            (currentStep === 'export' && step.id !== 'export');

          return (
            <li
              key={step.id}
              className={`step-header__item ${
                isActive ? 'step-header__item--active' : ''
              } ${isPassed ? 'step-header__item--completed' : ''}`}
              aria-current={isActive ? 'step' : undefined}
            >
              <div className="step-header__indicator">
                <span className="step-header__number">{step.number}</span>
                <span className="step-header__label">{step.label}</span>
              </div>
              {index < STEPS.length - 1 && (
                <div
                  className="step-header__connector"
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
