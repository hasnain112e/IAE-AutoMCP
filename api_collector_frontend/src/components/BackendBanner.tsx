/**
 * Backend Banner Component
 * 
 * Displays a non-blocking banner when backend is not detected.
 */

import React from "react";
import "./BackendBanner.css";

interface BackendBannerProps {
  visible: boolean;
  onDismiss?: () => void;
}

export const BackendBanner: React.FC<BackendBannerProps> = ({
  visible,
  onDismiss,
}) => {
  if (!visible) return null;

  return (
    <div className="backend-banner">
      <div className="backend-banner-content">
        <span className="backend-banner-icon">⚠️</span>
        <span className="backend-banner-text">
          Backend Not Detected — Waiting for Server…
        </span>
        {onDismiss && (
          <button
            className="backend-banner-dismiss"
            onClick={onDismiss}
            aria-label="Dismiss"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
};

