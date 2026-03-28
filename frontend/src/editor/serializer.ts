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
    language: "python" | "r";
    caption: string;
    starterCode: string;
    solutionCode: string;
    hints: string[];
  };
}

interface NotaASTBlock {
  type: "nota";
  attrs: {
    nivel: "note" | "tip" | "warning" | "important";
    titulo: string;
    contenido: string;
  };
}

interface EcuacionASTBlock {
  type: "ecuacion";
  attrs: {
    latex: string;
    modo: "bloque" | "linea";
  };
}

interface CargadorDatosASTBlock {
  type: "cargadorDatos";
  attrs: {
    datasetId: string;
    url: string;
    filename: string;
    mimetype: string;
    language: "python" | "r";
    variableName: string;
  };
}

interface CodeASTBlock {
  type: "code";
  attrs: {
    language: string;
    content: string;
  };
}

type ASTBlock =
  | TextASTBlock
  | ExerciseASTBlock
  | NotaASTBlock
  | EcuacionASTBlock
  | CargadorDatosASTBlock
  | CodeASTBlock;

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

      const lang: "python" | "r" =
        language === "r" ? "r" : "python";
      return {
        type: "exercise",
        attrs: {
          exerciseId,
          language: lang,
          caption: typeof caption === "string" ? caption : "",
          starterCode: typeof starterCode === "string" ? starterCode : "",
          solutionCode: typeof solutionCode === "string" ? solutionCode : "",
          hints: parseHints(hintsRaw),
        },
      };
    }

    case "nota": {
      const { nivel, titulo, contenido } = block.props;
      const notaNivel: "note" | "tip" | "warning" | "important" =
        nivel === "tip" ? "tip" : nivel === "warning" ? "warning" : nivel === "important" ? "important" : "note";
      return {
        type: "nota",
        attrs: {
          nivel: notaNivel,
          titulo: typeof titulo === "string" ? titulo : "",
          contenido: typeof contenido === "string" ? contenido : "",
        },
      };
    }

    case "ecuacion": {
      const { latex, modo } = block.props;
      const ecuacionModo: "bloque" | "linea" = modo === "linea" ? "linea" : "bloque";
      return {
        type: "ecuacion",
        attrs: {
          latex: typeof latex === "string" ? latex : "",
          modo: ecuacionModo,
        },
      };
    }

    case "cargadorDatos": {
      const { datasetId, url, filename, mimetype, language, variableName } = block.props;
      const cargLang: "python" | "r" = language === "r" ? "r" : "python";
      return {
        type: "cargadorDatos",
        attrs: {
          datasetId: typeof datasetId === "string" ? datasetId : "",
          url: typeof url === "string" ? url : "",
          filename: typeof filename === "string" ? filename : "",
          mimetype: typeof mimetype === "string" ? mimetype : "",
          language: cargLang,
          variableName: typeof variableName === "string" ? variableName : "datos",
        },
      };
    }

    case "codeBlock": {
      const { language, content } = block.props;
      return {
        type: "code",
        attrs: {
          language: typeof language === "string" ? language : "python",
          content: typeof content === "string" ? content : "",
        },
      };
    }

    default:
      return null;
  }
}

// Loose type for BlockNote partial blocks returned to the editor.
// BlockNote's PartialBlock<BSchema,...> is deeply generic; using Record avoids
// threading schema type params through the serializer.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type PartialEditorBlock = Record<string, any>;

function astBlockToEditorBlock(block: ASTBlock): PartialEditorBlock | null {
  switch (block.type) {
    case "text": {
      const headingMatch = block.text.match(/^(#{1,6}) (.*)$/);
      if (headingMatch) {
        return {
          type: "heading",
          props: { level: headingMatch[1].length },
          content: [{ type: "text", text: headingMatch[2], styles: {} }],
        };
      }
      return {
        type: "paragraph",
        content: block.text ? [{ type: "text", text: block.text, styles: {} }] : [],
      };
    }
    case "exercise":
      return {
        type: "ejercicio",
        props: {
          exerciseId: block.attrs.exerciseId,
          language: block.attrs.language,
          caption: block.attrs.caption,
          starterCode: block.attrs.starterCode,
          solutionCode: block.attrs.solutionCode,
          hints: JSON.stringify(block.attrs.hints),
        },
      };
    case "nota":
      return { type: "nota", props: { ...block.attrs } };
    case "ecuacion":
      return { type: "ecuacion", props: { ...block.attrs } };
    case "cargadorDatos":
      return { type: "cargadorDatos", props: { ...block.attrs } };
    case "code":
      return { type: "codeBlock", props: { ...block.attrs } };
    default:
      return null;
  }
}

/**
 * Converts a DocumentAST (from the backend) back into BlockNote-compatible partial blocks
 * for use as initialContent in useCreateBlockNote.
 */
export function astToBlockNote(ast: DocumentAST): PartialEditorBlock[] {
  return ast.blocks
    .map(astBlockToEditorBlock)
    .filter((b): b is PartialEditorBlock => b !== null);
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
