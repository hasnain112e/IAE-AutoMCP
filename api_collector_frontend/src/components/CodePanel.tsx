import React from 'react';
import './CodePanel.css';

interface CodePanelProps {
    code: string | null;
    issues?: Array<{
        line: number;
        severity: 'error' | 'warning' | 'suggestion';
        description: string;
    }>;
    previousCode?: string | null;
    iteration?: number;
}

const CodePanel: React.FC<CodePanelProps> = ({ code, issues = [], previousCode, iteration }) => {
  const handleCopy = () => {
    if (code) {
      navigator.clipboard.writeText(code);
    }
  };

  // Split code into lines for line numbering
  const codeLines = code ? code.split('\n') : [];
  const previousLines = previousCode ? previousCode.split('\n') : [];

  // Calculate line differences for highlighting
  const getLineDiff = (lineIndex: number): 'added' | 'removed' | 'modified' | null => {
    if (!previousCode || iteration === 1) return null;
    
    const currentLine = codeLines[lineIndex];
    const prevLine = previousLines[lineIndex];
    
    if (prevLine === undefined && currentLine !== undefined) return 'added';
    if (prevLine !== undefined && currentLine === undefined) return 'removed';
    if (prevLine !== currentLine && prevLine !== undefined && currentLine !== undefined) return 'modified';
    return null;
  };

  // Check if line has validation issue (line numbers are 1-based in issues)
  const getLineIssue = (lineNum: number) => {
    return issues.find(issue => issue.line === lineNum);
  };

  return (
    <div className="code-panel">
      <div className="panel-header">
        <h2>📄 Generated MCP Server Code</h2>
        {code && (
          <div className="header-actions">
            <span className="code-stats">{codeLines.length} lines</span>
            {iteration && iteration > 1 && (
              <span className="iteration-badge">Iteration {iteration}</span>
            )}
            <button onClick={handleCopy} className="copy-btn">
              📋 Copy Code
            </button>
          </div>
        )}
      </div>
      {code ? (
        <div className="code-container">
          <table className="code-table">
            <tbody>
              {codeLines.map((line, index) => {
                const lineNum = index + 1;  // 1-based line number (first line is 1)
                const lineDiff = getLineDiff(index);
                const lineIssue = getLineIssue(lineNum);
                const isImproved = lineDiff === 'modified' || lineDiff === 'added';
                
                return (
                  <tr 
                    key={index} 
                    className={`code-line ${lineDiff || ''} ${lineIssue ? `has-issue ${lineIssue.severity}` : ''} ${isImproved && iteration && iteration > 1 ? 'improved' : ''}`}
                    data-line={lineNum}
                  >
                    <td className="line-number" id={`line-${lineNum}`}>{lineNum}</td>
                    <td className="line-content" title={lineIssue ? `Line ${lineNum}: ${lineIssue.description}` : undefined}>
                      <span className="line-text">{line || ' '}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="no-code-placeholder">
          <span className="placeholder-icon">⏳</span>
          <p>No code generated yet. Start the pipeline to generate code.</p>
        </div>
      )}
    </div>
  );
};

export default CodePanel;
