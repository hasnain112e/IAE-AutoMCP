
import React from 'react';
import './InputOptions.css';

type SourceKind = "file" | "url" | "sdk";

interface InputOptionsProps {
  sourceKind: SourceKind;
  setSourceKind: (kind: SourceKind) => void;
  file: File | null;
  setFile: (file: File | null) => void;
  url: string;
  setUrl: (url: string) => void;
  sdkName: string;
  setSdkName: (name: string) => void;
}

const InputOptions: React.FC<InputOptionsProps> = ({
  sourceKind,
  setSourceKind,
  file,
  setFile,
  url,
  setUrl,
  sdkName,
  setSdkName
}) => {

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();

    const droppedFiles = e.dataTransfer.files;
    if (!droppedFiles || droppedFiles.length === 0) return;

    const f = droppedFiles[0];
    setFile(f);
  };

  const triggerFilePicker = () => {
    const input = document.getElementById(
      "file-input-hidden"
    ) as HTMLInputElement | null;
    if (input) input.click();
  };


  return (
    <div className="input-options">
      <div className="tabs">
        <button className={sourceKind === 'file' ? 'active' : ''} onClick={() => setSourceKind('file')}>File Upload</button>
        <button className={sourceKind === 'url' ? 'active' : ''} onClick={() => setSourceKind('url')}>Docs URL</button>
        <button className={sourceKind === 'sdk' ? 'active' : ''} onClick={() => setSourceKind('sdk')}>Python SDK</button>
      </div>
      <div className="tab-content">
        {sourceKind === 'file' && (
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={triggerFilePicker}
            className="dropzone"
          >
            <p>Drag & drop your OpenAPI / Postman / JSON / YAML file here, or click to select a file.</p>
            {file && <p>Selected file: {file.name}</p>}
            <input
              id="file-input-hidden"
              type="file"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setFile(f);
              }}
            />
          </div>
        )}
        {sourceKind === 'url' && (
          <div>
            <input type="text" placeholder="Enter Docs URL" value={url} onChange={(e) => setUrl(e.target.value)} />
          </div>
        )}
        {sourceKind === 'sdk' && (
          <div>
            <input type="text" placeholder="Enter Python SDK reference" value={sdkName} onChange={(e) => setSdkName(e.target.value)} />
          </div>
        )}
      </div>
    </div>
  );
};

export default InputOptions;
