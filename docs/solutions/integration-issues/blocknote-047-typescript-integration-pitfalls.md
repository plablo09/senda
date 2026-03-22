---
title: "BlockNote 0.47 + React 19 + Vite 6 Integration Pitfalls"
category: integration-issues
date: 2026-03-21
tags:
  - blocknote
  - react19
  - vite
  - typescript
  - vitest
  - custom-blocks
  - type-generics
  - erasable-syntax
problem_type: api_contract_mismatch
components:
  - frontend/src/editor/schema.ts
  - frontend/src/editor/SendaEditor.tsx
  - frontend/src/editor/nodes/
  - frontend/src/api/client.ts
  - frontend/src/hooks/useRenderStatus.ts
  - frontend/vite.config.ts
  - frontend/tsconfig.app.json
---

# BlockNote 0.47 + React 19 + Vite 6 Integration Pitfalls

Six non-obvious issues surfaced while integrating BlockNote 0.47 into a React 19 / Vite 6 / TypeScript strict project. None produced obvious error messages — most either compiled silently and failed at runtime, or produced misleading type errors that didn't point at the real problem.

**Related plan:** `docs/plans/2026-03-20-002-feat-block-editor-teacher-authoring-plan.md` §"BlockNote Custom Nodes"

---

## Pitfall 1: `createReactBlockSpec` is a factory factory — must be invoked in schema

### Symptom

Custom block specs registered in `BlockNoteSchema.create` were accepted by TypeScript but the schema silently produced wrong behavior at runtime. No type error.

### Root Cause

BlockNote 0.47 changed `createReactBlockSpec(config)` to return a **factory function** `(options?) => BlockSpec`, not a `BlockSpec` value. Passing the factory itself (without calling it) into `blockSpecs` passed TypeScript structural checks but didn't register correctly.

### Fix

Call each spec factory when constructing the schema:

```typescript
// schema.ts
import { ejercicioBlockSpec } from "./nodes/EjercicioNode";
import { notaBlockSpec }      from "./nodes/NotaNode";
import { ecuacionBlockSpec }  from "./nodes/EcuacionNode";
import { cargadorDatosBlockSpec } from "./nodes/CargadorDatosNode";

export const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    ejercicio:     ejercicioBlockSpec(),    // <-- invoke the factory
    nota:          notaBlockSpec(),
    ecuacion:      ecuacionBlockSpec(),
    cargadorDatos: cargadorDatosBlockSpec(),
  },
});
```

Each node file exports the result of `createReactBlockSpec(...)` — which is already the factory — so the consumer calls it.

### Detection

```bash
# Find createReactBlockSpec results used without invocation in schema
grep -rn "createReactBlockSpec" --include="*.ts" --include="*.tsx"
# Verify each result is referenced with () in schema.ts
grep -n "blockSpecs" frontend/src/editor/schema.ts
```

---

## Pitfall 2: `BlockNoteView` moved to `@blocknote/mantine`

### Symptom

```
Module '"@blocknote/react"' has no exported member 'BlockNoteView'.
```

### Root Cause

In BlockNote 0.47, the rendering component was split out of `@blocknote/react` and into renderer-specific packages. The React + Mantine renderer lives in `@blocknote/mantine`.

### Fix

```typescript
// Wrong:
import { BlockNoteView } from "@blocknote/react";

// Correct:
import { BlockNoteView } from "@blocknote/mantine";
```

The `@blocknote/react` package still exists and exports editor hooks (`useCreateBlockNote`), just not the view component.

### Detection

```bash
grep -rn "BlockNoteView\|useBlockNote" --include="*.tsx" --include="*.ts" | grep "@blocknote/react"
```

---

## Pitfall 3: `Block<T>` generic — use `schema.blockSchema`, not `schema`

### Symptom

```typescript
const [blocks, setBlocks] = useState<Block<typeof schema>[]>([]);
// block.type is `unknown` — switch/exhaustive checks don't work
```

No TypeScript error; everything compiles. But `block.type` resolves to `unknown`, breaking type narrowing in switch statements.

### Root Cause

`BlockNoteSchema` is a container object. The `Block<T>` generic expects the **inner block schema record** — accessible as `schema.blockSchema` — not the top-level schema wrapper.

### Fix

```typescript
// Wrong:
Block<typeof schema>

// Correct:
Block<typeof schema.blockSchema>

// Applied in Editor.tsx and SendaEditor.tsx:
const [blocks, setBlocks] = useState<Block<typeof schema.blockSchema>[]>([]);

// Callback types:
function handleBlocksChange(newBlocks: Block<typeof schema.blockSchema>[]) { ... }
```

