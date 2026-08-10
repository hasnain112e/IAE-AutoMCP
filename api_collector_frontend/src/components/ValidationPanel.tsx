
import React, { useState, useEffect } from 'react';
import './ValidationPanel.css';

interface ValidationPanelProps {
  validationResult: any;
  regenerationCount: number;
  pipelineStep: "idle" | "generating" | "validating" | "feedback" | "done";
}

const ValidationPanel: React.FC<ValidationPanelProps> = ({ validationResult, regenerationCount, pipelineStep }) => {
  const [validationCountdown, setValidationCountdown] = useState(10);
  const [regenerationCountdown, setRegenerationCountdown] = useState(10);

  useEffect(() => {
    if (pipelineStep === 'validating') {
      const timer = setInterval(() => {
        setValidationCountdown(prev => (prev > 0 ? prev - 1 : 0));
      }, 1000);
      return () => clearInterval(timer);
    } else {
      setValidationCountdown(10);
    }
  }, [pipelineStep]);

  useEffect(() => {
    if (pipelineStep === 'feedback' && validationResult && !validationResult.approved && regenerationCount < 3) {
      const timer = setInterval(() => {
        setRegenerationCountdown(prev => (prev > 0 ? prev - 1 : 0));
      }, 1000);
      return () => clearInterval(timer);
    } else {
      setRegenerationCountdown(10);
    }
  }, [pipelineStep, validationResult, regenerationCount]);


  return (
    <div className="validation-panel">
      <div className="panel-header">
        <h2>Validation & Feedback</h2>
      </div>
      {pipelineStep === 'validating' && (
        <div className="countdown">Auto-validating in {validationCountdown}s...</div>
      )}
      {pipelineStep === 'feedback' && validationResult && !validationResult.approved && regenerationCount < 3 && (
        <div className="countdown">Auto-regenerating in {regenerationCountdown}s...</div>
      )}
      {validationResult && (
        <>
          <div className="validation-status">
            <p>Status: <span className={validationResult.approved ? "status-success" : "status-fail"}>{validationResult.approved ? "PASS" : "FAIL"}</span></p>
            <p>Iteration: {regenerationCount + 1}</p>
          </div>
          <div className="feedback-messages">
            {validationResult.errors && validationResult.errors.map((error: string, index: number) => (
              <div key={index} className="feedback-message error">{error}</div>
            ))}
            {validationResult.warnings && validationResult.warnings.map((warning: string, index: number) => (
              <div key={index} className="feedback-message warning">{warning}</div>
            ))}
            {validationResult.approved && <div className="feedback-message success">Validation successful!</div>}
          </div>
        </>
      )}
    </div>
  );
};

export default ValidationPanel;
