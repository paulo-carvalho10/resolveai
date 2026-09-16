/** Portuguese labels and colour tokens for the enums the API returns in English. */

export const TICKET_STATUS = {
  OPEN: { label: "Aberto", tone: "open" },
  IN_PROGRESS: { label: "Em andamento", tone: "progress" },
  WAITING_USER: { label: "Aguardando solicitante", tone: "waiting" },
  RESOLVED: { label: "Resolvido", tone: "done" },
  CLOSED: { label: "Fechado", tone: "neutral" },
} as const;

export const TICKET_PRIORITY = {
  LOW: { label: "Baixa", tone: "neutral" },
  MEDIUM: { label: "Média", tone: "open" },
  HIGH: { label: "Alta", tone: "waiting" },
  CRITICAL: { label: "Crítica", tone: "danger" },
} as const;

export const SLA_STATUS = {
  ON_TRACK: { label: "No prazo", tone: "done" },
  AT_RISK: { label: "Em risco", tone: "waiting" },
  BREACHED: { label: "SLA estourado", tone: "danger" },
  MET: { label: "SLA cumprido", tone: "done" },
} as const;

export const USER_ROLE = {
  ADMIN: "Administrador",
  AGENT: "Atendente",
  USER: "Solicitante",
} as const;

export const ARTICLE_STATUS = {
  DRAFT: { label: "Rascunho", tone: "waiting" },
  PUBLISHED: { label: "Publicado", tone: "done" },
  ARCHIVED: { label: "Arquivado", tone: "neutral" },
} as const;

export const INDEX_STATUS = {
  PENDING: "Aguardando indexação",
  INDEXED: "Indexado",
  FAILED: "Falha na indexação",
} as const;

export const EVENT_LABEL = {
  CREATED: "Chamado criado",
  TITLE_CHANGED: "Título alterado",
  DESCRIPTION_CHANGED: "Descrição alterada",
  STATUS_CHANGED: "Status alterado",
  PRIORITY_CHANGED: "Prioridade alterada",
  CATEGORY_CHANGED: "Categoria alterada",
  SUBCATEGORY_CHANGED: "Subcategoria alterada",
  TEAM_CHANGED: "Equipe alterada",
  ASSIGNEE_CHANGED: "Responsável alterado",
  COMMENT_ADDED: "Comentário adicionado",
  RESOLVED: "Chamado resolvido",
  RESOLVED_BY_REQUESTER: "Resolvido pelo solicitante",
  AUTO_CLOSED: "Fechado automaticamente",
  RULE_APPLIED: "Regra de prioridade aplicada",
  AI_ANALYZED: "IA analisou o chamado",
  AI_ANALYSIS_FAILED: "Falha na análise da IA",
} as const;

export type Tone = "open" | "progress" | "waiting" | "done" | "danger" | "neutral" | "brand";

/** Tailwind classes per tone, kept in one place so badges and charts stay consistent. */
export const TONE_CLASSES: Record<Tone, string> = {
  open: "bg-state-open/10 text-state-open",
  progress: "bg-state-progress/10 text-state-progress",
  waiting: "bg-state-waiting/10 text-state-waiting",
  done: "bg-state-done/10 text-state-done",
  danger: "bg-state-danger/10 text-state-danger",
  neutral: "bg-state-neutral/10 text-state-neutral",
  brand: "bg-brand/10 text-brand",
};

export function translateEvent(event: keyof typeof EVENT_LABEL): string {
  return EVENT_LABEL[event] ?? event;
}

/** History and automatic changes store enum values; show them in Portuguese. */
export function translateValue(value: string | null): string | null {
  if (!value) return value;
  const status = TICKET_STATUS[value as keyof typeof TICKET_STATUS];
  if (status) return status.label;
  const priority = TICKET_PRIORITY[value as keyof typeof TICKET_PRIORITY];
  if (priority) return priority.label;
  return value;
}
