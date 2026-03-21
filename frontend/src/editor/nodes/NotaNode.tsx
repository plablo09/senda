import { type CSSProperties } from "react";
import { createReactBlockSpec } from "@blocknote/react";
import { t } from "../../i18n";

export const notaBlockSpec = createReactBlockSpec(
  {
    type: "nota" as const,
    propSchema: {
      nivel: { default: "note" as const },
      titulo: { default: "" },
      contenido: { default: "" },
    },
    content: "none",
  },
  {
    render: ({ block, editor }) => {
      const { nivel, titulo, contenido } = block.props;

      return (
        <NotaUI
          nivel={nivel}
          titulo={titulo}
          contenido={contenido}
          onNivelChange={(val) =>
            editor.updateBlock(block, { props: { nivel: val } })
          }
          onTituloChange={(val) =>
            editor.updateBlock(block, { props: { titulo: val } })
          }
          onContenidoChange={(val) =>
            editor.updateBlock(block, { props: { contenido: val } })
          }
        />
      );
    },
  }
);

type Nivel = "note" | "tip" | "warning" | "important";

const borderColors: Record<Nivel, string> = {
  note: "#3b82f6",
  tip: "#22c55e",
  warning: "#f97316",
  important: "#ef4444",
};

const backgroundColors: Record<Nivel, string> = {
  note: "#eff6ff",
  tip: "#f0fdf4",
  warning: "#fff7ed",
  important: "#fef2f2",
};

interface NotaUIProps {
  nivel: string;
  titulo: string;
  contenido: string;
  onNivelChange: (val: Nivel) => void;
  onTituloChange: (val: string) => void;
  onContenidoChange: (val: string) => void;
}

function NotaUI({
  nivel,
  titulo,
  contenido,
  onNivelChange,
  onTituloChange,
  onContenidoChange,
}: NotaUIProps) {
  const safeNivel: Nivel =
    nivel === "note" ||
    nivel === "tip" ||
    nivel === "warning" ||
    nivel === "important"
      ? nivel
      : "note";

  const borderColor = borderColors[safeNivel];
  const backgroundColor = backgroundColors[safeNivel];

  const containerStyle: CSSProperties = {
    borderLeft: `4px solid ${borderColor}`,
    background: backgroundColor,
    borderRadius: "4px",
    padding: "12px 16px",
    margin: "8px 0",
    fontFamily: "sans-serif",
  };

  const labelStyle: CSSProperties = {
    display: "block",
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "4px",
    marginTop: "10px",
  };

  const inputStyle: CSSProperties = {
    width: "100%",
    padding: "6px 10px",
    border: "1px solid #d1d5db",
    borderRadius: "4px",
    fontSize: "14px",
    boxSizing: "border-box",
    background: "white",
  };

  const textareaStyle: CSSProperties = {
    ...inputStyle,
    minHeight: "80px",
    resize: "vertical",
  };

  const selectStyle: CSSProperties = {
    ...inputStyle,
  };

  return (
    <div style={containerStyle}>
      <label style={{ ...labelStyle, marginTop: 0 }}>
        {t("nota.nivel")}
      </label>
      <select
        style={selectStyle}
        value={nivel}
        onChange={(e) => {
          const val = e.target.value;
          if (
            val === "note" ||
            val === "tip" ||
            val === "warning" ||
            val === "important"
          ) {
            onNivelChange(val);
          }
        }}
      >
        <option value="note">{t("nota.nivel.note")}</option>
        <option value="tip">{t("nota.nivel.tip")}</option>
        <option value="warning">{t("nota.nivel.warning")}</option>
        <option value="important">{t("nota.nivel.important")}</option>
      </select>

      <label style={labelStyle}>{t("nota.titulo")}</label>
      <input
        style={inputStyle}
        type="text"
        placeholder={t("nota.titulo_placeholder")}
        value={titulo}
        onChange={(e) => onTituloChange(e.target.value)}
      />

      <label style={labelStyle}>{t("nota.contenido")}</label>
      <textarea
        style={textareaStyle}
        placeholder={t("nota.contenido_placeholder")}
        value={contenido}
        onChange={(e) => onContenidoChange(e.target.value)}
      />
    </div>
  );
}
