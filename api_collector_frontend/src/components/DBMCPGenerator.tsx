import React, { useState, useRef, useEffect } from 'react';
import './DBMCPGenerator.css';

const API = 'http://127.0.0.1:8000';

type Step = 'idle' | 'connecting' | 'generating' | 'done' | 'error';

interface MCPResult {
  dbname: string;
  uri: string;
  collections: string[];
  tools_count: number;
  mongo_id: string | null;
  generated_code: string;
}

interface ChatMessage {
  role: 'user' | 'agent';
  text: string;
  data?: any[];
  collection?: string;
  filter?: any;
  count?: number;
  loading?: boolean;
}

export default function DBMCPGenerator() {
  const [uri, setUri] = useState('mongodb://127.0.0.1:27017');
  const [dbname, setDbname] = useState('demo');
  const [step, setStep] = useState<Step>('idle');
  const [mcpResult, setMcpResult] = useState<MCPResult | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [collections, setCollections] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [asking, setAsking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleConnect = async () => {
    if (!uri.trim() || !dbname.trim()) return;
    setStep('connecting');
    setError('');
    setMcpResult(null);
    setSessionId(null);
    setMessages([]);
    setCollections([]);

    try {
      // Step 1: Connect + create agent session
      const connRes = await fetch(`${API}/db-agent/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uri: uri.trim(), dbname: dbname.trim() }),
      });
      const connData = await connRes.json();
      if (!connRes.ok) throw new Error(connData.detail || 'Connection failed');
      setSessionId(connData.session_id);
      setCollections(connData.collections);

      // Step 2: Generate MCP server code
      setStep('generating');
      const mcpRes = await fetch(`${API}/generate-db-mcp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uri: uri.trim(), dbname: dbname.trim() }),
      });
      const mcpData = await mcpRes.json();
      if (!mcpRes.ok) throw new Error(mcpData.detail || 'MCP generation failed');

      setMcpResult(mcpData);
      setStep('done');

      // Welcome message
      setMessages([{
        role: 'agent',
        text: `Connected to **${dbname}** database. Found ${connData.collections.length} collections: ${connData.collections.join(', ')}.\n\nMCP server generated with ${mcpData.tools_count} tools. Ask me anything about your data!`,
      }]);
    } catch (e: any) {
      setStep('error');
      setError(e.message || 'Unknown error');
    }
  };

  const handleAsk = async () => {
    if (!input.trim() || !sessionId || asking) return;
    const question = input.trim();
    setInput('');
    setAsking(true);

    setMessages(prev => [
      ...prev,
      { role: 'user', text: question },
      { role: 'agent', text: '', loading: true },
    ]);

    try {
      const r = await fetch(`${API}/db-agent/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, question }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Query failed');

      setMessages(prev => [
        ...prev.slice(0, -1),
        {
          role: 'agent',
          text: data.answer,
          data: data.data,
          collection: data.collection,
          filter: data.filter,
          count: data.count,
        },
      ]);
    } catch (e: any) {
      setMessages(prev => [
        ...prev.slice(0, -1),
        { role: 'agent', text: `Error: ${e.message}` },
      ]);
    } finally {
      setAsking(false);
    }
  };

  const suggestedQueries = collections.length > 0 ? [
    `Show all ${collections[0]}`,
    `How many ${collections[0]} are there?`,
    collections[1] ? `List all ${collections[1]}` : `Show active ${collections[0]}`,
    `Show 5 records from ${collections[collections.length - 1]}`,
  ] : [];

  return (
    <div className="dbmcp-panel card">
      <h2 className="section-title">Database Agent — MCP Generator</h2>
      <p className="dbmcp-subtitle">
        Connect your MongoDB database → AutoMCP generates tools → Ask natural language questions about your data.
      </p>

      {/* Connection Form */}
      <div className="dbmcp-form">
        <div className="dbmcp-field">
          <label>MongoDB URI</label>
          <input
            className="dbmcp-input"
            value={uri}
            onChange={e => setUri(e.target.value)}
            placeholder="mongodb://127.0.0.1:27017"
            disabled={step === 'connecting' || step === 'generating'}
          />
        </div>
        <div className="dbmcp-field">
          <label>Database Name</label>
          <input
            className="dbmcp-input dbmcp-input-sm"
            value={dbname}
            onChange={e => setDbname(e.target.value)}
            placeholder="demo"
            disabled={step === 'connecting' || step === 'generating'}
          />
        </div>
        <button
          className="dbmcp-btn"
          onClick={handleConnect}
          disabled={!uri || !dbname || step === 'connecting' || step === 'generating'}
        >
          {step === 'connecting' || step === 'generating' ? (
            <><span className="dbmcp-spinner" /> {step === 'connecting' ? 'Connecting...' : 'Generating MCP...'}</>
          ) : step === 'done' ? 'Reconnect' : 'Connect & Generate MCP'}
        </button>
      </div>

      {/* Error */}
      {step === 'error' && (
        <div className="dbmcp-error"><strong>Error:</strong> {error}</div>
      )}

      {/* MCP Generated Info */}
      {mcpResult && step === 'done' && (
        <div className="dbmcp-info-bar">
          <div className="dbmcp-info-stats">
            <span className="dbmcp-success-badge">MCP Ready</span>
            <span className="dbmcp-stat-inline">{collections.length} Collections</span>
            <span className="dbmcp-stat-inline">{mcpResult.tools_count} Tools</span>
            <span className="dbmcp-stat-inline">{mcpResult.generated_code.split('\n').length} Lines</span>
          </div>
          <div className="dbmcp-col-chips">
            {collections.map(c => <span key={c} className="dbmcp-col-chip">{c}</span>)}
          </div>
          <button className="dbmcp-view-btn" onClick={() => setShowCode(v => !v)}>
            {showCode ? 'Hide MCP Code' : 'View MCP Code'}
          </button>
          {showCode && (
            <div className="dbmcp-code-viewer">
              <div className="dbmcp-code-header">
                <span>{mcpResult.dbname}_mcp_server.py</span>
                <button className="dbmcp-copy-btn" onClick={() => navigator.clipboard.writeText(mcpResult.generated_code)}>Copy</button>
                <button className="dbmcp-copy-btn" onClick={() => setShowCode(false)}>✕</button>
              </div>
              <pre className="dbmcp-code-pre"><code>{mcpResult.generated_code}</code></pre>
            </div>
          )}
        </div>
      )}

      {/* Chat Interface */}
      {step === 'done' && sessionId && (
        <div className="dbmcp-chat">
          <div className="dbmcp-chat-header">
            <span>Agent Chat — {dbname} database</span>
            <span className="dbmcp-online-dot" />
          </div>

          {/* Suggested queries */}
          {messages.length <= 1 && (
            <div className="dbmcp-suggestions">
              {suggestedQueries.map((q, i) => (
                <button key={i} className="dbmcp-suggestion" onClick={() => { setInput(q); }}>
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Messages */}
          <div className="dbmcp-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`dbmcp-msg dbmcp-msg-${msg.role}`}>
                <div className="dbmcp-msg-bubble">
                  {msg.loading ? (
                    <span className="dbmcp-typing"><span /><span /><span /></span>
                  ) : (
                    <>
                      <p className="dbmcp-msg-text">
                        {msg.text.split('**').map((part, j) =>
                          j % 2 === 1 ? <strong key={j}>{part}</strong> : part
                        )}
                      </p>
                      {msg.data && msg.data.length > 0 && (
                        <div className="dbmcp-result-table">
                          <table>
                            <thead>
                              <tr>
                                {Object.keys(msg.data[0]).filter(k => k !== '_id').slice(0, 6).map(k => (
                                  <th key={k}>{k}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {msg.data.slice(0, 10).map((row, ri) => (
                                <tr key={ri}>
                                  {Object.entries(row).filter(([k]) => k !== '_id').slice(0, 6).map(([k, v]) => (
                                    <td key={k}>{String(v ?? '')}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {msg.data.length > 10 && (
                            <p className="dbmcp-more">…and {msg.data.length - 10} more rows</p>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className="dbmcp-chat-input-row">
            <input
              className="dbmcp-chat-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAsk()}
              placeholder={`Ask about ${dbname}... e.g. "Show active employees"`}
              disabled={asking}
            />
            <button className="dbmcp-send-btn" onClick={handleAsk} disabled={asking || !input.trim()}>
              {asking ? '...' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
