import { useEffect, useState, useCallback, useRef } from 'react';

interface UseWebSocketOptions {
  url: string;
  onMessage: (data: any) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export function useWebSocket({
  url,
  onMessage,
  reconnectInterval = 3000,
  maxReconnectAttempts = Number.POSITIVE_INFINITY
}: UseWebSocketOptions) {
  const [connected, setConnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const manualCloseRef = useRef(false);
  const onMessageRef = useRef(onMessage);

  // Keep onMessage ref updated without triggering reconnections
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    // Prevent creating multiple connections
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected, skipping...');
      return;
    }

    try {
      console.log('Creating WebSocket connection to:', url);
      const ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('✅ WebSocket connected successfully');
        setConnected(true);
        setReconnectAttempt(0);
        manualCloseRef.current = false;

        // Start keepalive ping every 5 seconds
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }
        pingIntervalRef.current = setInterval(() => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            console.log('📡 Sending keepalive ping...');
            try {
              wsRef.current.send(JSON.stringify({ type: 'ping' }));
            } catch (err) {
              console.error('Failed to send ping:', err);
            }
          }
        }, 5000); // Ping every 5 seconds
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data?.type === 'ping') {
            wsRef.current?.send(JSON.stringify({ type: 'pong' }));
            return;
          }
          if (data?.type === 'pong') {
            return;
          }
          // Use ref to avoid reconnection on onMessage change
          onMessageRef.current(data);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
      };

      ws.onclose = (event) => {
        console.log('🔌 WebSocket disconnected. Code:', event.code, 'Reason:', event.reason);
        setConnected(false);
        wsRef.current = null;

        // Stop ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        if (!manualCloseRef.current && reconnectAttempt < maxReconnectAttempts) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(`🔄 Reconnecting... (attempt ${reconnectAttempt + 1})`);
            setReconnectAttempt(prev => prev + 1);
            connect();
          }, reconnectInterval);
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
    }
  }, [url, reconnectAttempt, maxReconnectAttempts, reconnectInterval]);

  useEffect(() => {
    connect();

    return () => {
      console.log('Cleaning up WebSocket...');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (wsRef.current) {
        manualCloseRef.current = true;
        wsRef.current.close(1000, 'Component unmounting');
        wsRef.current = null;
      }
    };
  }, [url]); // Only reconnect if URL changes

  const sendMessage = useCallback((data: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
      return true;
    }
    console.warn('WebSocket not connected, cannot send message');
    return false;
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      manualCloseRef.current = true;
      wsRef.current.close();
    }
  }, []);

  return {
    connected,
    sendMessage,
    disconnect,
    reconnectAttempt
  };
}
