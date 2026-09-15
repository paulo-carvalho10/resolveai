import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { TONE_CLASSES } from "../lib/labels";
import type { Tone } from "../lib/labels";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {typeof title === "string" ? (
            <h2 className="text-sm font-semibold text-text">{title}</h2>
          ) : (
            title
          )}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Spinner({ label = "Carregando..." }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-text-muted">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="text-sm font-medium text-text">{title}</p>
      {description && <p className="mt-1 text-sm text-text-muted">{description}</p>}
    </div>
  );
}

export function ErrorMessage({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg bg-state-danger/10 px-3 py-2 text-sm text-state-danger">
      {children}
    </p>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-state-danger">{error}</span>}
    </label>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-sm text-text-muted">
      <span>
        {first}–{last} de {total}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn-secondary"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
        >
          Anterior
        </button>
        <span>
          Página {page} de {pages}
        </span>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => onChange(page + 1)}
          disabled={page >= pages}
        >
          Próxima
        </button>
      </div>
    </div>
  );
}
