import { api } from "./client";
import type { SubtopicInfo, Question } from "../types";

export function fetchSubtopics(category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  return api.get<SubtopicInfo[]>(`/subtopics${qs}`);
}

export function fetchSubtopic(id: number) {
  return api.get<SubtopicInfo>(`/subtopics/${id}`);
}

export function fetchSubtopicCategories() {
  return api.get<string[]>("/subtopics/categories");
}

export function fetchSubtopicNames() {
  return api.get<string[]>("/subtopics/names");
}

export function fetchSubtopicQuestions(subtopicId: number) {
  return api.get<Question[]>(`/subtopics/${subtopicId}/questions`);
}

export function createSubtopic(data: {
  name: string;
  category: string;
  description?: string;
  when_to_use?: string;
  key_signals?: string;
}) {
  return api.post<SubtopicInfo>("/subtopics", data);
}

export function updateSubtopic(id: number, data: Partial<SubtopicInfo>) {
  return api.put<SubtopicInfo>(`/subtopics/${id}`, data);
}

export function deleteSubtopic(id: number) {
  return api.delete(`/subtopics/${id}`);
}

export function generateSubtopicDescriptions() {
  return api.post<{ updated: number; message?: string }>("/subtopics/generate-descriptions", {});
}

export function regenerateSubtopicDescription(subtopicId: number) {
  return api.post<SubtopicInfo>(`/subtopics/${subtopicId}/regenerate-description`, {});
}

export function rebuildTaxonomy() {
  return api.post<{ subtopics_created: number; questions_remapped: number }>("/subtopics/rebuild-taxonomy", {});
}

export function fetchTopicOrder() {
  return api.get<string[]>("/subtopics/topic-order");
}

export function findAndAddQuestions(subtopicId: number, count = 3) {
  return api.post<{
    added: { question_id: number; title: string; existed: boolean }[];
    errors: { number: number; title: string; error: string }[];
    subtopic: string;
  }>(`/subtopics/${subtopicId}/find-and-add-questions?count=${count}`, {});
}

export function fetchSubtopicVariants(subtopicId: number) {
  return api.get<SubtopicInfo[]>(`/subtopics/${subtopicId}/variants`);
}

export function generateVariant(subtopicId: number, variantName: string) {
  return api.post<SubtopicInfo>(`/subtopics/${subtopicId}/generate-variant`, {
    variant_name: variantName,
  });
}
