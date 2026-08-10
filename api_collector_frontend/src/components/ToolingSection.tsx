
import React from 'react';
import './ToolingSection.css';

interface Tool {
  name: string;
  status: 'Loaded' | 'Parsed' | 'Ready';
  description: string;
}

interface ToolingSectionProps {
  tools: Tool[];
}

const ToolingSection: React.FC<ToolingSectionProps> = ({ tools }) => {
  return (
    <div className="tooling-section">
      <h2>Tooling</h2>
      <table className="tools-table">
        <thead>
          <tr>
            <th>Tool Name</th>
            <th>Status</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {tools.map((tool, index) => (
            <tr key={index}>
              <td>{tool.name}</td>
              <td><span className={`status-pill ${tool.status.toLowerCase()}`}>{tool.status}</span></td>
              <td>{tool.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ToolingSection;
