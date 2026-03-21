import type { CSSProperties } from "react";
import { t } from "../i18n";

interface Props {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const overlayStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  backgroundColor: "rgba(0, 0, 0, 0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const dialogStyle: CSSProperties = {
  backgroundColor: "#fff",
  borderRadius: "8px",
  padding: "24px",
  maxWidth: "400px",
  width: "90%",
  boxShadow: "0 4px 24px rgba(0,0,0,0.18)",
};

const titleStyle: CSSProperties = {
  margin: "0 0 8px",
  fontSize: "18px",
  fontWeight: 600,
};

const messageStyle: CSSProperties = {
  margin: "0 0 24px",
  color: "#666",
  fontSize: "14px",
};

const actionsStyle: CSSProperties = {
  display: "flex",
  gap: "12px",
  justifyContent: "flex-end",
};

const cancelBtnStyle: CSSProperties = {
  padding: "8px 16px",
  borderRadius: "6px",
  border: "1px solid #ccc",
  background: "#fff",
  cursor: "pointer",
  fontSize: "14px",
};

const confirmBtnStyle: CSSProperties = {
  padding: "8px 16px",
  borderRadius: "6px",
  border: "none",
  background: "#e53e3e",
  color: "#fff",
  cursor: "pointer",
  fontSize: "14px",
  fontWeight: 600,
};

export function ConfirmDialog({ isOpen, onConfirm, onCancel }: Props) {
  if (!isOpen) return null;

  return (
    <div style={overlayStyle} onClick={onCancel}>
      <div style={dialogStyle} onClick={(e) => e.stopPropagation()}>
        <h2 style={titleStyle}>{t("confirm.eliminar.title")}</h2>
        <p style={messageStyle}>{t("confirm.eliminar.message")}</p>
        <div style={actionsStyle}>
          <button style={cancelBtnStyle} onClick={onCancel}>
            {t("confirm.eliminar.cancel")}
          </button>
          <button style={confirmBtnStyle} onClick={onConfirm}>
            {t("confirm.eliminar.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
