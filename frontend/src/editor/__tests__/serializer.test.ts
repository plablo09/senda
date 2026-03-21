import { describe, it, expect } from "vitest";
import { blockNoteToAST } from "../serializer";

// Minimal block shapes matching the serializer's Block interface
// (no BlockNote imports — plain objects only)

describe("blockNoteToAST", () => {
  it("empty blocks → empty blocks array with execution_url", () => {
    const result = blockNoteToAST([], "https://exec.example.com");
    expect(result).toEqual({
      execution_url: "https://exec.example.com",
      blocks: [],
    });
  });

  it("paragraph block → text block", () => {
    const blocks = [
      {
        type: "paragraph",
        props: {},
        content: [{ type: "text", text: "Hello world" }],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([{ type: "text", text: "Hello world" }]);
  });

  it("heading level 2 → ## prefix", () => {
    const blocks = [
      {
        type: "heading",
        props: { level: 2 },
        content: [{ type: "text", text: "My Heading" }],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([{ type: "text", text: "## My Heading" }]);
  });

  it("heading level 3 → ### prefix", () => {
    const blocks = [
      {
        type: "heading",
        props: { level: 3 },
        content: [{ type: "text", text: "Sub Heading" }],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([{ type: "text", text: "### Sub Heading" }]);
  });

  it("heading level 1 → # prefix", () => {
    const blocks = [
      {
        type: "heading",
        props: { level: 1 },
        content: [{ type: "text", text: "Title" }],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([{ type: "text", text: "# Title" }]);
  });

  it("paragraph with multiple inline segments → joined text", () => {
    const blocks = [
      {
        type: "paragraph",
        props: {},
        content: [
          { type: "text", text: "Hello " },
          { type: "text", text: "world" },
        ],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([{ type: "text", text: "Hello world" }]);
  });

  it("ejercicio block → exercise attrs", () => {
    const blocks = [
      {
        type: "ejercicio",
        props: {
          exerciseId: "ex-123",
          language: "python",
          caption: "My Exercise",
          starterCode: "x = 1",
          solutionCode: "x = 42",
          hints: '["Hint one", "Hint two"]',
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([
      {
        type: "exercise",
        attrs: {
          exerciseId: "ex-123",
          language: "python",
          caption: "My Exercise",
          starterCode: "x = 1",
          solutionCode: "x = 42",
          hints: ["Hint one", "Hint two"],
        },
      },
    ]);
  });

  it("ejercicio hints JSON string → string[]", () => {
    const blocks = [
      {
        type: "ejercicio",
        props: {
          exerciseId: "ex-abc",
          language: "javascript",
          caption: "",
          starterCode: "",
          solutionCode: "",
          hints: '["First hint", "Second hint", "Third hint"]',
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    const exerciseBlock = result.blocks[0];
    expect(exerciseBlock.type).toBe("exercise");
    if (exerciseBlock.type === "exercise") {
      expect(exerciseBlock.attrs.hints).toEqual([
        "First hint",
        "Second hint",
        "Third hint",
      ]);
    }
  });

  it("ejercicio with empty hints string → empty array", () => {
    const blocks = [
      {
        type: "ejercicio",
        props: {
          exerciseId: "ex-xyz",
          language: "python",
          caption: "",
          starterCode: "",
          solutionCode: "",
          hints: "[]",
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    const exerciseBlock = result.blocks[0];
    expect(exerciseBlock.type).toBe("exercise");
    if (exerciseBlock.type === "exercise") {
      expect(exerciseBlock.attrs.hints).toEqual([]);
    }
  });

  it("ejercicio with empty exerciseId → generated UUID", () => {
    const blocks = [
      {
        type: "ejercicio",
        props: {
          exerciseId: "",
          language: "python",
          caption: "",
          starterCode: "",
          solutionCode: "",
          hints: "[]",
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    const exerciseBlock = result.blocks[0];
    expect(exerciseBlock.type).toBe("exercise");
    if (exerciseBlock.type === "exercise") {
      expect(exerciseBlock.attrs.exerciseId).toBeTruthy();
      expect(exerciseBlock.attrs.exerciseId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
      );
    }
  });

  it("nota block → nota attrs", () => {
    const blocks = [
      {
        type: "nota",
        props: {
          nivel: "tip",
          titulo: "Important Note",
          contenido: "This is the note body.",
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([
      {
        type: "nota",
        attrs: {
          nivel: "tip",
          titulo: "Important Note",
          contenido: "This is the note body.",
        },
      },
    ]);
  });

  it("ecuacion block → ecuacion attrs", () => {
    const blocks = [
      {
        type: "ecuacion",
        props: {
          latex: "E = mc^2",
          modo: "bloque",
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([
      {
        type: "ecuacion",
        attrs: {
          latex: "E = mc^2",
          modo: "bloque",
        },
      },
    ]);
  });

  it("cargadorDatos block → cargadorDatos attrs", () => {
    const blocks = [
      {
        type: "cargadorDatos",
        props: {
          url: "https://data.example.com/dataset.csv",
          filename: "dataset.csv",
          mimetype: "text/csv",
          language: "python",
          variableName: "datos",
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toEqual([
      {
        type: "cargadorDatos",
        attrs: {
          url: "https://data.example.com/dataset.csv",
          filename: "dataset.csv",
          mimetype: "text/csv",
          language: "python",
          variableName: "datos",
        },
      },
    ]);
  });

  it("unknown block types are skipped", () => {
    const blocks = [
      {
        type: "unknownCustomBlock",
        props: { foo: "bar" },
        content: [],
      },
      {
        type: "paragraph",
        props: {},
        content: [{ type: "text", text: "Keep me" }],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toHaveLength(1);
    expect(result.blocks[0]).toEqual({ type: "text", text: "Keep me" });
  });

  it("mixed blocks → correct order in output", () => {
    const blocks = [
      {
        type: "heading",
        props: { level: 1 },
        content: [{ type: "text", text: "Chapter 1" }],
      },
      {
        type: "paragraph",
        props: {},
        content: [{ type: "text", text: "Intro text." }],
      },
      {
        type: "nota",
        props: {
          nivel: "warning",
          titulo: "Watch out",
          contenido: "Be careful.",
        },
        content: [],
      },
      {
        type: "ecuacion",
        props: { latex: "x^2", modo: "inline" },
        content: [],
      },
      {
        type: "ejercicio",
        props: {
          exerciseId: "ex-001",
          language: "python",
          caption: "Exercise 1",
          starterCode: "pass",
          solutionCode: "print(42)",
          hints: '["Think carefully"]',
        },
        content: [],
      },
    ];
    const result = blockNoteToAST(blocks, "https://exec.example.com");
    expect(result.blocks).toHaveLength(5);
    expect(result.blocks[0]).toEqual({ type: "text", text: "# Chapter 1" });
    expect(result.blocks[1]).toEqual({ type: "text", text: "Intro text." });
    expect(result.blocks[2]).toEqual({
      type: "nota",
      attrs: { nivel: "warning", titulo: "Watch out", contenido: "Be careful." },
    });
    expect(result.blocks[3]).toEqual({
      type: "ecuacion",
      attrs: { latex: "x^2", modo: "inline" },
    });
    expect(result.blocks[4]).toEqual({
      type: "exercise",
      attrs: {
        exerciseId: "ex-001",
        language: "python",
        caption: "Exercise 1",
        starterCode: "pass",
        solutionCode: "print(42)",
        hints: ["Think carefully"],
      },
    });
  });
});
