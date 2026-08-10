import React, { useState } from 'react';
import './InputSection.css';

type SourceType = 'file' | 'url' | 'sdk';

interface InputSectionProps {
  sourceType: SourceType;
  onSourceTypeChange: (type: SourceType) => void;
  sourceData: string;
  onSourceDataChange: (data: string) => void;
  file: File | null;
  onFileChange: (file: File | null) => void;
}

const InputSection: React.FC<InputSectionProps> = ({
  sourceType,
  onSourceTypeChange,
  sourceData,
  onSourceDataChange,
  file,
  onFileChange
}) => {
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      onFileChange(files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      onFileChange(files[0]);
    }
  };

  return (
    <div className="input-section card">
      <div className="card-header">
        <h2 className="card-title">1. Input Source</h2>
        <span className="badge badge-info">Required</span>
      </div>

      {/* Source Type Tabs */}
      <div className="source-tabs">
        <button
          className={`source-tab ${sourceType === 'file' ? 'active' : ''}`}
          onClick={() => onSourceTypeChange('file')}
        >
          <span className="tab-icon">📁</span>
          File Upload
        </button>
        <button
          className={`source-tab ${sourceType === 'url' ? 'active' : ''}`}
          onClick={() => onSourceTypeChange('url')}
        >
          <span className="tab-icon">🔗</span>
          Docs URL
        </button>
        <button
          className={`source-tab ${sourceType === 'sdk' ? 'active' : ''}`}
          onClick={() => onSourceTypeChange('sdk')}
        >
          <span className="tab-icon">🐍</span>
          Python SDK
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {sourceType === 'file' && (
          <div className="file-input-container">
            <div
              className={`drop-zone ${isDragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              {file ? (
                <div className="file-selected">
                  <span className="file-icon">📄</span>
                  <div className="file-info">
                    <div className="file-name">{file.name}</div>
                    <div className="file-size">{(file.size / 1024).toFixed(2)} KB</div>
                  </div>
                  <button
                    onClick={() => onFileChange(null)}
                    className="file-remove"
                  >
                    ×
                  </button>
                </div>
              ) : (
                <>
                  <span className="drop-icon">📤</span>
                  <p className="drop-text">Drag & drop your API spec file here</p>
                  <p className="drop-subtitle">or</p>
                  <label className="browse-button button-primary">
                    Browse Files
                    <input
                      type="file"
                      onChange={handleFileInput}
                      accept=".json,.yaml,.yml"
                      style={{ display: 'none' }}
                    />
                  </label>
                  <p className="drop-hint">Supports: OpenAPI, Postman, JSON, YAML</p>
                </>
              )}
            </div>
          </div>
        )}

        {sourceType === 'url' && (
          <div className="url-input-container">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="input-label">API Documentation URL</label>
              {sourceData === 'https://jsonplaceholder.typicode.com/' && (
                <span className="badge badge-success" style={{ fontSize: '11px' }}>
                  ✅ Pre-loaded
                </span>
              )}
            </div>
            <input
              type="url"
              className="text-input"
              placeholder="https://api.example.com/openapi.json"
              value={sourceData}
              onChange={(e) => onSourceDataChange(e.target.value)}
            />
            <p className="input-hint">
              {sourceData === 'https://jsonplaceholder.typicode.com/' ? (
                <span style={{ color: '#10b981', fontWeight: 500 }}>
                  🎉 JSONPlaceholder API ready! Just click "Start Pipeline"
                </span>
              ) : (
                'Enter the URL to your API documentation or OpenAPI spec'
              )}
            </p>
          </div>
        )}

        {sourceType === 'sdk' && (
          <div className="sdk-input-container">
            <label className="input-label">Python SDK Package Name</label>
            <input
              type="text"
              className="text-input"
              placeholder="e.g., fmpsdk, pycoingecko"
              value={sourceData}
              onChange={(e) => onSourceDataChange(e.target.value)}
            />
            <p className="input-hint">
              Enter the Python package name (must be installed in backend environment)
            </p>
          </div>
        )}
      </div>

      {/* Default Sample Note */}
      <div className="default-note">
        <span className="note-icon">💡</span>
        <span>A sample API spec is preloaded by default for demonstration</span>
      </div>
    </div>
  );
};

export default InputSection;
