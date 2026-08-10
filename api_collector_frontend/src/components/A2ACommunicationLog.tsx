// Edited by Dr. Wasim
import React, { useMemo } from 'react';
import './A2ACommunicationLog.css';

export interface TelemetryEvent {
  event_id: string;
  correlation_id: string;
  context_id?: string;
  from_agent: string;
  to_agent: string;
  request_payload: Record<string, any>;
  response_payload: Record<string, any> | null;
  send_ts: number;
  recv_ts: number;
  latency_ms: number;
  status?: string;
}

interface A2ACommunicationLogProps {
  events: TelemetryEvent[];
}

const A2ACommunicationLog: React.FC<A2ACommunicationLogProps> = ({ events }) => {
  const ordered = useMemo(
    () => [...events].sort((a, b) => (b.send_ts || 0) - (a.send_ts || 0)),
    [events]
  );

  const formatTs = (ts?: number) => {
    if (!ts) return '--';
    const date = new Date(ts);
    return date.toLocaleTimeString();
  };

  const formatJson = (payload: any) => {
    try {
      return JSON.stringify(payload ?? {}, null, 2);
    } catch {
      return '<<unserializable payload>>';
    }
  };

  return (
    <div className="a2a-communication-log">
      <div className="a2a-header">
        <h3>A2A Communications</h3>
        <span className="a2a-count">{ordered.length} events</span>
        <span className="a2a-badge latest">Latest on Top ↑</span>
      </div>

      <div className="a2a-messages">
        {ordered.length === 0 ? (
          <div className="a2a-empty">No backend telemetry yet. A2A exchanges will appear here when agents communicate.</div>
        ) : (
          ordered.map((ev) => (
            <div key={ev.event_id} className="a2a-entry">
              <div className="entry-top">
                <div className="agent-line">
                  <span className="agent-label">{ev.from_agent}</span>
                  <span className="agent-arrow">-&gt;</span>
                  <span className="agent-label">{ev.to_agent}</span>
                </div>
                <div className="status-pill">{ev.status || 'unknown'}</div>
              </div>

              <div className="entry-meta">
                <span className="meta-chip">latency: {ev.latency_ms ?? 0}ms</span>
                <span className="meta-chip subtle">sent: {formatTs(ev.send_ts)}</span>
                <span className="meta-chip subtle">recv: {formatTs(ev.recv_ts)}</span>
              </div>

              <div className="payload-block">
                <details>
                  <summary>▼ Request payload</summary>
                  <pre className="payload-pre">{formatJson(ev.request_payload)}</pre>
                </details>
                <details>
                  <summary>▼ Response payload</summary>
                  <pre className="payload-pre">{formatJson(ev.response_payload)}</pre>
                </details>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default A2ACommunicationLog;


