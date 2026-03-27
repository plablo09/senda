import { BlockNoteSchema, defaultBlockSpecs, createCodeBlockSpec } from "@blocknote/core";
import { codeBlockOptions } from "@blocknote/code-block";
import { ejercicioBlockSpec } from "./nodes/EjercicioNode";
import { notaBlockSpec } from "./nodes/NotaNode";
import { cargadorDatosBlockSpec } from "./nodes/CargadorDatosNode";
import { ecuacionBlockSpec } from "./nodes/EcuacionNode";

export const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    codeBlock: createCodeBlockSpec(codeBlockOptions),
    ejercicio: ejercicioBlockSpec(),
    nota: notaBlockSpec(),
    cargadorDatos: cargadorDatosBlockSpec(),
    ecuacion: ecuacionBlockSpec(),
  },
});

export type SchemaDef = typeof schema;
