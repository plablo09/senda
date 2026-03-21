import { useState, useEffect, type CSSProperties, type ChangeEvent } from "react";
import { createReactBlockSpec } from "@blocknote/react";
import { t } from "../../i18n";
import { listar, subir } from "../../api/datasets";
import type { Dataset } from "../../api/types";

export const cargadorDatosBlockSpec = createReactBlockSpec(
  {
    type: "cargadorDatos" as const,
    propSchema: {
      datasetId: { default: "" },
      filename: { default: "" },
      url: { default: "" },
      mimetype: { default: "text/csv" },
      language: { default: "python" as const },
      variableName: { default: "datos" },
    },
    content: "none",
  },
  {
    render: ({ block, editor }) => {
      const {
        datasetId,
        filename,
        url,
        mimetype,
        language,
        variableName,
      } = block.props;

      return (
        <CargadorDatosUI
          datasetId={datasetId}
          filename={filename}
          url={url}
          mimetype={mimetype}
          language={language}
          variableName={variableName}
          onDatasetChange={(d) =>
            editor.updateBlock(block, {
              props: {
                datasetId: d.id,
                filename: d.filename,
                url: d.url,
                mimetype: d.mimetype,
              },
            })
          }
          onLanguageChange={(val) =>
            editor.updateBlock(block, { props: { language: val } })
          }
          onVariableNameChange={(val) =>
            editor.updateBlock(block, { props: { variableName: val } })
          }
        />
      );
    },
  }
);

interface CargadorDatosUIProps {
  datasetId: string;
  filename: string;
  url: string;
  mimetype: string;
  language: string;
  variableName: string;
  onDatasetChange: (d: Dataset) => void;
  onLanguageChange: (val: "python" | "r") => void;
  onVariableNameChange: (val: string) => void;
}

function CargadorDatosUI({
  datasetId,
  filename,
  url: _url,
  mimetype: _mimetype,
  language,
  variableName,
  onDatasetChange,
  onLanguageChange,
  onVariableNameChange,
}: CargadorDatosUIProps) {
  const [mode, setMode] = useState<"subir" | "seleccionar">("subir");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showChange, setShowChange] = useState(false);

  useEffect(() => {
    listar()
      .then(setDatasets)
      .catch(() => {
        // silently fail — datasets list just stays empty
      });
  }, []);

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
    background: "white",
  };

  const selectStyle: CSSProperties = { ...inputStyle };

  const tabStyle = (active: boolean): CSSProperties => ({
    padding: "6px 14px",
    fontSize: "13px",
    cursor: "pointer",
    borderRadius: "4px 4px 0 0",
    border: "1px solid #d1d5db",
    borderBottom: active ? "1px solid #f9fafb" : "1px solid #d1d5db",
    background: active ? "#f9fafb" : "#e5e7eb",
    fontWeight: active ? 600 : 400,
    marginRight: "4px",
  });

  const hasDataset = datasetId.length > 0;

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploading(true);
    try {
      const dataset = await subir(file);
      onDatasetChange(dataset);
      setShowChange(false);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  };

  const handleSelectChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const selected = datasets.find((d) => d.id === e.target.value);
    if (selected) {
      onDatasetChange(selected);
    }
  };

  return (
    <div style={containerStyle}>
      <div style={{ marginBottom: "12px" }}>
        <button
          type="button"
          style={tabStyle(mode === "subir")}
          onClick={() => setMode("subir")}
        >
          {t("cargador.modo.subir")}
        </button>
        <button
          type="button"
          style={tabStyle(mode === "seleccionar")}
          onClick={() => setMode("seleccionar")}
        >
          {t("cargador.modo.seleccionar")}
        </button>
      </div>

      {mode === "subir" && (
        <div>
          {hasDataset && !showChange ? (
            <div style={{ fontSize: "14px", color: "#374151" }}>
              <span>{t("cargador.archivo_actual")} </span>
              <strong>{filename}</strong>
              <button
                type="button"
                style={{
                  marginLeft: "8px",
                  background: "none",
                  border: "none",
                  color: "#3b82f6",
                  cursor: "pointer",
                  fontSize: "14px",
                  textDecoration: "underline",
                  padding: 0,
                }}
                onClick={() => setShowChange(true)}
              >
                {t("cargador.cambiar")}
              </button>
            </div>
          ) : (
            <div>
              <label style={{ ...labelStyle, marginTop: 0 }}>
                {t("cargador.subir_archivo")}
              </label>
              <input
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                disabled={uploading}
                style={{ fontSize: "14px" }}
              />
              {uploading && (
                <span
                  style={{ fontSize: "13px", color: "#6b7280", marginLeft: "8px" }}
                >
                  {t("cargador.subiendo")}
                </span>
              )}
              {uploadError && (
                <div style={{ color: "#ef4444", fontSize: "13px", marginTop: "4px" }}>
                  {uploadError}
                </div>
              )}
              <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "4px" }}>
                {t("cargador.formatos_aceptados")}
              </div>
            </div>
          )}
        </div>
      )}

      {mode === "seleccionar" && (
        <div>
          {datasets.length === 0 ? (
            <div style={{ fontSize: "14px", color: "#6b7280" }}>
              {t("cargador.sin_datasets")}
            </div>
          ) : (
            <div>
              <select
                style={selectStyle}
                value={datasetId}
                onChange={handleSelectChange}
              >
                <option value="">{t("cargador.sin_archivo")}</option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      <label style={labelStyle}>{t("cargador.variable_nombre")}</label>
      <input
        style={inputStyle}
        type="text"
        value={variableName}
        onChange={(e) => onVariableNameChange(e.target.value)}
      />

      <label style={labelStyle}>{t("cargador.language")}</label>
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
    </div>
  );
}
