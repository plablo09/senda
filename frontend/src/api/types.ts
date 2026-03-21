export type EstadoRender = "pendiente" | "procesando" | "listo" | "fallido";

export interface DocumentoAST {
  execution_url: string;
  blocks: ASTBlock[];
}

export type ASTBlock =
  | { type: "text"; text: string }
  | { type: "exercise"; attrs: ExerciseAttrs }
  | { type: "nota"; attrs: NotaAttrs }
  | { type: "ecuacion"; attrs: EcuacionAttrs }
  | { type: "cargadorDatos"; attrs: CargadorDatosAttrs };

export interface ExerciseAttrs {
  language: "python" | "r";
  exerciseId: string;
  caption: string;
  starterCode: string;
  solutionCode: string;
  hints: string[];
}

export interface NotaAttrs {
  nivel: "note" | "tip" | "warning" | "important";
  titulo: string;
  contenido: string;
}

export interface EcuacionAttrs {
  latex: string;
  modo: "bloque" | "linea";
}

export interface CargadorDatosAttrs {
  datasetId: string;
  filename: string;
  url: string;
  mimetype: string;
  language: "python" | "r";
  variableName: string;
}

export interface Documento {
  id: string;
  titulo: string;
  ast: DocumentoAST | null;
  qmd_source: string | null;
  estado_render: EstadoRender;
  url_artefacto: string | null;
  error_render: string | null;
  created_at: string;
  updated_at: string;
}

export interface Dataset {
  id: string;
  filename: string;
  url: string;
  mimetype: string;
  es_publico: boolean;
  created_at: string;
}
