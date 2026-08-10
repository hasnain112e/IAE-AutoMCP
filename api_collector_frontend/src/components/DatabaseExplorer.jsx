import React, { useState, useRef, useEffect } from 'react';
import './DatabaseExplorer.css';

const BASE = 'http://localhost:8000';

const api = {
  post: (path, body) => fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  }).then(r => r.json()),
  postForm: (path, formData) => fetch(BASE + path, { method: 'POST', body: formData }).then(r => r.json()),
  get: (path) => fetch(BASE + path).then(r => r.json()),
  delete: (path) => fetch(BASE + path, { method: 'DELETE' }).then(r => r.json()),
};

// ── Tiny helpers ──────────────────────────────────────────────────────────────

function Spinner() { return <span className="de-spinner" />; }

function SafeBadge() {
  return <span className="de-safe-badge">READ-ONLY</span>;
}

function DataTable({ rows }) {
  if (!rows || rows.length === 0) return <p className="de-no-data">No data returned.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="de-table-wrap">
      <table className="de-table">
        <thead><tr>{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, 200).map((r, i) => (
            <tr key={i}>{cols.map(c => <td key={c}>{String(r[c] ?? '')}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {rows.length > 200 && <p className="de-truncate">Showing 200 of {rows.length} rows</p>}
    </div>
  );
}

// ── Schema Sidebar ─────────────────────────────────────────────────────────────

function SchemaSidebar({ schema, counts, onTableClick }) {
  const [open, setOpen] = useState({});
  if (!schema) return <div className="de-sidebar-empty">No schema yet</div>;

  return (
    <div className="de-sidebar">
      <div className="de-sidebar-title">Schema</div>
      {Object.entries(schema).map(([table, cols]) => (
        <div key={table} className="de-schema-table">
          <div className="de-schema-table-header" onClick={() => setOpen(o => ({ ...o, [table]: !o[table] }))}>
            <span className="de-schema-arrow">{open[table] ? '▾' : '▸'}</span>
            <span className="de-schema-table-name" onClick={(e) => { e.stopPropagation(); onTableClick(table); }}>
              {table}
            </span>
            <span className="de-schema-count">{counts?.[table] ?? '?'}</span>
          </div>
          {open[table] && (
            <div className="de-schema-cols">
              {cols.map(c => (
                <div key={c.name} className="de-schema-col">
                  <span className="de-col-name">{c.name}</span>
                  <span className="de-col-type">{c.type}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Connection Panel ───────────────────────────────────────────────────────────

function ConnectPanel({ onConnected }) {
  const [tab, setTab] = useState('postgresql');
  const [uri, setUri] = useState('');
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState('5432');
  const [dbname, setDbname] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mongoUri, setMongoUri] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const connectPG = async () => {
    setLoading(true); setError('');
    try {
      const body = uri
        ? { db_type: 'postgresql', uri }
        : { db_type: 'postgresql', host, port: parseInt(port), dbname, username, password };
      const data = await api.post('/db-explorer/connect', body);
      if (data.success) onConnected(data);
      else setError(data.error || 'Connection failed');
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  const connectMongo = async () => {
    setLoading(true); setError('');
    try {
      const data = await api.post('/db-explorer/connect', { db_type: 'mongodb', uri: mongoUri });
      if (data.success) onConnected(data);
      else setError(data.error || 'Connection failed');
    } catch (e) { setError(e.message); }
    setLoading(false);
  };

  const uploadFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const data = await api.postForm('/db-explorer/upload', fd);
      if (data.success) onConnected(data);
      else setError(data.error || 'Upload failed');
    } catch (err) { setError(err.message); }
    setLoading(false);
  };

  return (
    <div className="de-connect-panel">
      <div className="de-connect-tabs">
        {[['postgresql', '🐘 PostgreSQL'], ['mongodb', '🍃 MongoDB'], ['file', '📁 Upload File']].map(([t, label]) => (
          <button key={t} className={`de-ctab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{label}</button>
        ))}
      </div>

      {tab === 'postgresql' && (
        <div className="de-connect-form">
          <label>Connection URI (optional)</label>
          <input placeholder="postgresql://user:pass@host:5432/dbname" value={uri} onChange={e => setUri(e.target.value)} />
          {!uri && <>
            <div className="de-form-row">
              <div><label>Host</label><input value={host} onChange={e => setHost(e.target.value)} /></div>
              <div><label>Port</label><input value={port} onChange={e => setPort(e.target.value)} type="number" /></div>
            </div>
            <label>Database</label><input value={dbname} onChange={e => setDbname(e.target.value)} />
            <div className="de-form-row">
              <div><label>Username</label><input value={username} onChange={e => setUsername(e.target.value)} /></div>
              <div><label>Password</label><input type="password" value={password} onChange={e => setPassword(e.target.value)} /></div>
            </div>
          </>}
          <button className="de-connect-btn pg" onClick={connectPG} disabled={loading}>
            {loading ? <Spinner /> : 'Connect'}
          </button>
        </div>
      )}

      {tab === 'mongodb' && (
        <div className="de-connect-form">
          <label>MongoDB URI</label>
          <input placeholder="mongodb://user:pass@host:27017/dbname" value={mongoUri} onChange={e => setMongoUri(e.target.value)} />
          <button className="de-connect-btn mg" onClick={connectMongo} disabled={loading}>
            {loading ? <Spinner /> : 'Connect'}
          </button>
        </div>
      )}

      {tab === 'file' && (
        <div className="de-connect-form de-upload-area">
          <div className="de-drop-zone" onClick={() => document.getElementById('de-file-input').click()}>
            {loading ? <><Spinner /> Parsing file...</> : <>
              <span className="de-drop-icon">📁</span>
              <span>Click to upload or drag & drop</span>
              <span className="de-drop-hint">.sql · .sqlite · .csv · .json</span>
            </>}
          </div>
          <input id="de-file-input" type="file" accept=".sql,.sqlite,.db,.csv,.json,.bson" style={{ display: 'none' }} onChange={uploadFile} />
        </div>
      )}

      {error && <div className="de-connect-error">{error}</div>}
    </div>
  );
}

// ── Chat message ──────────────────────────────────────────────────────────────

function ChatMessage({ msg, sessionId, question }) {
  const [showSteps, setShowSteps] = useState(false);
  const [exporting, setExporting] = useState(false);

  const exportCSV = async () => {
    setExporting(true);
    try {
      const resp = await fetch(`${BASE}/db-explorer/export/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: msg.question })
      });
      if (!resp.ok) { setExporting(false); return; }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'export.csv'; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { console.error(e); }
    setExporting(false);
  };

  if (msg.role === 'user') {
    return <div className="de-msg de-msg-user"><span>{msg.content}</span></div>;
  }

  const data = msg.data;
  if (!data) return null;

  return (
    <div className="de-msg de-msg-agent">
      {/* Safety status */}
      {data.safety_ok === false && (
        <div className="de-blocked-bar">BLOCKED — {data.safety_reason}</div>
      )}

      {/* Answer */}
      {data.query_explanation && (
        <div className="de-answer-text">{data.query_explanation}</div>
      )}

      {/* Generated query */}
      {data.generated_query && (
        <details className="de-query-details">
          <summary>Generated Query</summary>
          <pre className="de-query-code">{data.generated_query}</pre>
          {data.optimization_notes && data.optimization_notes !== 'No changes needed' && (
            <div className="de-opt-notes">Optimization: {data.optimization_notes}</div>
          )}
        </details>
      )}

      {/* Results */}
      {data.results && data.results.length > 0 && (
        <div className="de-results-section">
          <div className="de-results-header">
            <span>{data.row_count} row{data.row_count !== 1 ? 's' : ''}</span>
            <button className="de-export-btn" onClick={exportCSV} disabled={exporting}>
              {exporting ? <Spinner /> : 'Export CSV'}
            </button>
          </div>
          <DataTable rows={data.results} />
        </div>
      )}

      {/* Steps */}
      {data.steps && data.steps.length > 0 && (
        <div className="de-steps-section">
          <button className="de-steps-toggle" onClick={() => setShowSteps(s => !s)}>
            {showSteps ? 'Hide' : 'Show'} agent steps ({data.steps.length})
          </button>
          {showSteps && (
            <div className="de-steps">
              {data.steps.map((step, i) => (
                <div key={i} className="de-step">
                  <span className="de-step-node">{step.node}</span>
                  {step.tables && <span className="de-step-detail">tables: {step.tables.join(', ')}</span>}
                  {step.query && <code className="de-step-query">{step.query.slice(0, 80)}...</code>}
                  {step.count !== undefined && <span className="de-step-count">{step.count} rows</span>}
                  {step.error && <span className="de-step-error">{step.error}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Query History ─────────────────────────────────────────────────────────────

function HistoryPanel({ history, onRerun }) {
  if (!history.length) return null;
  return (
    <div className="de-history">
      <div className="de-history-title">Query History</div>
      <table className="de-history-table">
        <thead><tr><th>Question</th><th>Query</th><th>Rows</th><th>Time</th></tr></thead>
        <tbody>
          {[...history].reverse().map((h, i) => (
            <tr key={i} onClick={() => onRerun(h.question)} className="de-history-row">
              <td>{h.question.slice(0, 50)}</td>
              <td><code>{(h.query || '').slice(0, 40)}...</code></td>
              <td>{h.row_count}</td>
              <td>{h.timestamp?.slice(11, 19)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────

const SAMPLE_QUESTIONS = [
  'Show all records from the first table',
  'What are the top 10 rows by ID?',
  'Count records in each table',
  'Show distinct values in the first column',
];

export default function DatabaseExplorer() {
  const [session, setSession] = useState(null);
  const [schema, setSchema] = useState(null);
  const [counts, setCounts] = useState(null);
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [question, setQuestion] = useState('');
  const [querying, setQuerying] = useState(false);
  const [exploring, setExploring] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const onConnected = (data) => {
    setSession({ id: data.session_id, db_type: data.db_type });
    setSchema(data.schema || null);
    setCounts(data.row_counts || null);
    setMessages([{
      role: 'agent',
      data: { query_explanation: `Connected! Found ${data.table_count} table(s) with ${data.column_count} columns total. Ask me anything about your data.` }
    }]);
  };

  const reExplore = async () => {
    if (!session) return;
    setExploring(true);
    try {
      const data = await api.post(`/db-explorer/explore/${session.id}`);
      if (data.success) { setSchema(data.schema); setCounts(data.row_counts); }
    } catch (e) { console.error(e); }
    setExploring(false);
  };

  const sendQuestion = async (q) => {
    const text = (q || question).trim();
    if (!text || !session || querying) return;
    setQuestion('');
    setMessages(m => [...m, { role: 'user', content: text }]);
    setQuerying(true);
    try {
      const data = await api.post(`/db-explorer/query/${session.id}`, { question: text });
      setMessages(m => [...m, { role: 'agent', data, question: text }]);
      // refresh history
      const hist = await api.get(`/db-explorer/history/${session.id}`);
      if (hist.success) setHistory(hist.history);
    } catch (e) {
      setMessages(m => [...m, { role: 'agent', data: { query_explanation: `Error: ${e.message}` } }]);
    }
    setQuerying(false);
  };

  const disconnect = async () => {
    if (session) await api.delete(`/db-explorer/session/${session.id}`);
    setSession(null); setSchema(null); setCounts(null);
    setMessages([]); setHistory([]);
  };

  return (
    <div className="de-root">
      {/* Header */}
      <div className="de-header">
        <div className="de-header-left">
          <h2>Production DB Explorer</h2>
          <p>Connect any database · Natural language queries · Read-only · Self-improving AI</p>
        </div>
        <div className="de-header-right">
          <SafeBadge />
          {session && (
            <button className="de-disconnect-btn" onClick={disconnect}>Disconnect</button>
          )}
        </div>
      </div>

      {/* Connection bar (shown when not connected) */}
      {!session && <ConnectPanel onConnected={onConnected} />}

      {/* Main layout (shown when connected) */}
      {session && (
        <div className="de-main">
          {/* Sidebar */}
          <div className="de-sidebar-wrap">
            <div className="de-connected-info">
              <span className="de-conn-dot" />
              <span>{session.db_type}</span>
            </div>
            <SchemaSidebar
              schema={schema}
              counts={counts}
              onTableClick={t => setQuestion(`Show me all records from ${t}`)}
            />
            <button className="de-reexplore-btn" onClick={reExplore} disabled={exploring}>
              {exploring ? <Spinner /> : 'Re-explore Schema'}
            </button>
          </div>

          {/* Chat area */}
          <div className="de-chat-area">
            {/* Sample questions */}
            {messages.length <= 1 && (
              <div className="de-samples">
                {SAMPLE_QUESTIONS.map(q => (
                  <button key={q} className="de-sample-chip" onClick={() => sendQuestion(q)}>{q}</button>
                ))}
              </div>
            )}

            {/* Messages */}
            <div className="de-messages">
              {messages.map((msg, i) => (
                <ChatMessage key={i} msg={msg} sessionId={session.id} question={msg.question} />
              ))}
              {querying && (
                <div className="de-thinking"><Spinner /> Agent is thinking...</div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="de-input-row">
              <textarea
                className="de-input"
                rows={2}
                placeholder="Ask anything about your data... (Enter to send)"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); } }}
                disabled={querying}
              />
              <button className="de-send-btn" onClick={() => sendQuestion()} disabled={querying || !question.trim()}>
                {querying ? <Spinner /> : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* History */}
      {session && <HistoryPanel history={history} onRerun={sendQuestion} />}
    </div>
  );
}
