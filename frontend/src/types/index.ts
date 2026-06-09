export type Difficulty = "Easy" | "Medium" | "Hard";
export type Status = "todo" | "in_progress" | "done" | "review" | "rework";
export type QuizType =
  | "multiple_choice"
  | "ordering"
  | "code_completion"
  | "observation_match";
export type QuizFocus =
  | "input_output"
  | "pattern_recognition"
  | "approach_reasoning"
  | "code_implementation"
  | "edge_cases"
  | "complexity"
  | "full_flow";

export interface SourceTag {
  name: string;
  type: string;
}

export interface ExampleItem {
  input: string;
  output: string;
  explanation: string;
}

export interface GlossaryTerm {
  name: string;
  definition: string;
  how_it_works: string;
  example: string;
}

export type ApproachCategory = "data_structure" | "algorithm" | "optimization" | string;

export interface CodeStep {
  code: string;
  explanation: string;
}

export interface ApproachStep {
  label: string;
  category: ApproachCategory;
  why: string;
  code_steps: CodeStep[];
}

export interface DrillQuestion {
  question: string;
  answer: string;
  wrong_options: string[];
  approach_label: string;
}

export interface PatternAnalysis {
  scenario?: string;
  example?: string;
  data_characteristics: string;
  goal: string;
  constraint_signals: string[];
  approaches: ApproachStep[];
  questions: DrillQuestion[];
}

export interface DrillCard {
  id: number;
  number: number | null;
  title: string;
  difficulty: Difficulty;
  topics: string[];
  subtopics: string[];
  pattern_analysis: PatternAnalysis | null;
  completed: boolean;
}

export interface Question {
  id: number;
  number: number | null;
  title: string;
  difficulty: Difficulty;
  topics: string[];
  subtopics: string[];
  frequency: number;
  sources: SourceTag[];
  url: string | null;
  description: string | null;
  examples: ExampleItem[] | null;
  notes: string | null;
  status: Status;
  created_at: string;
  updated_at: string;
  solution_count: number;
  has_progress: boolean;
}

export interface QuestionListResponse {
  items: Question[];
  total: number;
}

export interface EdgeCase {
  case: string;
  reasoning: string;
  how_handled: string;
}

export interface Solution {
  id: number;
  question_id: number;
  approach_name: string;
  initial_observation: string;
  approach_reasoning: string;
  step_by_step: string;
  edge_cases: EdgeCase[];
  time_complexity: string;
  space_complexity: string;
  code: string;
  fill_in_code: string;
  is_optimal: boolean;
  sort_order: number;
  llm_provider: string | null;
  llm_model: string | null;
  generated_at: string | null;
  created_at: string;
}

export interface QuizAttempt {
  id: number;
  question_id: number;
  quiz_type: QuizType;
  quiz_focus: QuizFocus;
  quiz_data: {
    prompt: string;
    options: string[] | null;
    explanation: string;
    prior_steps_summary: string | null;
    question_title: string | null;
    question_number: number | null;
    question_description: string | null;
  };
  user_answer: string | null;
  correct_answer: string;
  is_correct: boolean | null;
  time_spent_seconds: number | null;
  created_at: string;
}

export interface DailyPlanItem {
  question_id: number;
  question_title: string;
  question_number: number | null;
  difficulty: string;
  topics: string[];
  status: string;
  reason: string;
  next_review: string | null;
  has_solutions: boolean;
}

export interface DailyPlan {
  date: string;
  items: DailyPlanItem[];
  review_count: number;
  new_count: number;
  days_until_interview: number;
  hours_until_interview: number;
  minutes_until_interview: number;
  missing_solutions_count: number;
}

export interface ApiKeyInfo {
  provider: string;
  model: string;
  is_active: boolean;
  api_key_masked: string;
}

export interface StudyPreferences {
  review_count: number;
  template_count: number;
  google_count: number;
  hard_count: number;
  pattern_count: number;
  daily_refresh_hour: number;
  timezone_offset: number;
}

export interface QuizStats {
  total_attempts: number;
  correct_count: number;
  accuracy: number;
  by_topic: Record<string, Record<string, number>>;
  by_focus: Record<string, Record<string, number>>;
  weak_topics: string[];
}

export interface WeaknessInfo {
  topic: string;
  subtopic: string | null;
  attempts: number;
  correct: number;
  accuracy: number;
}

