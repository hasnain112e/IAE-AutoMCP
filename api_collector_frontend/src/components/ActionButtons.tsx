
import React from 'react';
import './ActionButtons.css';

interface ActionButtonsProps {
  onForgeTools: () => void;
  onGenerateCode: () => void;
  pipelineStep: "idle" | "generating" | "validating" | "feedback" | "done";
}

const ActionButtons: React.FC<ActionButtonsProps> = ({ onForgeTools, onGenerateCode, pipelineStep }) => {
  return (
    <div className="action-buttons">
      <button className="forge-button" onClick={onForgeTools} disabled={pipelineStep !== 'idle'}>Forge / Generate MCP Tools</button>
      <button className="generate-code-button" onClick={onGenerateCode} disabled={pipelineStep !== 'idle'}>Generate MCP Server Code</button>
      <div className="export-buttons">
        <button disabled={pipelineStep !== 'done'}>Export JSON</button>
        <button disabled={pipelineStep !== 'done'}>Export CSV</button>
        <button disabled={pipelineStep !== 'done'}>Export MCP Code</button>
      </div>
    </div>
  );
};

export default ActionButtons;
