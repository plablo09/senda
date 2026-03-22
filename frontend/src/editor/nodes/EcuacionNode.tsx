import { useMemo, useRef, type CSSProperties } from "react";
import { createReactBlockSpec } from "@blocknote/react";
import katex from "katex";
import "katex/dist/katex.min.css";
import { t } from "../../i18n";

export const ecuacionBlockSpec = createReactBlockSpec(
  {
    type: "ecuacion" as const,
    propSchema: {
      latex: { default: "" },
      modo: { default: "bloque" as const },
    },
    content: "none",
  },
  {
    render: ({ block, editor }) => {
      const { latex, modo } = block.props;

      return (
        <EcuacionUI
          latex={latex}
          modo={modo}
          onLatexChange={(val) =>
            editor.updateBlock(block, { props: { latex: val } })
          }
          onModoChange={(val) =>
            editor.updateBlock(block, { props: { modo: val } })
          }
        />
      );
    },
  }
);

type Modo = "bloque" | "linea";

interface EcuacionUIProps {
  latex: string;
  modo: string;
  onLatexChange: (val: string) => void;
  onModoChange: (val: Modo) => void;
}

const GREEK_SYMBOLS = [
  "\\alpha",
  "\\beta",
  "\\gamma",
  "\\delta",
  "\\mu",
  "\\sigma",
  "\\pi",
  "\\sum",
  "\\prod",
];

const OPERATOR_SYMBOLS = [
  "\\pm",
  "\\sqrt{}",
  "\\infty",
  "\\partial",
  "\\int",
  "\\leq",
  "\\geq",
  "\\neq",
  "\\approx",
];

const STRUCTURE_BUTTONS: Array<{ label: string; snippet: string }> = [
  { label: "Fracción", snippet: "\\frac{}{}" },
  { label: "Índice", snippet: "_{}" },
  { label: "Exponente", snippet: "^{}" },
  { label: "Raíz", snippet: "\\sqrt{}" },
];

function EcuacionUI({
  latex,
  modo,
  onLatexChange,
  onModoChange,
}: EcuacionUIProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const safeModo: Modo =
    modo === "bloque" || modo === "linea" ? modo : "bloque";

  const preview = useMemo(() => {
    try {
      return katex.renderToString(latex || "\\square", {
        throwOnError: false,
        trust: false,
        displayMode: safeModo === "bloque",
      });
    } catch {
      return "";
    }
  }, [latex, safeModo]);

  const containerStyle: CSSProperties = {
    border: "1px solid #d1d5db",
    borderRadius: "8px",
    padding: "16px",
    margin: "8px 0",
    background: "#fafaf9",
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
    fontFamily: "monospace",
    background: "white",
  };

  const symbolButtonStyle: CSSProperties = {
    padding: "3px 8px",
    margin: "2px",
    fontSize: "13px",
    fontFamily: "monospace",
    cursor: "pointer",
    borderRadius: "3px",
    border: "1px solid #d1d5db",
    background: "white",
  };

  const modeButtonStyle = (active: boolean): CSSProperties => ({
    padding: "4px 12px",
    fontSize: "13px",
    cursor: "pointer",
    borderRadius: "4px",
    border: "1px solid #d1d5db",
    background: active ? "#3b82f6" : "white",
    color: active ? "white" : "#374151",
    fontWeight: active ? 600 : 400,
    marginRight: "6px",
  });

  const previewStyle: CSSProperties = {
    border: "1px solid #e5e7eb",
    borderRadius: "4px",
    padding: "12px",
    background: "white",
    minHeight: "40px",
    overflowX: "auto",
    marginTop: "4px",
  };

  function insertSnippet(snippet: string) {
    const ta = textareaRef.current;
    if (!ta) {
      onLatexChange(latex + snippet);
      return;
    }
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const newValue = latex.slice(0, start) + snippet + latex.slice(end);
    onLatexChange(newValue);
    // Restore cursor position after state update
    requestAnimationFrame(() => {
      ta.setSelectionRange(start + snippet.length, start + snippet.length);
      ta.focus();
    });
  }

  return (
    <div style={containerStyle}>
      <label style={{ ...labelStyle, marginTop: 0 }}>{t("ecuacion.modo")}</label>
      <div>
        <button
          type="button"
          style={modeButtonStyle(safeModo === "bloque")}
          onClick={() => onModoChange("bloque")}
        >
          {t("ecuacion.modo.bloque")}
        </button>
        <button
          type="button"
          style={modeButtonStyle(safeModo === "linea")}
          onClick={() => onModoChange("linea")}
        >
          {t("ecuacion.modo.linea")}
        </button>
      </div>

      <label style={labelStyle}>{t("ecuacion.simbolos")}</label>
      <div>
        {GREEK_SYMBOLS.map((sym) => (
          <button
            key={sym}
            type="button"
            style={symbolButtonStyle}
            onClick={() => insertSnippet(sym)}
            title={sym}
          >
            {sym}
          </button>
        ))}
      </div>
      <div>
        {OPERATOR_SYMBOLS.map((sym) => (
          <button
            key={sym}
            type="button"
            style={symbolButtonStyle}
            onClick={() => insertSnippet(sym)}
            title={sym}
          >
            {sym}
          </button>
        ))}
      </div>
      <div>
        {STRUCTURE_BUTTONS.map(({ label, snippet }) => (
          <button
            key={label}
            type="button"
            style={symbolButtonStyle}
            onClick={() => insertSnippet(snippet)}
            title={snippet}
          >
            {label === "Fracción"
              ? t("ecuacion.fraccion")
              : label === "Índice"
                ? t("ecuacion.indice")
                : label === "Exponente"
                  ? t("ecuacion.exponente")
                  : t("ecuacion.raiz")}
          </button>
        ))}
      </div>

      <label style={labelStyle}>{t("ecuacion.latex")}</label>
      <textarea
        ref={textareaRef}
        style={inputStyle}
        placeholder={t("ecuacion.latex_placeholder")}
        value={latex}
        onChange={(e) => onLatexChange(e.target.value)}
        rows={3}
      />

      <label style={labelStyle}>{t("ecuacion.preview")}</label>
      <div
        style={previewStyle}
        dangerouslySetInnerHTML={{ __html: preview }}
      />
    </div>
  );
}
