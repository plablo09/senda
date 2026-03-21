import { useEffect, useState, useRef } from "react";
import type { EstadoRender } from "../api/types";
import { obtener } from "../api/documentos";

export function useRenderStatus(documentoId: string | null) {
  const [estado, setEstado] = useState<EstadoRender | null>(null);
  const [urlArtefacto, setUrlArtefacto] = useState<string | null>(null);
  const [errorRender, setErrorRender] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Use a ref to track terminal state to avoid stale closure in ws.onclose
  const isTerminalRef = useRef<boolean>(false);

  useEffect(() => {
    if (!documentoId) return;
    const docId: string = documentoId;

    const TERMINAL = new Set<EstadoRender>(["listo", "fallido"]);
    isTerminalRef.current = false;

    function stopAll() {
      wsRef.current?.close();
      wsRef.current = null;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    }

    function startPolling() {
      if (pollRef.current) return;
      pollRef.current = setInterval(() => {
        obtener(docId)
          .then((doc) => {
            setEstado(doc.estado_render);
            setUrlArtefacto(doc.url_artefacto);
            setErrorRender(doc.error_render);
            if (TERMINAL.has(doc.estado_render)) {
              isTerminalRef.current = true;
              stopAll();
            }
          })
          .catch(() => {
            // keep polling
          });
      }, 3000);
    }

    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${protocol}//${location.host}/ws/documentos/${docId}/estado`,
    );
    wsRef.current = ws;

    ws.onmessage = (event: MessageEvent) => {
      const data = JSON.parse(event.data as string) as {
        status: EstadoRender;
        url_artefacto: string | null;
        error_render: string | null;
      };
      setEstado(data.status);
      setUrlArtefacto(data.url_artefacto);
      setErrorRender(data.error_render);
      if (TERMINAL.has(data.status)) {
        isTerminalRef.current = true;
        stopAll();
      }
    };

    ws.onerror = () => startPolling();
    ws.onclose = () => {
      if (!isTerminalRef.current) startPolling();
    };

    return stopAll;
  }, [documentoId]);

  return { estado, urlArtefacto, errorRender };
}
