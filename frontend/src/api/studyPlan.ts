import { api } from "./client";
import type {
  SourceImportResponse,
  SourcePost,
  StudyPlan,
  StudyPlanItem,
  TemplateDetail,
  TemplateReview,
  TemplateSummary,
} from "../types";

export function fetchStudyPlan() {
  return api.get<StudyPlan>("/study-plan/today");
}

export function regenerateStudyPlan() {
  return api.post<StudyPlan>("/study-plan/today/regenerate");
}

export function addPatternDrills(count = 5) {
  return api.post<StudyPlan>("/study-plan/today/pattern-drills/add", { count });
}

export function addTemplates(count = 3, subtopicId?: number) {
  return api.post<StudyPlan>("/study-plan/today/templates/add", {
    count,
    subtopic_id: subtopicId,
  });
}

export function skipAndReplaceTemplate(itemId: number) {
  return api.post<StudyPlan>(`/study-plan/items/${itemId}/skip-replace-template`, {});
}

export function updateStudyPlanItem(
  itemId: number,
  data: Partial<Pick<StudyPlanItem, "status" | "pinned" | "notes">>
) {
  return api.patch<{ id: number; status: string; pinned: boolean; notes: string | null }>(
    `/study-plan/items/${itemId}`,
    data
  );
}

export function importStudySource(text: string, title?: string, url?: string) {
  return api.post<SourceImportResponse>("/study-plan/sources/import", {
    text,
    title: title || undefined,
    url: url || undefined,
  });
}

export function scrapeLeetcodeSources(maxResults = 200, maxComments = 20) {
  return api.post<SourceImportResponse>("/study-plan/sources/scrape-leetcode", {
    max_results: maxResults,
    max_comments: maxComments,
  });
}

export function fetchStudySources() {
  return api.get<SourcePost[]>("/study-plan/sources");
}

export interface ReviewItem {
  id: number;
  review_type: "question" | "template" | "pattern_drill";
  question_id: number | null;
  template_id: number | null;
  title: string;
  number: number | null;
  difficulty: string;
  topics: string[];
  subtopics: string[];
  status: string;
  next_review: string | null;
  last_reviewed: string | null;
  repetitions: number;
}

export function fetchAllCompleted() {
  return api.get<{ items: ReviewItem[]; total: number }>("/study-plan/review/all");
}

export function fetchTemplates() {
  return api.get<TemplateSummary[]>("/templates");
}

export function fetchTemplate(templateId: number) {
  return api.get<TemplateDetail>(`/templates/${templateId}`);
}

export function startTemplate(templateId: number) {
  return api.post<{ started: boolean }>(`/templates/${templateId}/start`, {});
}

export function reviewTemplate(templateId: number, quality: number, notes?: string) {
  return api.post<TemplateReview>(`/templates/${templateId}/review`, {
    quality,
    notes: notes || undefined,
  });
}
