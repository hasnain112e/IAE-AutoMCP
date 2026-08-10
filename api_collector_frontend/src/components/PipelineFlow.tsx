import React from 'react';
import './PipelineFlow.css';

export interface PipelineStep {
  id: string;
  label: string;
  description: string;
  status: 'pending' | 'active' | 'completed' | 'error';
  icon: string;
}

interface PipelineFlowProps {
  currentState: string;
  iterationCount?: number;
  maxIterations?: number;
}

export const PipelineFlow: React.FC<PipelineFlowProps> = ({
  currentState,
  iterationCount = 0,
  maxIterations = 3
}) => {

  // Define all pipeline steps
  const steps: PipelineStep[] = [
    {
      id: 'initial',
      label: '1. System Ready',
      description: 'Waiting for input',
      status: getStepStatus('initial'),
      icon: '🚀'
    },
    {
      id: 'input_received',
      label: '2. Input Received',
      description: 'Processing your API source',
      status: getStepStatus('input_received'),
      icon: '📥'
    },
    {
      id: 'collecting_tools',
      label: '3. Extracting Tools',
      description: 'Analyzing API endpoints',
      status: getStepStatus('collecting_tools'),
      icon: '🔍'
    },
    {
      id: 'generating_code',
      label: '4. Generating Code',
      description: 'AI is creating MCP server',
      status: getStepStatus('generating_code'),
      icon: '🤖'
    },
    {
      id: 'awaiting_validation',
      label: '5. Preparing Validation',
      description: 'Getting ready to validate',
      status: getStepStatus('awaiting_validation'),
      icon: '⏱️'
    },
    {
      id: 'validating_code',
      label: '6. Validating Code',
      description: 'AI is checking quality',
      status: getStepStatus('validating_code'),
      icon: '✅'
    },
    {
      id: 'done',
      label: '7. Complete!',
      description: 'Your MCP server is ready',
      status: getStepStatus('done'),
      icon: '🎉'
    }
  ];

  function getStepStatus(stepId: string): 'pending' | 'active' | 'completed' | 'error' {
    const stateOrder = [
      'initial',
      'input_received',
      'collecting_tools',
      'tools_ready',
      'generating_code',
      'awaiting_validation',
      'validating_code',
      'validation_result',
      'awaiting_regen',
      'regenerating_code',
      'done',
      'failed_final'
    ];

    const currentIndex = stateOrder.indexOf(currentState);
    const stepIndex = stateOrder.indexOf(stepId);

    // Handle failed state
    if (currentState === 'failed_final' && stepId === 'done') {
      return 'error';
    }

    // Handle done state - mark it as completed
    if (currentState === 'done' && stepId === 'done') {
      return 'completed';
    }

    // Special completion rules for transition states
    // When we're at 'tools_ready', collecting is DONE
    if (currentState === 'tools_ready' && stepId === 'collecting_tools') {
      return 'completed';
    }

    // When we're awaiting or doing regeneration, show it as generating
    if ((currentState === 'awaiting_regen' || currentState === 'regenerating_code') && stepId === 'generating_code') {
      return 'active';
    }

    // When we're at validation_result, mark validation as completed
    if (currentState === 'validation_result' && stepId === 'validating_code') {
      return 'completed';
    }

    // When we're done, mark all previous steps as completed
    if (currentState === 'done' && stepIndex < stateOrder.indexOf('done')) {
      return 'completed';
    }

    // Direct match with current state
    if (currentState === stepId) {
      return 'active';
    }

    // If we've moved past this step in the order, mark it completed
    if (stepIndex !== -1 && currentIndex !== -1 && stepIndex < currentIndex) {
      return 'completed';
    }

    return 'pending';
  }

  return (
    <div className="pipeline-flow">
      <div className="pipeline-header">
        <h2>📋 Pipeline Progress</h2>
        {iterationCount > 0 && (
          <div className="iteration-badge">
            Iteration {iterationCount}
          </div>
        )}
      </div>

      <div className="steps-container">
        {steps.map((step, index) => (
          <div key={step.id} className="step-wrapper">
            <div className={`step-card ${step.status}`}>
              <div className="step-icon">{step.icon}</div>
              <div className="step-content">
                <div className="step-label">{step.label}</div>
                <div className="step-description">{step.description}</div>
              </div>
              <div className="step-status-indicator">
                {step.status === 'completed' && <span className="status-check">✓</span>}
                {step.status === 'active' && <span className="status-spinner"></span>}
                {step.status === 'error' && <span className="status-error">✗</span>}
                {step.status === 'pending' && <span className="status-pending">○</span>}
              </div>
            </div>

            {index < steps.length - 1 && (
              <div className={`step-connector ${step.status === 'completed' ? 'completed' : ''}`}></div>
            )}
          </div>
        ))}
      </div>

      {/* Show special message for regeneration */}
      {(currentState === 'awaiting_regen' || currentState === 'regenerating_code') && (
        <div className="regeneration-notice">
          <span className="notice-icon">🔄</span>
          <div className="notice-content">
            <strong>Regenerating Code</strong>
            <p>Incorporating validation feedback to improve the code...</p>
          </div>
        </div>
      )}

      {/* Show error message if failed */}
      {currentState === 'failed_final' && (
        <div className="error-notice">
          <span className="notice-icon">⚠️</span>
          <div className="notice-content">
            <strong>Generation Error</strong>
            <p>Please review the feedback and try again.</p>
          </div>
        </div>
      )}
    </div>
  );
};
