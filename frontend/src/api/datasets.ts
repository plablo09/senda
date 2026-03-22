import type { Dataset } from "./types";

const BASE = "/api";

export async function listar(): Promise<Dataset[]> {
  const res = await fetch(`${BASE}/datasets`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<Dataset[]>;
}

export async function subir(file: File): Promise<Dataset> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/datasets`, {
    method: "POST",
    body: form,
    // Do NOT set Content-Type — browser sets it with boundary for multipart
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }
  return res.json() as Promise<Dataset>;
}

export async function eliminar(id: string): Promise<void> {
  const res = await fetch(`${BASE}/datasets/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
}
