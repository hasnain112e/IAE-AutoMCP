// Edited by Dr. Wasim
import React, { useState, useEffect, useRef } from "react";
import { getBackendStatus, BackendReadyResponse } from "../api/backend";

export type ConnectionStatus = "connected" | "connecting" | "offline";

export const getStatusIcon = (status: ConnectionStatus) => {
  switch (status) {
    case "connected":
      return "\u{1F7E2}";
    case "connecting":
      return "\u{1F7E1}";
    case "offline":
      return "\u{1F534}";
    default:
      return "\u{1F7E1}";
  }
};

interface ConnectionStatusProps {
  pollingInterval?: number; // milliseconds
  onStatusChange?: (status: ConnectionStatus) => void;
  onServiceStatusChange?: (statuses: {
    orchestrator: ConnectionStatus;
    generator: ConnectionStatus;
    validator: ConnectionStatus;
    backend: ConnectionStatus;
  }) => void;
}

export const ConnectionStatus: React.FC<ConnectionStatusProps> = ({
  pollingInterval = 2000,
  onStatusChange,
  onServiceStatusChange,
}) => {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [backendStatus, setBackendStatus] = useState<BackendReadyResponse | null>(null);
  const lastGoodPingRef = useRef<number | null>(null);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;
    let mounted = true;

    const checkConnection = async () => {
      try {
        const result = await getBackendStatus();

        if (!mounted) return;

        const backendHealthy =
          !!result &&
          (result.backend === "ready" ||
            result.backend === "healthy" ||
            result.status === "healthy" ||
            result.status === "ready");

        if (backendHealthy) {
          setStatus("connected");
          setBackendStatus(result);
          lastGoodPingRef.current = Date.now();
          onStatusChange?.("connected");
          notifyServiceStatuses("connected", result);
        } else {
          setStatus("connecting");
          setBackendStatus(result);
          onStatusChange?.("connecting");
          notifyServiceStatuses("connecting", result);
        }
      } catch {
        if (!mounted) return;
        const lastPing = lastGoodPingRef.current;
        const recent = lastPing && Date.now() - lastPing < 12000;
        const fallbackStatus: ConnectionStatus = recent ? "connecting" : "offline";
        setStatus(fallbackStatus);
        setBackendStatus(null);
        onStatusChange?.(fallbackStatus);
        notifyServiceStatuses(fallbackStatus, null);
      }
    };

    checkConnection();
    intervalId = setInterval(checkConnection, pollingInterval);

    return () => {
      mounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [pollingInterval, onStatusChange, onServiceStatusChange]);

  const notifyServiceStatuses = (
    backendConnection: ConnectionStatus,
    services: BackendReadyResponse | null
  ) => {
    if (!onServiceStatusChange) return;

    const backendHealth = services?.status || services?.backend;
    const derive = (serviceReady?: "ready" | "unavailable" | boolean | string): ConnectionStatus => {
      if (backendConnection === "offline") return "offline";
      if (backendConnection === "connecting") return "connecting";
      if (
        serviceReady === "ready" ||
        serviceReady === true ||
        serviceReady === "healthy"
      ) {
        return "connected";
      }
      if (serviceReady === "unavailable" || serviceReady === false) return "offline";
      if (backendHealth === "healthy" || backendHealth === "ready") return "connected";
      return "connecting";
    };

    onServiceStatusChange({
      orchestrator: derive(services?.orchestrator),
      generator: derive(services?.generator),
      validator: derive(services?.validator),
      backend: backendConnection,
    });
  };

  // Component renders no UI; status is surfaced through callbacks.
  return null;
};