### Rule of Thumb

If `block.type` is `unknown` in a BlockNote context, the generic parameter is wrong. Always drill into `.blockSchema`.

---

## Pitfall 4: Vitest `defineConfig` must come from `vitest/config`, not `vite`

### Symptom

```
Object literal may only specify known properties, and 'test' does not exist
in type 'UserConfigExport'.
```

### Root Cause

`defineConfig` from `vite` does not include the `test` field in its type signature. Vitest ships its own `defineConfig` in `vitest/config` that extends Vite's config with the `test` field.

### Fix

```typescript
// vite.config.ts — Wrong:
import { defineConfig } from "vite";

// Correct:
import { defineConfig } from "vitest/config";

export default defineConfig({
  // ... vite config ...
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

The Vitest-aware `defineConfig` is a superset — all Vite options still work.

---

## Pitfall 5: `erasableSyntaxOnly` rejects constructor parameter properties

### Symptom

```
Parameter property is not allowed when 'erasableSyntaxOnly' is enabled.
```

Affects any class that uses TypeScript's constructor parameter shorthand:
```typescript
constructor(public status: number) // ← rejected
```

### Root Cause

`erasableSyntaxOnly: true` in `tsconfig.app.json` disallows syntax that emits JavaScript (rather than being erased at type-check time). Constructor parameter properties emit assignment code and are therefore non-erasable.

### Fix

Write the property explicitly:

```typescript
// Wrong:
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// Correct:
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
```

### Detection

```bash
grep -rn "constructor\s*(" --include="*.ts" --include="*.tsx" -A5 \
  | grep -E "(private|public|protected|readonly)\s+\w+"
```

---

## Pitfall 6: Null narrowing is lost inside async closures

### Symptom

TypeScript reports `Type 'string | null' is not assignable to type 'string'` inside a `setInterval` callback, even after a null guard above it.

### Root Cause

TypeScript's control-flow narrowing does not persist across closure boundaries (callbacks, `setInterval`, `setTimeout`, promise chains). Even if `documentoId !== null` is established before the closure, the compiler cannot guarantee it stays non-null inside the callback.

```typescript
// Fails — narrowing doesn't cross the closure boundary:
if (!documentoId) return;
setInterval(() => {
  obtener(documentoId).then(...); // TS error: possibly null
}, 3000);
```

### Fix

Capture the narrowed value to a typed `const` before the closure:

```typescript
if (!documentoId) return;
const docId: string = documentoId; // capture here, narrowed forever

setInterval(() => {
  obtener(docId).then(...); // safe — docId is string, not string | null
}, 3000);
```

This pattern also documents intent: `docId` is the stable ID for this effect's lifetime, regardless of external state changes.

### Rule of Thumb

If a nullable value is needed inside a callback or after an `await`, capture it to a `const` immediately after the null guard, before any async boundary.

---

## Type System Boundary Pattern

When two type systems meet at a single call site (BlockNote's `Block<T>` on one side, a plain-object serializer interface on the other), use a single cast at the boundary rather than trying to unify the types:

```typescript
// Editor.tsx — the ONE place where BlockNote types meet API types
const ast = blockNoteToAST(
  blocks as SerBlock[],          // cast to serializer's interface
  executionUrl
) as DocumentoAST;               // cast result to API type
```

Keep `serializer.ts` testable with plain objects (no BlockNote imports). The test suite runs against `SerBlock[]`, not `Block<typeof schema.blockSchema>[]`.

**Related files:**
- `frontend/src/editor/serializer.ts` — plain-object `Block` interface
- `frontend/src/api/types.ts` — API-level `DocumentoAST`
- `frontend/src/pages/Editor.tsx:226` — the boundary cast

---

## Prevention Checklist

- [ ] All `@blocknote/*` packages pinned to the same patch version in `package.json`
- [ ] `BlockNoteView` imported from `@blocknote/mantine`, not `@blocknote/react`
- [ ] All `Block<T>` generics use `typeof schema.blockSchema`, not `typeof schema`
- [ ] `defineConfig` in `vite.config.ts` imported from `vitest/config`
- [ ] No constructor parameter properties (`public`/`private`/`protected` in ctor args) — use explicit property + assignment
- [ ] Nullable variables captured to typed `const` before any callback or async boundary
