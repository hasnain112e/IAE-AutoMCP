import React, { useState } from 'react';
import CodePanel from './CodePanel';
import ValidationFeedback from './ValidationFeedback';
import './IterationTabs.css';

interface CodeIteration {
  iteration: number;
  code: string;
  timestamp: Date;
  validationResult?: any;
}

interface IterationTabsProps {
  iterations: CodeIteration[];
  selectedIteration: number | null;
  onSelectIteration: (iteration: number) => void;
}

const IterationTabs: React.FC<IterationTabsProps> = ({ 
  iterations, 
  selectedIteration, 
  onSelectIteration 
}) => {
  const selected = iterations.find(ci => ci.iteration === selectedIteration) || iterations[iterations.length - 1];
  const previousCode = selected && selectedIteration && selectedIteration > 1
    ? iterations.find(ci => ci.iteration === selectedIteration - 1)?.code || null
    : null;

  return (
    <div className="iteration-tabs-container">
      {/* Tabs Header */}
      <div className="tabs-header">
        <h3>📚 Code Iterations ({iterations.length})</h3>
        <p className="tabs-hint">View all generated code versions with their validation results</p>
      </div>

      {/* Tabs Navigation */}
      <div className="tabs-nav">
        {iterations.map((iter) => (
          <button
            key={iter.iteration}
            className={`tab-button ${selectedIteration === iter.iteration ? 'active' : ''}`}
            onClick={() => onSelectIteration(iter.iteration)}
          >
            <span className="tab-number">Iteration {iter.iteration}</span>
            {iter.validationResult && (
              <span className={`tab-badge ${iter.validationResult.approved ? 'approved' : 'rejected'}`}>
                {iter.validationResult.approved ? '✓' : '✗'} {iter.validationResult.quality_score}/100
              </span>
            )}
            <span className="tab-time">{iter.timestamp.toLocaleTimeString()}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {selected && (
        <div className="tab-content">
          {/* Code Panel */}
          <div className="tab-pane code-pane">
            <CodePanel
              code={selected.code}
              previousCode={previousCode}
              iteration={selected.iteration}
              issues={selected.validationResult ? [
                ...(selected.validationResult.errors || []).map((e: any) => ({
                  line: e.line || 0,
                  severity: 'error' as const,
                  description: e.description || e.message || ''
                })),
                ...(selected.validationResult.warnings || []).map((w: any) => ({
                  line: w.line || 0,
                  severity: 'warning' as const,
                  description: w.description || w.message || ''
                }))
              ] : []}
            />
          </div>

          {/* Validation Feedback */}
          {selected.validationResult && (
            <div className="tab-pane validation-pane">
              <ValidationFeedback result={selected.validationResult} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default IterationTabs;

