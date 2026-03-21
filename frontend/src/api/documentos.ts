import { apiFetch } from "./client";
import type { Documento, DocumentoAST } from "./types";

export function listar(): Promise<Documento[]> {
  return apiFetch<Documento[]>("/documentos");
}

export function obtener(id: string): Promise<Documento> {
  return apiFetch<Documento>(`/documentos/${id}`);
}

export function crear(titulo: string, ast: DocumentoAST): Promise<Documento> {
  return apiFetch<Documento>("/documentos", {
    method: "POST",
    body: JSON.stringify({ titulo, ast }),
  });
}

export function actualizar(
  id: string,
  titulo: string,
  ast: DocumentoAST,
): Promise<Documento> {
  return apiFetch<Documento>(`/documentos/${id}`, {
    method: "PUT",
    body: JSON.stringify({ titulo, ast }),
  });
}

export function eliminar(id: string): Promise<void> {
  return apiFetch<void>(`/documentos/${id}`, { method: "DELETE" });
}
