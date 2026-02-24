import { useEffect, useRef, useState } from "react";
import type { SystemState } from "../types";

type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function useSystemState() {
  const [state, setState] = useState<SystemState | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = () => {
    // Clean up any existing source
    if (esRef.current) {
      esRef.current.close();
    }
    setStatus("connecting");

    const es = new EventSource("/api/stream");
    esRef.current = es;

    es.onopen = () => setStatus("connected");

    es.onmessage = (event) => {
      try {
        const data: SystemState = JSON.parse(event.data);
        setState(data);
        setStatus("connected");
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setStatus("disconnected");
      es.close();
      esRef.current = null;
      // Reconnect after 5 seconds
      retryRef.current = setTimeout(connect, 5000);
    };
  };

  useEffect(() => {
    connect();
    return () => {
      esRef.current?.close();
      if (retryRef.current) clearTimeout(retryRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { state, status };
}

export async function setRelayOverride(relay: string, on: boolean): Promise<void> {
  await fetch(`/api/relay/${relay}/override?state=${on}`, { method: "POST" });
}

export async function clearRelayOverride(relay: string): Promise<void> {
  await fetch(`/api/relay/${relay}/override`, { method: "DELETE" });
}