export interface TemplateSummary {
  id: number;
  slug: string;
  title: string;
  topic: string;
  subtopic: string | null;
  when_to_use: string;
  signals: string[];
  last_reviewed: string | null;
  next_review: string | null;
}

export interface TemplateDetail extends TemplateSummary {
  core_code: string;
  breakdown: string;
  mental_model: string;
  variants: string;
  pitfalls: string;
  recall_tasks: string[];
  related_question_ids: number[];
}

export interface TemplateReview {
  template_id: number;
  quality_history: number[];
  last_reviewed: string | null;
  next_review: string | null;
  notes: string | null;
}

export interface StudyPlanItem {
  id: number;
  item_type: "question" | "template" | "reflection" | string;
  question_id: number | null;
  template_id: number | null;
  title: string;
  reason: string;
  priority: number;
  status: "not_started" | "in_progress" | "completed" | "skipped" | string;
  pinned: boolean;
  manual: boolean;
  estimated_minutes: number;
  sort_order: number;
  notes: string | null;
  metadata: Record<string, unknown>;
  template: TemplateDetail | null;
}

export interface StudyPlanSession {
  id: number;
  session_type: string;
  title: string;
  description: string | null;
  sort_order: number;
  estimated_minutes: number;
  items: StudyPlanItem[];
}

export interface StudyPlan {
  id: number;
  date: string;
  interview_target: string;
  status: string;
  generated_at: string;
  updated_at: string;
  regenerated_count: number;
  days_until_interview: number;
  hours_until_interview: number;
  minutes_until_interview: number;
  summary: Record<string, unknown>;
  markdown_snapshot: string;
  sessions: StudyPlanSession[];
}

export interface SourcePost {
  id: number;
  source_type: string;
  uuid: string | null;
  topic_id: number | null;
  slug: string | null;
  title: string;
  url: string | null;
  summary: string | null;
  full_text_preview: string | null;
  created_at_from_source: string | null;
  updated_at_from_source: string | null;
  hit_count: number | null;
  comment_count: number | null;
  score: number;
  extracted_questions: string[];
  imported_at: string;
}

export interface SourceImportResponse {
  posts_added: number;
  posts_updated: number;
  questions_added: number;
  questions_updated: number;
  questions_skipped: number;
  posts: SourcePost[];
}

export interface UserAttempt {
  id: number;
  question_id: number;
  observation: string | null;
  approach: string | null;
  code: string | null;
  time_complexity: string | null;
  space_complexity: string | null;
  ai_feedback: Record<string, StepFeedback> | null;
  created_at: string;
  updated_at: string;
}

export interface StepFeedback {
  step: string;
  feedback: string;
  score: number | null;
  suggestions: string[];
}

export interface SubtopicVariantSummary {
  id: number;
  name: string;
  slug: string | null;
}

export interface SubtopicInfo {
  id: number;
  name: string;
  slug: string | null;
  category: string;
  parent_id: number | null;
  parent_name: string | null;
  description: string | null;
  when_to_use: string | null;
  key_signals: string | null;
  signals: string[] | null;
  variants: string | null;
  implementation_keys: string | null;
  common_pitfalls: string | null;
  core_code: string | null;
  breakdown: string | null;
  mental_model: string | null;
  recall_tasks: string[] | null;
  related_question_ids: number[] | null;
  comparison_same: string | null;
  comparison_different: string | null;
  comparison_when: string | null;
  comparison_code: string | null;
  variant_children: SubtopicVariantSummary[] | null;
  question_count: number;
  created_at: string;
  updated_at: string;
}

export type ReviewQuizFormat =
  | "scenario_match"
  | "signal_recognition"
  | "code_repair"
  | "drill_recall"
  | "when_to_use"
  | "approach_select"
  | "mistake_retry";

export type ReviewQuizSourceType =
  | "question"
  | "template"
  | "pattern_drill"
  | "code_mistake"
  | "quiz";

export interface ReviewQuizItem {
  id: number;
  quiz_format: ReviewQuizFormat;
  source_type: ReviewQuizSourceType;
  source_id: number;
  replaces_quiz_id: number | null;
  prompt: string;
  options: string[] | null;
  correct_answer: string;
  explanation: string | null;
  user_answer: string | null;
  is_correct: boolean | null;
  time_spent_seconds: number | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface ReviewQuizStats {
  total: number;
  correct: number;
  accuracy: number;
  by_format: Record<string, { total: number; correct: number; accuracy: number }>;
}
