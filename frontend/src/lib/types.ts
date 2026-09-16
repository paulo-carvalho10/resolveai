/** Shapes returned by the API (see /docs for the OpenAPI schema). */

export type Role = "ADMIN" | "AGENT" | "USER";
export type TicketStatus = "OPEN" | "IN_PROGRESS" | "WAITING_USER" | "RESOLVED" | "CLOSED";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type SlaStatus = "ON_TRACK" | "AT_RISK" | "BREACHED" | "MET";
export type ArticleStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";
export type IndexStatus = "PENDING" | "INDEXED" | "FAILED";
export type AnalysisStatus = "SUCCEEDED" | "FAILED";

export type NamedRef = { id: number; name: string };
export type UserSummary = { id: number; full_name: string; email: string };

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type User = {
  id: number;
  organization_id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
};

export type Ticket = {
  id: number;
  title: string;
  description: string;
  status: TicketStatus;
  priority: Priority;
  category: NamedRef | null;
  subcategory: NamedRef | null;
  team: NamedRef | null;
  requester: UserSummary;
  assignee: UserSummary | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  resolved_by: UserSummary | null;
  ai_category: NamedRef | null;
  ai_subcategory: NamedRef | null;
  ai_team: NamedRef | null;
  ai_priority: Priority | null;
  ai_confidence: number | null;
  ai_summary: string | null;
  ai_analyzed_at: string | null;
  sla_due_at: string;
  sla_status: SlaStatus;
  /** When the system closes the ticket if nobody does. Only while resolved. */
  auto_close_at: string | null;
};

export type TicketMessage = {
  id: number;
  ticket_id: number;
  author: UserSummary;
  body: string;
  is_internal: boolean;
  /** The requester's account of how they solved the problem themselves. */
  is_solution: boolean;
  created_at: string;
};

export type HistoryEntry = {
  id: number;
  event_type: string;
  field: string | null;
  old_value: string | null;
  new_value: string | null;
  actor: UserSummary | null;
  created_at: string;
};

export type Analysis = {
  id: number;
  status: AnalysisStatus;
  provider: string;
  model: string;
  category_name: string | null;
  subcategory_name: string | null;
  team_name: string | null;
  priority: Priority | null;
  urgency: Priority | null;
  summary: string | null;
  reasoning: string | null;
  confidence: number | null;
  matched_rule: NamedRef | null;
  applied_fields: string[];
  error_code: string | null;
  requested_by: UserSummary | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  created_at: string;
};

export type SuggestionSource = {
  article_id: number | null;
  article_code: string;
  article_title: string;
  rank: number;
  score: number;
  cited: boolean;
};

export type Suggestion = {
  id: number;
  status: AnalysisStatus;
  provider: string;
  model: string;
  embedding_model: string | null;
  can_answer: boolean | null;
  answer: string | null;
  sources: SuggestionSource[];
  error_code: string | null;
  requested_by: UserSummary | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  created_at: string;
};

export type Team = {
  id: number;
  name: string;
  description: string | null;
  members: UserSummary[];
  created_at: string;
};

export type Subcategory = {
  id: number;
  category_id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

export type Category = {
  id: number;
  name: string;
  description: string | null;
  default_team_id: number | null;
  is_active: boolean;
  subcategories: Subcategory[];
};

export type PriorityRule = {
  id: number;
  name: string;
  keywords: string[];
  priority: Priority;
  is_active: boolean;
  created_at: string;
};

export type ArticleSummary = {
  id: number;
  code: string;
  title: string;
  category: NamedRef | null;
  tags: string[];
  status: ArticleStatus;
};

export type Article = ArticleSummary & {
  content: string;
  author: UserSummary | null;
  index_status: IndexStatus;
  index_error: string | null;
  indexed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SearchHit = { article: ArticleSummary; score: number; excerpt: string };

export type Dashboard = {
  generated_at: string;
  timezone: string;
  indicators: {
    open: number;
    in_progress: number;
    waiting_user: number;
    critical_open: number;
    sla_at_risk: number;
    sla_breached_open: number;
    resolved_today: number;
  };
  period: {
    days: number;
    created: number;
    resolved: number;
    resolution_rate: number | null;
    avg_first_response_hours: number | null;
    avg_resolution_hours: number | null;
    sla_met: number;
    sla_breached: number;
  };
  by_category: { label: string; count: number }[];
  by_priority: { label: string; count: number }[];
  by_team: { label: string; count: number }[];
  by_status: { label: string; count: number }[];
  daily: { date: string; created: number; resolved: number }[];
  resolution_by_category: { label: string; avg_hours: number; tickets: number }[];
  ai: {
    analyses: number;
    failed_analyses: number;
    category_acceptance: number | null;
    priority_acceptance: number | null;
    avg_confidence: number | null;
    auto_applied: number;
    suggestions: number;
    suggestions_answered: number;
    estimated_minutes_saved: number;
    top_articles: { article_id: number | null; code: string; title: string; citations: number }[];
  };
};
