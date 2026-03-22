import { BlockNoteSchema, defaultBlockSpecs } from "@blocknote/core";
import { ejercicioBlockSpec } from "./nodes/EjercicioNode";
import { notaBlockSpec } from "./nodes/NotaNode";
import { cargadorDatosBlockSpec } from "./nodes/CargadorDatosNode";
import { ecuacionBlockSpec } from "./nodes/EcuacionNode";

export const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    ejercicio: ejercicioBlockSpec(),
    nota: notaBlockSpec(),
    cargadorDatos: cargadorDatosBlockSpec(),
    ecuacion: ecuacionBlockSpec(),
  },
});

export type SchemaDef = typeof schema;
