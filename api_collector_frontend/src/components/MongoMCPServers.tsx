import React, { useState, useEffect, useCallback } from 'react';
import './MongoMCPServers.css';

interface MCPServer {
  _id: string;
  source_name: string;
  source_type: string;
  tools_count: number;
  code_lines: number;
  created_at: string;
  generated_code?: string;
}

const API = 'http://127.0.0.1:8000';

export default function MongoMCPServers() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [askLoading, setAskLoading] = useState(false);
  const [selectedCode, setSelectedCode] = useState<{ name: string; code: string } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const fetchServers = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/mcp-servers`);
      const data = await r.json();
      setServers(data.servers || []);
    } catch {
      setServers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchServers(); }, [fetchServers]);

  const handleViewCode = async (server: MCPServer) => {
    if (selectedCode?.name === server.source_name) {
      setSelectedCode(null);
      return;
    }
    try {
      const r = await fetch(`${API}/mcp-servers/${server._id}`);
      const data = await r.json();
      setSelectedCode({ name: server.source_name, code: data.server?.generated_code || '' });
    } catch {
      setSelectedCode({ name: server.source_name, code: 'Failed to load code.' });
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await fetch(`${API}/mcp-servers/${id}`, { method: 'DELETE' });
      setServers(prev => prev.filter(s => s._id !== id));
      if (selectedCode) setSelectedCode(null);
    } catch {}
    setDeleteConfirm(null);
  };

  const handleAsk = async () => {
    if (!question.trim()) return;
    setAskLoading(true);
    setAnswer('');
    try {
      const r = await fetch(`${API}/api/chat/mcp-servers/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await r.json();
      setAnswer(data.reply || 'No answer.');
    } catch {
      setAnswer('Error contacting server.');
    } finally {
      setAskLoading(false);
    }
  };

  const formatDate = (iso: string) =>
    iso ? new Date(iso).toLocaleString() : '—';

  const badgeClass = (type: string) => {
    const map: Record<string, string> = {
      openapi: 'badge-blue',
      postman: 'badge-orange',
      sdk: 'badge-purple',
      url: 'badge-green',
    };
    return `mcp-badge ${map[type] || 'badge-gray'}`;
  };

  return (
    <div className="mongo-mcp-panel card">
      <div className="mcp-panel-header">
        <h2 className="section-title">MongoDB — Stored MCP Servers</h2>
        <button className="mcp-refresh-btn" onClick={fetchServers} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* NL Query Box */}
      <div className="mcp-query-box">
        <input
          className="mcp-query-input"
          placeholder='Ask anything: "which MCP has the most tools?", "list all MCPs", "show latest"'
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAsk()}
          disabled={askLoading}
        />
        <button className="mcp-ask-btn" onClick={handleAsk} disabled={askLoading || !question.trim()}>
          {askLoading ? '...' : 'Ask'}
        </button>
      </div>
      {answer && (
        <div className="mcp-answer-box">
          <pre>{answer}</pre>
        </div>
      )}

      {/* Table */}
      {servers.length === 0 && !loading ? (
        <p className="mcp-empty">No MCP servers stored yet. Generate one via "Forge Tools" + pipeline.</p>
      ) : (
        <div className="mcp-table-wrap">
          <table className="mcp-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Type</th>
                <th>Tools</th>
                <th>Lines</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {servers.map(s => (
                <tr key={s._id} className={selectedCode?.name === s.source_name ? 'mcp-row-active' : ''}>
                  <td className="mcp-source-cell" title={s._id}>
                    <span className="mcp-source-name">{s.source_name}</span>
                    <span className="mcp-id-chip">{s._id.slice(0, 8)}…</span>
                  </td>
                  <td><span className={badgeClass(s.source_type)}>{s.source_type}</span></td>
                  <td className="mcp-num">{s.tools_count}</td>
                  <td className="mcp-num">{s.code_lines}</td>
                  <td className="mcp-date">{formatDate(s.created_at)}</td>
                  <td className="mcp-actions-cell">
                    <button className="mcp-view-btn" onClick={() => handleViewCode(s)}>
                      {selectedCode?.name === s.source_name ? 'Hide' : 'View Code'}
                    </button>
                    {deleteConfirm === s._id ? (
                      <>
                        <button className="mcp-confirm-btn" onClick={() => handleDelete(s._id)}>Confirm</button>
                        <button className="mcp-cancel-btn" onClick={() => setDeleteConfirm(null)}>Cancel</button>
                      </>
                    ) : (
                      <button className="mcp-del-btn" onClick={() => setDeleteConfirm(s._id)}>Delete</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Code Viewer */}
      {selectedCode && (
        <div className="mcp-code-viewer">
          <div className="mcp-code-header">
            <span>{selectedCode.name}</span>
            <button className="mcp-copy-btn" onClick={() => navigator.clipboard.writeText(selectedCode.code)}>
              Copy
            </button>
            <button className="mcp-close-code-btn" onClick={() => setSelectedCode(null)}>✕</button>
          </div>
          <pre className="mcp-code-pre"><code>{selectedCode.code}</code></pre>
        </div>
      )}
    </div>
  );
}
