// Serializer: converts BlockNote Block[] to the AST payload the Python backend expects.

interface InlineContent {
  type: string;
  text?: string;
}

interface Block {
  type: string;
  props: Record<string, unknown>;
  content?: InlineContent[];
}

// --- AST block types ---

interface TextASTBlock {
  type: "text";
  text: string;
}

interface ExerciseASTBlock {
  type: "exercise";
  attrs: {
    exerciseId: string;
    language: string;
    caption: string;
    starterCode: string;
    solutionCode: string;
    hints: string[];
  };
}

interface NotaASTBlock {
  type: "nota";
  attrs: {
    nivel: string;
    titulo: string;
    contenido: string;
  };
}

interface EcuacionASTBlock {
  type: "ecuacion";
  attrs: {
    latex: string;
    modo: string;
  };
}

interface CargadorDatosASTBlock {
  type: "cargadorDatos";
  attrs: {
    url: string;
    filename: string;
    mimetype: string;
    language: string;
    variableName: string;
  };
}

type ASTBlock =
  | TextASTBlock
  | ExerciseASTBlock
  | NotaASTBlock
  | EcuacionASTBlock
  | CargadorDatosASTBlock;

interface DocumentAST {
  execution_url: string;
  blocks: ASTBlock[];
}

// --- Helpers ---

function joinInlineContent(content: InlineContent[] | undefined): string {
  if (!content) return "";
  return content
    .filter((item) => item.type === "text" && item.text !== undefined)
    .map((item) => item.text ?? "")
    .join("");
}

function parseHints(hintsRaw: unknown): string[] {
  if (typeof hintsRaw !== "string") return [];
  try {
    const parsed: unknown = JSON.parse(hintsRaw);
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
}

function serializeBlock(block: Block): ASTBlock | null {
  switch (block.type) {
    case "paragraph": {
      const text = joinInlineContent(block.content);
      return { type: "text", text };
    }

    case "heading": {
      const level = typeof block.props.level === "number" ? block.props.level : 1;
      const prefix = "#".repeat(level) + " ";
      const text = prefix + joinInlineContent(block.content);
      return { type: "text", text };
    }

    case "ejercicio": {
      const {
        exerciseId: rawId,
        language,
        caption,
        starterCode,
        solutionCode,
        hints: hintsRaw,
      } = block.props;

      const exerciseId =
        typeof rawId === "string" && rawId.length > 0
          ? rawId
          : crypto.randomUUID();

      return {
        type: "exercise",
        attrs: {
          exerciseId,
          language: typeof language === "string" ? language : "python",
          caption: typeof caption === "string" ? caption : "",
          starterCode: typeof starterCode === "string" ? starterCode : "",
          solutionCode: typeof solutionCode === "string" ? solutionCode : "",
          hints: parseHints(hintsRaw),
        },
      };
    }

    case "nota": {
      const { nivel, titulo, contenido } = block.props;
      return {
        type: "nota",
        attrs: {
          nivel: typeof nivel === "string" ? nivel : "",
          titulo: typeof titulo === "string" ? titulo : "",
          contenido: typeof contenido === "string" ? contenido : "",
        },
      };
    }

    case "ecuacion": {
      const { latex, modo } = block.props;
      return {
        type: "ecuacion",
        attrs: {
          latex: typeof latex === "string" ? latex : "",
          modo: typeof modo === "string" ? modo : "bloque",
        },
      };
    }

    case "cargadorDatos": {
      const { url, filename, mimetype, language, variableName } = block.props;
      return {
        type: "cargadorDatos",
        attrs: {
          url: typeof url === "string" ? url : "",
          filename: typeof filename === "string" ? filename : "",
          mimetype: typeof mimetype === "string" ? mimetype : "",
          language: typeof language === "string" ? language : "python",
          variableName: typeof variableName === "string" ? variableName : "datos",
        },
      };
    }

    default:
      return null;
  }
}

/**
 * Converts a BlockNote Block[] to the DocumentAST payload expected by the Python backend.
 *
 * @param blocks - Array of BlockNote blocks (or plain mock shapes in tests)
 * @param executionUrl - The kernel execution URL to embed in the AST
 */
export function blockNoteToAST(
  blocks: Block[],
  executionUrl: string
): DocumentAST {
  const astBlocks: ASTBlock[] = blocks
    .map(serializeBlock)
    .filter((b): b is ASTBlock => b !== null);

  return {
    execution_url: executionUrl,
    blocks: astBlocks,
  };
}

export type {
  Block,
  InlineContent,
  DocumentAST,
  ASTBlock,
  TextASTBlock,
  ExerciseASTBlock,
  NotaASTBlock,
  EcuacionASTBlock,
  CargadorDatosASTBlock,
};
