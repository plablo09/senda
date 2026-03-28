import { useState, useEffect, useRef, useCallback, type CSSProperties } from "react";
import { useParams, useNavigate } from "react-router-dom";
import type { Block } from "@blocknote/core";
import type { Block as SerBlock } from "../editor/serializer";
import { SendaEditor } from "../editor/SendaEditor";
import { schema } from "../editor/schema";
import { blockNoteToAST, astToBlockNote } from "../editor/serializer";
import { obtener, crear, actualizar } from "../api/documentos";
import { useRenderStatus } from "../hooks/useRenderStatus";
import type { EstadoRender, DocumentoAST } from "../api/types";
import { t } from "../i18n";

// ---- Styles ----

const pageStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100vh",
  fontFamily: "system-ui, sans-serif",
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  padding: "12px 20px",
  borderBottom: "1px solid #e2e8f0",
  background: "#fff",
  flexShrink: 0,
};

const titleInputStyle: CSSProperties = {
  flex: 1,
  fontSize: "20px",
  fontWeight: 600,
  border: "none",
  outline: "none",
  padding: "4px 0",
  minWidth: 0,
};

const saveBtnStyle: CSSProperties = {
  padding: "8px 18px",
  borderRadius: "6px",
  border: "none",
  background: "#4a90e2",
  color: "#fff",
  cursor: "pointer",
  fontSize: "14px",
  fontWeight: 600,
  position: "relative",
  flexShrink: 0,
};

const saveBtnDisabledStyle: CSSProperties = {
  ...saveBtnStyle,
  opacity: 0.6,
  cursor: "not-allowed",
};

const dirtyDotStyle: CSSProperties = {
  position: "absolute",
  top: "4px",
  right: "4px",
  width: "8px",
  height: "8px",
  borderRadius: "50%",
  background: "#f6ad55",
};

const statusBarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  padding: "8px 20px",
  borderBottom: "1px solid #e2e8f0",
  background: "#fafafa",
  flexShrink: 0,
  fontSize: "13px",
};

const mainAreaStyle: CSSProperties = {
  display: "flex",
  flex: 1,
  overflow: "hidden",
};

const editorPaneStyle: CSSProperties = {
  flex: 1,
  overflow: "auto",
  padding: "16px",
};

const previewPaneStyle: CSSProperties = {
  width: "400px",
  flexShrink: 0,
  borderLeft: "1px solid #e2e8f0",
  display: "flex",
  flexDirection: "column",
  background: "#fafafa",
};

const previewHeaderStyle: CSSProperties = {
  padding: "10px 14px",
  borderBottom: "1px solid #e2e8f0",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "8px",
};

const iframeStyle: CSSProperties = {
  flex: 1,
  border: "none",
  width: "100%",
};

const toastStyle = (type: "success" | "error"): CSSProperties => ({
  position: "fixed",
  bottom: "24px",
  right: "24px",
  padding: "12px 20px",
  borderRadius: "8px",
  background: type === "success" ? "#276749" : "#c53030",
  color: "#fff",
  fontSize: "14px",
  fontWeight: 500,
  zIndex: 9999,
  boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
});

// ---- Badge helpers ----

function badgeStyle(estado: EstadoRender | null): CSSProperties {
  const base: CSSProperties = {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: "12px",
    fontSize: "12px",
    fontWeight: 600,
  };
  switch (estado) {
    case "pendiente":
      return { ...base, background: "#e2e8f0", color: "#4a5568" };
    case "procesando":
      return { ...base, background: "#ebf8ff", color: "#2b6cb0" };
    case "listo":
      return { ...base, background: "#f0fff4", color: "#276749" };
    case "fallido":
      return { ...base, background: "#fff5f5", color: "#c53030" };
    default:
      return { ...base, background: "#e2e8f0", color: "#4a5568" };
  }
}

// ---- Component ----

interface Toast {
  message: string;
  type: "success" | "error";
}

