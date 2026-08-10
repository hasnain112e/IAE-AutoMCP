import React from 'react';
import './ActionButtons_new.css';

interface ActionButtonsProps {
  state: string;
  iteration: number;
  onStartPipeline: () => void;
  onValidate: () => void;
  onRegenerate: () => void;
  disabled: boolean;
}

const ActionButtons: React.FC<ActionButtonsProps> = ({
  state,
  iteration,
  onStartPipeline,
  onValidate,
  onRegenerate,
  disabled
}) => {
  const showStartButton = state === 'initial' || state === 'input_received';
  const showValidateButton = state === 'awaiting_validation';
  const showRegenerateButton = state === 'awaiting_regen';
  const isGenerating = state === 'generating_code' || state === 'regenerating_code';
  const isValidating = state === 'validating_code';
  const isDone = state === 'done';
  const isFailed = state === 'failed_final';

  return (
    <div className="action-buttons card">
      <div className="card-header">
        <h2 className="card-title">3. Actions</h2>
        {iteration > 0 && (
          <span className="badge badge-info">Iteration {iteration}/3</span>
        )}
      </div>

      <div className="buttons-grid">
        {showStartButton && (
          <button
            onClick={onStartPipeline}
            disabled={disabled}
            className="action-button button-primary"
          >
            <span className="button-icon">🚀</span>
            <span>Start Pipeline</span>
          </button>
        )}

        {isGenerating && (
          <button disabled className="action-button button-secondary">
            <span className="button-icon spinner">⚙️</span>
            <span>Generating Code...</span>
          </button>
        )}

        {showValidateButton && (
          <button
            onClick={onValidate}
            className="action-button button-success"
          >
            <span className="button-icon">✅</span>
            <span>Validate Code Now</span>
          </button>
        )}

        {isValidating && (
          <button disabled className="action-button button-secondary">
            <span className="button-icon spinner">🔍</span>
            <span>Validating...</span>
          </button>
        )}

        {showRegenerateButton && (
          <button
            onClick={onRegenerate}
            className="action-button button-primary"
          >
            <span className="button-icon">🔄</span>
            <span>Regenerate Code Now</span>
          </button>
        )}

        {isDone && (
          <div className="status-message success">
            <span className="status-icon">🎉</span>
            <div>
              <div className="status-title">Pipeline Complete!</div>
              <div className="status-subtitle">MCP server code generated and validated</div>
            </div>
          </div>
        )}

        {isFailed && (
          <div className="status-message error">
            <span className="status-icon">⚠️</span>
            <div>
              <div className="status-title">Maximum Iterations Reached</div>
              <div className="status-subtitle">Review validation feedback below</div>
            </div>
          </div>
        )}
      </div>

      <div className="action-info">
        <div className="info-item">
          <span className="info-label">⏸️ Mode:</span>
          <span className="info-value" style={{color: '#f59e0b', fontWeight: 600}}>MANUAL CONTROL</span>
        </div>
        <div className="info-item">
          <span className="info-label">Max iterations:</span>
          <span className="info-value">3 attempts</span>
        </div>
        <div className="info-item">
          <span className="info-label">👉</span>
          <span className="info-value" style={{fontSize: '12px'}}>You click buttons when ready!</span>
        </div>
      </div>
    </div>
  );
};

export default ActionButtons;
