import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../components/Layout";
import { Badge, Card, ErrorMessage, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import { formatDateTime } from "../lib/format";
import { ARTICLE_STATUS, INDEX_STATUS } from "../lib/labels";
import type { Article } from "../lib/types";
import { ArticleForm } from "./KnowledgePage";

export function ArticlePage() {
  const { id } = useParams();
  const articleId = Number(id);
  const { isAdmin, isStaff } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);

  const { data, isPending, error } = useQuery({
    queryKey: ["knowledge", articleId],
    queryFn: () => api<Article>(`/knowledge/${articleId}`),
  });

  const remove = useMutation({
    mutationFn: () => api<void>(`/knowledge/${articleId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      navigate("/base-de-conhecimento");
    },
  });

  if (isPending) return <Spinner />;
  if (error || !data) return <ErrorMessage>{errorMessage(error)}</ErrorMessage>;

  if (editing) {
    return (
      <div className="mx-auto max-w-3xl">
        <ArticleForm article={data} onClose={() => setEditing(false)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/base-de-conhecimento" className="btn-ghost mb-4 -ml-3">
        <ArrowLeft aria-hidden className="size-4" />
        Voltar para a base
      </Link>

      <PageHeader
        title={data.title}
        description={`${data.code} · atualizado em ${formatDateTime(data.updated_at)}`}
        action={
          isAdmin && (
            <div className="flex gap-2">
              <button className="btn-secondary" onClick={() => setEditing(true)}>
                <Pencil aria-hidden className="size-4" />
                Editar
              </button>
              <button
                className="btn-secondary text-state-danger"
                onClick={() => {
                  if (confirm("Excluir este artigo? A ação não pode ser desfeita.")) remove.mutate();
                }}
                disabled={remove.isPending}
              >
                <Trash2 aria-hidden className="size-4" />
                Excluir
              </button>
            </div>
          )
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {isStaff && (
          <Badge tone={ARTICLE_STATUS[data.status].tone}>{ARTICLE_STATUS[data.status].label}</Badge>
        )}
        {data.category && <Badge>{data.category.name}</Badge>}
        {data.tags.map((tag) => (
          <Badge key={tag}>{tag}</Badge>
        ))}
      </div>

      {remove.error && (
        <div className="mb-4">
          <ErrorMessage>{errorMessage(remove.error)}</ErrorMessage>
        </div>
      )}

      <Card>
        <article className="text-sm leading-relaxed whitespace-pre-wrap text-text">
          {data.content}
        </article>
      </Card>

      {isStaff && (
        <p className="mt-4 text-xs text-text-muted">
          {INDEX_STATUS[data.index_status]}
          {data.indexed_at && ` em ${formatDateTime(data.indexed_at)}`}
          {data.index_error && ` (${data.index_error})`}
          {data.author && ` · autor: ${data.author.full_name}`}
        </p>
      )}
    </div>
  );
}
