import React from 'react';
import './ToolsPanel.css';

interface Tool {
  name: string;
  description: string;
  method?: string;
  path?: string;
  tags: string[];
}

interface ToolsPanelProps {
  tools: Tool[];
  state: string;
}

const ToolsPanel: React.FC<ToolsPanelProps> = ({ tools, state }) => {
  const getStatusBadge = () => {
    if (tools.length === 0) return <span className="badge badge-warning">No Tools</span>;
    if (state === 'collecting_tools') return <span className="badge badge-info">Loading...</span>;
    if (state === 'tools_ready' || tools.length > 0) return <span className="badge badge-success">Ready</span>;
    return <span className="badge badge-warning">Waiting</span>;
  };

  return (
    <div className="tools-panel card">
      <div className="card-header">
        <h2 className="card-title">2. API Tools</h2>
        {getStatusBadge()}
      </div>

      {tools.length > 0 ? (
        <>
          <div className="tools-summary">
            <span className="tools-count">{tools.length} tools extracted</span>
          </div>

          <div className="tools-table-container">
            <table className="tools-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Method</th>
                  <th>Path</th>
                  <th>Tags</th>
                </tr>
              </thead>
              <tbody>
                {tools.slice(0, 10).map((tool, index) => (
                  <tr key={index}>
                    <td className="tool-name">{tool.name}</td>
                    <td>
                      <span className={`method-badge method-${tool.method?.toLowerCase()}`}>
                        {tool.method || 'N/A'}
                      </span>
                    </td>
                    <td className="tool-path">{tool.path || '-'}</td>
                    <td>
                      <div className="tool-tags">
                        {tool.tags.slice(0, 2).map((tag, i) => (
                          <span key={i} className="tag">{tag}</span>
                        ))}
                        {tool.tags.length > 2 && (
                          <span className="tag">+{tool.tags.length - 2}</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {tools.length > 10 && (
            <div className="tools-footer">
              <span className="tools-note">Showing 10 of {tools.length} tools</span>
            </div>
          )}
        </>
      ) : (
        <div className="tools-empty">
          <span className="empty-icon">📋</span>
          <p>No tools loaded yet</p>
          <p className="empty-subtitle">Upload an API spec or provide a URL to get started</p>
        </div>
      )}
    </div>
  );
};

export default ToolsPanel;
