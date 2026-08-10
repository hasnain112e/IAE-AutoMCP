// Edited by Dr. Wasim
import React from 'react';
import './StatusHeader.css';
import { ConnectionStatus as ConnectionStatusType, getStatusIcon } from './ConnectionStatus';

interface StatusHeaderProps {
  orchestratorStatus: ConnectionStatusType;
  validatorStatus: ConnectionStatusType;
  generatorStatus: ConnectionStatusType;
  backendStatus: ConnectionStatusType;
  // Auto Run props
  isAutoRunning?: boolean;
  autoRunStatus?: string;
  totalIterations?: number;
  maxIterations?: number;
  onAutoRun?: () => void;
  onStopAutoRun?: () => void;
  onResetAutoRun?: () => void;
  autoRunDisabled?: boolean;
}

const StatusHeader: React.FC<StatusHeaderProps> = ({
  orchestratorStatus,
  validatorStatus,
  generatorStatus,
  backendStatus,
  isAutoRunning = false,
  autoRunStatus = '',
  totalIterations = 0,
  maxIterations = 10,
  onAutoRun,
  onStopAutoRun,
  onResetAutoRun,
  autoRunDisabled = false
}) => {
  return (
    <header className="status-header">
      <div className="status-header-content">
        <div className="header-left">
          <h1 className="app-title">MCP Agentic System</h1>
          <span className="app-subtitle">Integrated Pipeline</span>
        </div>

        <div className="header-center">
          <div className="service-statuses">
            <ServiceStatus
              name="Orch"
              status={orchestratorStatus}
              port="8100"
            />
            <ServiceStatus
              name="Gen"
              status={generatorStatus}
              port="8101"
            />
            <ServiceStatus
              name="Val"
              status={validatorStatus}
              port="8002"
            />
            <ServiceStatus
              name="Back"
              status={backendStatus}
              port="8000"
            />
          </div>
        </div>

        <div className="header-right">
          {/* Auto Run Status Display */}
          {autoRunStatus && (
            <span className="auto-run-status" title={autoRunStatus}>
              {autoRunStatus}
            </span>
          )}
          
          {/* Iteration Counter */}
          <span className="iteration-counter">
            {totalIterations}/{maxIterations}
          </span>
          
          {/* Auto Run Button */}
          {isAutoRunning ? (
            <button 
              className="header-button auto-run-button running" 
              onClick={onStopAutoRun}
              title="Stop Auto Run"
            >
              <span className="icon">⏹</span>
              Stop
            </button>
          ) : (
            <button 
              className="header-button auto-run-button" 
              onClick={totalIterations >= maxIterations ? onResetAutoRun : onAutoRun}
              disabled={autoRunDisabled}
              title={totalIterations >= maxIterations 
                ? "Max iterations reached - click to reset" 
                : "Auto Run: Forge → Generate → Validate (5 iterations per batch)"}
            >
              <span className="icon">{totalIterations >= maxIterations ? "🔄" : "▶"}</span>
              {totalIterations >= maxIterations ? "Reset" : "Auto Run"}
            </button>
          )}
          
          <button className="header-button" onClick={() => window.location.reload()}>
            <span className="icon">🔄</span>
            Refresh
          </button>
          <a
            href="http://127.0.0.1:8100/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="header-button"
          >
            <span className="icon">📖</span>
            API Docs
          </a>
        </div>
      </div>
    </header>
  );
};

const ServiceStatus: React.FC<{
  name: string;
  status: ConnectionStatusType;
  port: string;
}> = ({ name, status, port }) => {
  const getStatusColor = (status: ConnectionStatusType) => {
    switch (status) {
      case 'connected':
        return '#22c55e'; // Green
      case 'connecting':
        return '#f59e0b'; // Amber
      case 'offline':
        return '#ef4444'; // Red
      default:
        return '#94a3b8'; // Gray
    }
  };

  return (
    <div className="service-status">
      <span 
        className="status-indicator" 
        style={{ backgroundColor: getStatusColor(status) }}
      />
      <span className="service-name">{name}</span>
      <span className="service-port">:{port}</span>
    </div>
  );
};

export default StatusHeader;
