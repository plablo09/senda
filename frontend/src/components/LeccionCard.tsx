import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import type { Documento, EstadoRender } from "../api/types";
import { t } from "../i18n";

interface Props {
  documento: Documento;
  onEliminar: (id: string) => void;
}

function estadoBadgeStyle(estado: EstadoRender): CSSProperties {
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
  }
}

const cardStyle: CSSProperties = {
  border: "1px solid #e2e8f0",
  borderRadius: "8px",
  padding: "16px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "16px",
  background: "#fff",
};

const infoStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
};

const titleStyle: CSSProperties = {
  margin: "0 0 6px",
  fontSize: "16px",
  fontWeight: 600,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const metaStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  fontSize: "12px",
  color: "#718096",
};

const actionsStyle: CSSProperties = {
  display: "flex",
  gap: "8px",
  flexShrink: 0,
};

const editBtnStyle: CSSProperties = {
  padding: "6px 14px",
  borderRadius: "6px",
  border: "1px solid #4a90e2",
  background: "#fff",
  color: "#4a90e2",
  cursor: "pointer",
  fontSize: "13px",
  fontWeight: 500,
};

const deleteBtnStyle: CSSProperties = {
  padding: "6px 14px",
  borderRadius: "6px",
  border: "1px solid #e53e3e",
  background: "#fff",
  color: "#e53e3e",
  cursor: "pointer",
  fontSize: "13px",
  fontWeight: 500,
};

function estadoLabel(estado: EstadoRender): string {
  switch (estado) {
    case "pendiente":
      return t("leccion.estado.pendiente");
    case "procesando":
      return t("leccion.estado.procesando");
    case "listo":
      return t("leccion.estado.listo");
    case "fallido":
      return t("leccion.estado.fallido");
  }
}

export function LeccionCard({ documento, onEliminar }: Props) {
  const navigate = useNavigate();

  const fecha = new Date(documento.created_at).toLocaleDateString("es", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div style={cardStyle}>
      <div style={infoStyle}>
        <h3 style={titleStyle}>{documento.titulo || "(Sin título)"}</h3>
        <div style={metaStyle}>
          <span style={estadoBadgeStyle(documento.estado_render)}>
            {estadoLabel(documento.estado_render)}
          </span>
          <span>{fecha}</span>
        </div>
      </div>
      <div style={actionsStyle}>
        <button
          style={editBtnStyle}
          onClick={() => navigate(`/editor/${documento.id}`)}
        >
          {t("leccion.editar")}
        </button>
        <button style={deleteBtnStyle} onClick={() => onEliminar(documento.id)}>
          {t("leccion.eliminar")}
        </button>
      </div>
    </div>
  );
}
