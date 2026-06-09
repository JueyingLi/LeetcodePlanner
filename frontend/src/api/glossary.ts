import { api } from "./client";
import type { GlossaryTerm } from "../types";

export function fetchGlossaryTerm(term: string) {
  return api.get<GlossaryTerm>(`/glossary?term=${encodeURIComponent(term)}`);
}
