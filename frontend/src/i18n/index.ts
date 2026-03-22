import es from "./es.json";

type TranslationKey = keyof typeof es;

export function t(key: TranslationKey): string {
  return es[key] ?? key;
}
