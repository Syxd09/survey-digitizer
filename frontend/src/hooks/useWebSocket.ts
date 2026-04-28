import { useEffect, useRef, useCallback, useState } from 'react';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8005/ws';
const RECONNECT_DELAY = 3000;
const PING_INTERVAL = 25000;

type MessageHandler = (data: any) => void;

interface UseWebSocketReturn {
  isConnected: boolean;
  send: (message: any) => void;
  requestVault: () => void;
  requestMetrics: () => void;
  requestScanStatus: (scanId: string) => void;
}

/**
 * Singleton WebSocket hook — replaces HTTP polling with real-time push.
 * 
 * Auto-reconnects, sends keepalive pings, and dispatches incoming
 * messages to registered handlers.
 */
export function useWebSocket(onMessage: MessageHandler): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const onMessageRef = useRef<MessageHandler>(onMessage);
  const [isConnected, setIsConnected] = useState(false);

  // Keep handler ref fresh without re-triggering effect
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (wsRef.current?.readyState === WebSocket.OPEN || 
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[WS] Connected');
      setIsConnected(true);

      // Start keepalive pings
      if (pingTimer.current) clearInterval(pingTimer.current);
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, PING_INTERVAL);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type !== 'pong') {
          onMessageRef.current(data);
        }
      } catch (err) {
        console.warn('[WS] Parse error:', err);
      }
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected — reconnecting...');
      setIsConnected(false);
      if (pingTimer.current) clearInterval(pingTimer.current);

      // Auto-reconnect
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
    };

    ws.onerror = (err) => {
      console.warn('[WS] Error:', err);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (pingTimer.current) clearInterval(pingTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const requestVault = useCallback(() => send({ type: 'request_vault' }), [send]);
  const requestMetrics = useCallback(() => send({ type: 'request_metrics' }), [send]);
  const requestScanStatus = useCallback((scanId: string) => 
    send({ type: 'request_scan_status', scanId }), [send]);

  return { isConnected, send, requestVault, requestMetrics, requestScanStatus };
}
