import { useState, useRef, type CSSProperties } from "react";
import { createReactBlockSpec } from "@blocknote/react";
import { t } from "../../i18n";

export const ejercicioBlockSpec = createReactBlockSpec(
  {
    type: "ejercicio" as const,
    propSchema: {
      language: { default: "python" as const },
      exerciseId: { default: "" },
      caption: { default: "" },
      starterCode: { default: "" },
      solutionCode: { default: "" },
      hints: { default: "[]" },
    },
    content: "none",
  },
  {
    render: ({ block, editor }) => {
      const { language, caption, starterCode, solutionCode, hints } =
        block.props;

      const parsedHints: string[] = (() => {
        try {
          const parsed: unknown = JSON.parse(hints);
          if (
            Array.isArray(parsed) &&
            parsed.every((h) => typeof h === "string")
          ) {
            return parsed as string[];
          }
          return [];
        } catch {
          return [];
        }
      })();

      return (
        <EjercicioUI
          language={language}
          caption={caption}
          starterCode={starterCode}
          solutionCode={solutionCode}
          hints={parsedHints}
          onLanguageChange={(val) =>
            editor.updateBlock(block, { props: { language: val } })
          }
          onCaptionChange={(val) =>
            editor.updateBlock(block, { props: { caption: val } })
          }
          onStarterCodeChange={(val) =>
            editor.updateBlock(block, { props: { starterCode: val } })
          }
          onSolutionCodeChange={(val) =>
            editor.updateBlock(block, { props: { solutionCode: val } })
          }
          onHintsChange={(arr) =>
            editor.updateBlock(block, {
              props: { hints: JSON.stringify(arr) },
            })
          }
        />
      );
    },
  }
);

interface EjercicioUIProps {
  language: string;
  caption: string;
  starterCode: string;
  solutionCode: string;
  hints: string[];
  onLanguageChange: (val: "python" | "r") => void;
  onCaptionChange: (val: string) => void;
  onStarterCodeChange: (val: string) => void;
  onSolutionCodeChange: (val: string) => void;
  onHintsChange: (hints: string[]) => void;
}

function EjercicioUI({
  language,
  caption,
  starterCode,
  solutionCode,
  hints,
  onLanguageChange,
  onCaptionChange,
  onStarterCodeChange,
  onSolutionCodeChange,
  onHintsChange,
}: EjercicioUIProps) {
  const [showSolution, setShowSolution] = useState(false);

  const containerStyle: CSSProperties = {
    border: "1px solid #d1d5db",
    borderRadius: "8px",
    padding: "16px",
    margin: "8px 0",
    background: "#f9fafb",
    fontFamily: "sans-serif",
  };

  const labelStyle: CSSProperties = {
    display: "block",
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "4px",
    marginTop: "12px",
  };

  const inputStyle: CSSProperties = {
    width: "100%",
    padding: "6px 10px",
    border: "1px solid #d1d5db",
    borderRadius: "4px",
    fontSize: "14px",
    boxSizing: "border-box",
  };

  const textareaStyle: CSSProperties = {
    ...inputStyle,
    fontFamily: "monospace",
    minHeight: "80px",
    resize: "vertical",
  };

  const selectStyle: CSSProperties = {
    ...inputStyle,
    background: "white",
  };

  const buttonStyle: CSSProperties = {
    padding: "4px 10px",
    fontSize: "12px",
    cursor: "pointer",
    borderRadius: "4px",
    border: "1px solid #d1d5db",
    background: "white",
  };

  return (
    <div style={containerStyle}>
      <label style={labelStyle}>{t("ejercicio.language")}</label>
      <select
        style={selectStyle}
        value={language}
        onChange={(e) => {
          const val = e.target.value;
          if (val === "python" || val === "r") {
            onLanguageChange(val);
          }
        }}
      >
        <option value="python">{t("ejercicio.language.python")}</option>
        <option value="r">{t("ejercicio.language.r")}</option>
      </select>

      <label style={labelStyle}>{t("ejercicio.caption")}</label>
      <input
        style={inputStyle}
        type="text"
        placeholder={t("ejercicio.caption_placeholder")}
        value={caption}
        onChange={(e) => onCaptionChange(e.target.value)}
      />

      <label style={labelStyle}>{t("ejercicio.starter_code")}</label>
      <textarea
        style={textareaStyle}
        placeholder={t("ejercicio.starter_placeholder")}
        value={starterCode}
        onChange={(e) => onStarterCodeChange(e.target.value)}
      />

      <div style={{ marginTop: "12px" }}>
        <button
          style={buttonStyle}
          onClick={() => setShowSolution((s) => !s)}
          type="button"
        >
          {showSolution
            ? t("ejercicio.ocultar_solucion")
            : t("ejercicio.mostrar_solucion")}
        </button>
      </div>

      {showSolution && (
        <div>
          <label style={labelStyle}>{t("ejercicio.solution")}</label>
          <textarea
            style={textareaStyle}
            placeholder={t("ejercicio.solution_placeholder")}
            value={solutionCode}
            onChange={(e) => onSolutionCodeChange(e.target.value)}
          />
        </div>
      )}

      <label style={labelStyle}>{t("ejercicio.pistas")}</label>
      <HintsList hints={hints} onChange={onHintsChange} />
    </div>
  );
}

interface HintsListProps {
  hints: string[];
  onChange: (hints: string[]) => void;
}

function HintsList({ hints, onChange }: HintsListProps) {
  const textareaStyle: CSSProperties = {
    width: "100%",
    padding: "6px 10px",
    border: "1px solid #d1d5db",
    borderRadius: "4px",
    fontSize: "14px",
    boxSizing: "border-box",
    minHeight: "60px",
    resize: "vertical",
    marginBottom: "4px",
  };

  const buttonStyle: CSSProperties = {
    padding: "4px 10px",
    fontSize: "12px",
    cursor: "pointer",
    borderRadius: "4px",
    border: "1px solid #d1d5db",
    background: "white",
    marginRight: "8px",
  };

  const removeButtonStyle: CSSProperties = {
    ...buttonStyle,
    color: "#ef4444",
    borderColor: "#ef4444",
    marginRight: 0,
  };

  // We need a stable ref for hints to avoid stale closure issues
  const hintsRef = useRef(hints);
  hintsRef.current = hints;

  return (
    <div>
      {hints.map((hint, index) => (
        <div
          key={index}
          style={{ display: "flex", alignItems: "flex-start", gap: "8px" }}
        >
          <textarea
            style={{ ...textareaStyle, flex: 1 }}
            placeholder={t("ejercicio.pista_placeholder")}
            value={hint}
            onChange={(e) => {
              const updated = [...hintsRef.current];
              updated[index] = e.target.value;
              onChange(updated);
            }}
          />
          <button
            type="button"
            style={removeButtonStyle}
            onClick={() => {
              const updated = hintsRef.current.filter((_, i) => i !== index);
              onChange(updated);
            }}
            aria-label={t("ejercicio.eliminar_pista")}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        style={buttonStyle}
        onClick={() => onChange([...hints, ""])}
      >
        + {t("ejercicio.agregar_pista")}
      </button>
    </div>
  );
}
