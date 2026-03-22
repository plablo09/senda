import { useState, useEffect, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import type { Documento } from "../api/types";
import { listar, eliminar } from "../api/documentos";
import { LeccionCard } from "../components/LeccionCard";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { t } from "../i18n";

const pageStyle: CSSProperties = {
  maxWidth: "800px",
  margin: "0 auto",
  padding: "40px 20px",
  fontFamily: "system-ui, sans-serif",
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "24px",
};

const titleStyle: CSSProperties = {
  margin: 0,
  fontSize: "24px",
  fontWeight: 700,
};

const newBtnStyle: CSSProperties = {
  padding: "8px 18px",
  borderRadius: "6px",
  border: "none",
  background: "#4a90e2",
  color: "#fff",
  cursor: "pointer",
  fontSize: "14px",
  fontWeight: 600,
};

const listStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "12px",
};

const emptyStyle: CSSProperties = {
  textAlign: "center",
  color: "#718096",
  padding: "60px 20px",
  fontSize: "15px",
};

const loadingStyle: CSSProperties = {
  textAlign: "center",
  color: "#a0aec0",
  padding: "60px 20px",
  fontSize: "15px",
};

export function Inicio() {
  const navigate = useNavigate();
  const [documentos, setDocumentos] = useState<Documento[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  useEffect(() => {
    listar()
      .then((docs) => {
        setDocumentos(docs);
      })
      .catch(() => {
        // fail silently; list stays empty
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  function handleEliminarRequest(id: string) {
    setConfirmId(id);
  }

  async function handleEliminarConfirm() {
    if (!confirmId) return;
    const idToDelete = confirmId;
    setConfirmId(null);
    try {
      await eliminar(idToDelete);
      setDocumentos((prev) => prev.filter((d) => d.id !== idToDelete));
    } catch {
      // ignore
    }
  }

  function handleEliminarCancel() {
    setConfirmId(null);
  }

  return (
    <div style={pageStyle}>
      <div style={headerStyle}>
        <h1 style={titleStyle}>{t("inicio.title")}</h1>
        <button style={newBtnStyle} onClick={() => navigate("/editor")}>
          {t("inicio.nueva_leccion")}
        </button>
      </div>

      {isLoading ? (
        <div style={loadingStyle}>Cargando...</div>
      ) : documentos.length === 0 ? (
        <div style={emptyStyle}>{t("inicio.empty")}</div>
      ) : (
        <div style={listStyle}>
          {documentos.map((doc) => (
            <LeccionCard
              key={doc.id}
              documento={doc}
              onEliminar={handleEliminarRequest}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        isOpen={confirmId !== null}
        onConfirm={() => void handleEliminarConfirm()}
        onCancel={handleEliminarCancel}
      />
    </div>
  );
}
