import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Sparkles } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { PageHeader } from "../components/Layout";
import { Badge, Card, EmptyState, ErrorMessage, Field, Pagination, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import { formatPercent } from "../lib/format";
import { ARTICLE_STATUS } from "../lib/labels";
import type { Article, ArticleSummary, Category, Page, SearchHit } from "../lib/types";

export function KnowledgePage() {
  const { isAdmin, isStaff } = useAuth();
  const [search, setSearch] = useState("");
  const [semanticQuery, setSemanticQuery] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);

  const list = useQuery({
    queryKey: ["knowledge", page],
    queryFn: () => api<Page<ArticleSummary>>("/knowledge", { params: { page, page_size: 20 } }),
    enabled: !semanticQuery,
  });

  const semantic = useQuery({
    queryKey: ["knowledge", "search", semanticQuery],
    queryFn: () => api<SearchHit[]>("/knowledge/search", { params: { q: semanticQuery, limit: 10 } }),
    enabled: semanticQuery.length >= 3,
  });

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setSemanticQuery(search.trim());
  }

  return (
    <>
      <PageHeader
        title="Base de conhecimento"
        description="Busca semântica: descreva o problema com suas palavras, não só por palavra-chave."
        action={
          isAdmin && (
            <button className="btn-primary" onClick={() => setCreating((value) => !value)}>
              <Plus aria-hidden className="size-4" />
              Novo artigo
            </button>
          )
        }
      />

      {creating && isAdmin && <ArticleForm onClose={() => setCreating(false)} />}

      <form onSubmit={onSearch} className="card mb-4 flex items-center gap-2 p-4">
        <div className="relative flex-1">
          <Search aria-hidden className="absolute top-2.5 left-3 size-4 text-text-muted" />
          <input
            className="input pl-9"
            placeholder="Ex.: a nota fiscal deu duplicidade na SEFAZ"
            aria-label="Buscar artigos"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <button type="submit" className="btn-secondary">
          Buscar
        </button>
        {semanticQuery && (
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setSearch("");
              setSemanticQuery("");
            }}
          >
            Limpar
          </button>
        )}
      </form>

      {semanticQuery ? (
        <Card
          title={
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles aria-hidden className="size-4 text-brand" />
              Resultados para “{semanticQuery}”
            </h2>
          }
        >
          {semantic.isPending && <Spinner />}
          {semantic.error && <ErrorMessage>{errorMessage(semantic.error)}</ErrorMessage>}
          {semantic.data?.length === 0 && (
            <EmptyState
              title="Nenhum artigo relevante"
              description="Nenhum artigo publicado passou do limite mínimo de similaridade."
            />
          )}
          <ul className="space-y-4">
            {semantic.data?.map((hit) => (
              <li key={hit.article.id} className="border-b border-border pb-4 last:border-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/base-de-conhecimento/${hit.article.id}`}
                    className="font-medium text-text hover:text-brand"
                  >
                    {hit.article.code} — {hit.article.title}
                  </Link>
                  <Badge tone="brand">similaridade {formatPercent(hit.score)}</Badge>
                </div>
                <p className="mt-1 text-sm text-text-muted">{hit.excerpt}</p>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <div className="card overflow-hidden">
          {list.isPending && <Spinner />}
          {list.error && (
            <div className="p-4">
              <ErrorMessage>{errorMessage(list.error)}</ErrorMessage>
            </div>
          )}
          {list.data?.items.length === 0 && (
            <EmptyState title="Nenhum artigo ainda" description="Crie o primeiro artigo da base." />
          )}
          <ul>
            {list.data?.items.map((article) => (
              <li key={article.id} className="border-b border-border last:border-0">
                <Link
                  to={`/base-de-conhecimento/${article.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-surface-muted"
                >
                  <span>
                    <span className="text-sm font-medium text-text">
                      <span className="text-text-muted">{article.code}</span> {article.title}
                    </span>
                    {article.tags.length > 0 && (
                      <span className="mt-1 block text-xs text-text-muted">
                        {article.tags.join(" · ")}
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-2">
                    {article.category && <Badge>{article.category.name}</Badge>}
                    {isStaff && (
                      <Badge tone={ARTICLE_STATUS[article.status].tone}>
                        {ARTICLE_STATUS[article.status].label}
                      </Badge>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {list.data && (
            <Pagination
              page={list.data.page}
              pageSize={list.data.page_size}
              total={list.data.total}
              onChange={setPage}
            />
          )}
        </div>
      )}
    </>
  );
}

export function ArticleForm({ article, onClose }: { article?: Article; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(article?.title ?? "");
  const [content, setContent] = useState(article?.content ?? "");
  const [categoryId, setCategoryId] = useState(String(article?.category?.id ?? ""));
  const [tags, setTags] = useState(article?.tags.join(", ") ?? "");
  const [status, setStatus] = useState(article?.status ?? "PUBLISHED");

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/categories"),
  });

  const save = useMutation({
    mutationFn: () =>
      api<Article>(article ? `/knowledge/${article.id}` : "/knowledge", {
        method: article ? "PATCH" : "POST",
        body: {
          title,
          content,
          category_id: categoryId ? Number(categoryId) : null,
          tags: tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
          status,
        },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      onClose();
    },
  });

  return (
    <Card title={article ? "Editar artigo" : "Novo artigo"} className="mb-4">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Título">
          <input
            className="input"
            required
            minLength={5}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
        <Field label="Conteúdo" hint="Separe os passos em parágrafos: cada bloco vira um trecho indexado.">
          <textarea
            className="input min-h-56 font-mono text-xs"
            required
            minLength={20}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Categoria">
            <select
              className="input"
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
            >
              <option value="">Sem categoria</option>
              {categories?.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Tags" hint="Separadas por vírgula">
            <input className="input" value={tags} onChange={(event) => setTags(event.target.value)} />
          </Field>
          <Field label="Situação">
            <select
              className="input"
              value={status}
              onChange={(event) => setStatus(event.target.value as typeof status)}
            >
              {Object.entries(ARTICLE_STATUS).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {save.error && <ErrorMessage>{errorMessage(save.error)}</ErrorMessage>}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="btn-primary" disabled={save.isPending}>
            {save.isPending ? "Salvando..." : "Salvar"}
          </button>
        </div>
      </form>
    </Card>
  );
}
