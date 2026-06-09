import type { ReviewItem } from "../api/studyPlan";
import type { SubtopicInfo, TemplateSummary } from "../types";

export function templateUniverseIds(subtopics: SubtopicInfo[] | undefined): Set<number> {
  return new Set(
    (subtopics || []).flatMap((st) => [
      st.id,
      ...(st.variant_children || []).map((variant) => variant.id),
    ]),
  );
}

export function templateUniverseTotal(subtopics: SubtopicInfo[] | undefined): number {
  return subtopics
    ? subtopics.length + subtopics.reduce((sum, st) => sum + (st.variant_children?.length || 0), 0)
    : 0;
}

export function completedTemplateIds(
  templates: TemplateSummary[] | undefined,
  completedItems: ReviewItem[] | undefined,
): Set<number> {
  const ids = new Set<number>();
  for (const template of templates || []) {
    if (template.last_reviewed) ids.add(template.id);
  }
  for (const item of completedItems || []) {
    if (item.review_type === "template" && item.template_id != null && item.last_reviewed) {
      ids.add(item.template_id);
    }
  }
  return ids;
}
