import React from 'react';
import './TimerDisplay.css';

interface TimerDisplayProps {
  action: 'validate' | 'regenerate';
  remaining: number;
  total: number;
  onCancel: () => void;
}

const TimerDisplay: React.FC<TimerDisplayProps> = ({
  action,
  remaining,
  total,
  onCancel
}) => {
  const progress = ((total - remaining) / total) * 100;
  const actionLabel = action === 'validate' ? 'Validation' : 'Regeneration';

  return (
    <div className="timer-display card">
      <div className="timer-header">
        <div className="timer-info">
          <span className="timer-icon">⏱️</span>
          <div>
            <div className="timer-label">Auto-{actionLabel}</div>
            <div className="timer-subtitle">
              {actionLabel} will start in {remaining} seconds
            </div>
          </div>
        </div>
        <button onClick={onCancel} className="button-secondary timer-cancel">
          Cancel
        </button>
      </div>

      <div className="timer-progress-container">
        <div
          className="timer-progress-bar"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="timer-countdown">
        <span className="countdown-number">{remaining}</span>
        <span className="countdown-label">seconds</span>
      </div>
    </div>
  );
};

export default TimerDisplay;