export function Editor() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();

  const [titulo, setTitulo] = useState("");
  const [blocks, setBlocks] = useState<Block<typeof schema.blockSchema>[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [initialBlocks, setInitialBlocks] = useState<any[] | undefined>(undefined);
  const [isSaving, setIsSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const [isLoading, setIsLoading] = useState(!!id);

  const documentoId = id ?? null;
  const { estado, urlArtefacto, errorRender } = useRenderStatus(documentoId);

  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load document on mount when id is provided
  useEffect(() => {
    if (!id) return;
    setIsLoading(true);
    obtener(id)
      .then((doc) => {
        setTitulo(doc.titulo);
        if (doc.ast) {
          setInitialBlocks(astToBlockNote(doc.ast));
        }
      })
      .catch(() => {
        showToast(t("editor.error_guardar"), "error");
      })
      .finally(() => {
        setIsLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // beforeunload warning when dirty
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  function showToast(message: string, type: "success" | "error") {
    setToast({ message, type });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  }

  const handleBlocksChange = useCallback((newBlocks: Block<typeof schema.blockSchema>[]) => {
    setBlocks(newBlocks);
    setIsDirty(true);
  }, []);

  async function handleSave() {
    if (isSaving) return;
    setIsSaving(true);
    try {
      const executionUrl = `ws://${location.host}/ws/ejecutar`;
      const ast = blockNoteToAST(blocks as SerBlock[], executionUrl) as DocumentoAST;
      let doc;
      if (id) {
        doc = await actualizar(id, titulo, ast);
      } else {
        doc = await crear(titulo, ast);
      }
      setIsDirty(false);
      if (!id) {
        navigate(`/editor/${doc.id}`);
      }
      showToast("Guardado correctamente", "success");
    } catch {
      showToast(t("editor.error_guardar"), "error");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCopyLink() {
    if (!urlArtefacto) return;
    try {
      await navigator.clipboard.writeText(urlArtefacto);
      showToast(t("editor.enlace_copiado"), "success");
    } catch {
      showToast("No se pudo copiar el enlace", "error");
    }
  }

  function handleUpdatePreview() {
    if (urlArtefacto) {
      setPreviewSrc(urlArtefacto);
    }
  }

  if (isLoading) {
    return (
      <div style={{ padding: "40px", textAlign: "center", color: "#718096" }}>
        Cargando...
      </div>
    );
  }

  return (
    <div style={pageStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <input
          style={titleInputStyle}
          value={titulo}
          onChange={(e) => {
            setTitulo(e.target.value);
            setIsDirty(true);
          }}
          placeholder={t("editor.title_placeholder")}
        />
        <button
          style={isSaving ? saveBtnDisabledStyle : saveBtnStyle}
          onClick={() => void handleSave()}
          disabled={isSaving}
        >
          {isSaving ? t("editor.guardando") : t("editor.guardar")}
          {isDirty && !isSaving && <span style={dirtyDotStyle} />}
        </button>
      </div>

      {/* Render status bar */}
      {documentoId && (
        <div style={statusBarStyle}>
          <span style={badgeStyle(estado)}>
            {estado === "pendiente" && t("leccion.estado.pendiente")}
            {estado === "procesando" && (
              <>
                {"⏳ "}
                {t("leccion.estado.procesando")}
              </>
            )}
            {estado === "listo" && t("leccion.estado.listo")}
            {estado === "fallido" && t("leccion.estado.fallido")}
            {estado === null && t("leccion.estado.pendiente")}
          </span>

          {estado === "listo" && urlArtefacto && (
            <>
              <input
                readOnly
                value={urlArtefacto}
                style={{
                  flex: 1,
                  padding: "4px 8px",
                  border: "1px solid #e2e8f0",
                  borderRadius: "4px",
                  fontSize: "12px",
                  maxWidth: "300px",
                  background: "#f7fafc",
                }}
              />
              <button
                style={{
                  padding: "4px 10px",
                  borderRadius: "4px",
                  border: "1px solid #4a90e2",
                  background: "#fff",
                  color: "#4a90e2",
                  cursor: "pointer",
                  fontSize: "12px",
                }}
                onClick={() => void handleCopyLink()}
              >
                {t("editor.copiar_enlace")}
              </button>
            </>
          )}

          {estado === "fallido" && (
            <button
              style={{
                padding: "4px 10px",
                borderRadius: "4px",
                border: "1px solid #e2e8f0",
                background: "#fff",
                cursor: "pointer",
                fontSize: "12px",
                color: "#718096",
              }}
              onClick={() => setShowErrorDetails((v) => !v)}
            >
              {showErrorDetails
                ? t("editor.ocultar_detalles")
                : t("editor.ver_detalles")}
            </button>
          )}
        </div>
      )}

      {/* Error details */}
      {estado === "fallido" && showErrorDetails && errorRender && (
        <div
          style={{
            padding: "8px 20px",
            background: "#fff5f5",
            borderBottom: "1px solid #feb2b2",
            fontSize: "12px",
            color: "#c53030",
            fontFamily: "monospace",
            whiteSpace: "pre-wrap",
            maxHeight: "150px",
            overflow: "auto",
          }}
        >
          {errorRender}
        </div>
      )}

      {/* Main area */}
      <div style={mainAreaStyle}>
        <div style={editorPaneStyle}>
          <SendaEditor key={id ?? "new"} initialContent={initialBlocks} onChange={handleBlocksChange} />
        </div>

        {/* Preview panel */}
        <div style={previewPaneStyle}>
          <div style={previewHeaderStyle}>
            <span style={{ fontWeight: 600, fontSize: "13px", color: "#4a5568" }}>
              {t("editor.preview")}
            </span>
            <button
              style={{
                padding: "5px 12px",
                borderRadius: "5px",
                border: "1px solid #4a90e2",
                background: "#fff",
                color: "#4a90e2",
                cursor: "pointer",
                fontSize: "12px",
              }}
              onClick={handleUpdatePreview}
              disabled={!urlArtefacto}
            >
              {t("editor.actualizar_preview")}
            </button>
          </div>
          {previewSrc ? (
            <iframe
              src={previewSrc}
              style={iframeStyle}
              sandbox="allow-scripts allow-forms"
              title="Vista previa"
            />
          ) : (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#a0aec0",
                fontSize: "13px",
                padding: "20px",
                textAlign: "center",
              }}
            >
              Guarda y renderiza el documento para ver la vista previa.
            </div>
          )}
        </div>
      </div>

      {/* Toast */}
      {toast && <div style={toastStyle(toast.type)}>{toast.message}</div>}
    </div>
  );
}
