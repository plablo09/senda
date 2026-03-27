import { useEffect } from "react";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { schema } from "./schema";
import type { Block } from "@blocknote/core";

type SchemaBlock = Block<typeof schema.blockSchema>;

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  initialContent?: any[];
  onChange?: (blocks: SchemaBlock[]) => void;
}

export function SendaEditor({ initialContent, onChange }: Props) {
  const editor = useCreateBlockNote({
    schema,
    initialContent,
  });

  useEffect(() => {
    if (!onChange) return;
    return editor.onChange(() => {
      onChange(editor.document);
    });
  }, [editor, onChange]);

  return <BlockNoteView editor={editor} />;
}
