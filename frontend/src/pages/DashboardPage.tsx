import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, Clock, Inbox, Timer } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { PageHeader } from "../components/Layout";
import { DailyChart, OrdinalChart, ProportionBar, RankingChart } from "../components/charts";
import { Card, ErrorMessage, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { errorMessage } from "../lib/errors";
import { formatHours, formatMinutes, formatNumber, formatPercent } from "../lib/format";
import { TICKET_PRIORITY } from "../lib/labels";
import type { Dashboard } from "../lib/types";

const PERIODS = [
  { days: 7, label: "7 dias" },
  { days: 30, label: "30 dias" },
  { days: 90, label: "90 dias" },
];

export function DashboardPage() {
  const [days, setDays] = useState(30);
  const { data, isPending, error } = useQuery({
    queryKey: ["dashboard", days],
    queryFn: () => api<Dashboard>("/analytics/dashboard", { params: { days } }),
  });

  if (isPending) return <Spinner label="Calculando indicadores..." />;
  if (error || !data) return <ErrorMessage>{errorMessage(error)}</ErrorMessage>;

  const { indicators, period, ai } = data;
  const topCategories = data.by_category.slice(0, 6);
  const topTeams = data.by_team.slice(0, 6);
  const priorities = data.by_priority.map((item) => ({
    label: TICKET_PRIORITY[item.label as keyof typeof TICKET_PRIORITY].label,
    count: item.count,
  }));

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Fila atual e métricas dos últimos ${days} dias.`}
        action={
          <div className="flex gap-1 rounded-lg border border-border p-1">
            {PERIODS.map((option) => (
              <button
                key={option.days}
                type="button"
                onClick={() => setDays(option.days)}
                className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                  days === option.days
                    ? "bg-brand-soft text-brand"
                    : "text-text-muted hover:text-text"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          icon={<Inbox className="size-4" />}
          label="Não resolvidos"
          value={formatNumber(indicators.open + indicators.in_progress + indicators.waiting_user)}
          hint={`${formatNumber(indicators.open)} novos · ${formatNumber(indicators.in_progress)} em andamento`}
        />
        <Stat
          icon={<AlertTriangle className="size-4" />}
          label="Críticos não resolvidos"
          value={formatNumber(indicators.critical_open)}
          hint={`${formatNumber(indicators.sla_at_risk)} com SLA em risco`}
          tone={indicators.critical_open > 0 ? "danger" : undefined}
        />
        <Stat
          icon={<CheckCircle2 className="size-4" />}
          label="Resolvidos hoje"
          value={formatNumber(indicators.resolved_today)}
          hint={`${formatNumber(period.resolved)} no período`}
        />
        <Stat
          icon={<Timer className="size-4" />}
          label="Tempo médio de resolução"
          value={formatHours(period.avg_resolution_hours)}
          hint={`1ª resposta em ${formatHours(period.avg_first_response_hours)}`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Chamados por dia" className="lg:col-span-2">
          <DailyChart data={data.daily} labels={["Criados", "Resolvidos"]} />
        </Card>

        <Card title="SLA no período">
          <ProportionBar
            positive={period.sla_met}
            negative={period.sla_breached}
            positiveLabel="Dentro do prazo"
            negativeLabel="Estourado"
          />
          <dl className="mt-5 space-y-2 border-t border-border pt-4 text-sm">
            <Row label="Taxa de resolução" value={formatPercent(period.resolution_rate)} />
            <Row label="Prazo estourado agora" value={formatNumber(indicators.sla_breached_open)} />
            <Row label="Aguardando solicitante" value={formatNumber(indicators.waiting_user)} />
          </dl>
        </Card>

        <Card title="Chamados por categoria">
          <RankingChart data={topCategories} />
        </Card>

        <Card title="Chamados por prioridade">
          <OrdinalChart data={priorities} />
        </Card>

        <Card title="Chamados por equipe">
          <RankingChart data={topTeams} />
        </Card>

        <Card
          title={
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Bot aria-hidden className="size-4 text-brand" />
              Desempenho da IA
            </h2>
          }
          className="lg:col-span-2"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat
              label="Categoria aceita"
              value={formatPercent(ai.category_acceptance)}
              hint="categoria da IA mantida pelo atendente"
              plain
            />
            <Stat
              label="Prioridade aceita"
              value={formatPercent(ai.priority_acceptance)}
              hint="prioridade da IA mantida"
              plain
            />
            <Stat
              label="Confiança média"
              value={formatPercent(ai.avg_confidence)}
              hint={`${formatNumber(ai.analyses)} análises`}
              plain
            />
          </div>
          <dl className="mt-4 space-y-2 border-t border-border pt-4 text-sm">
            <Row label="Triagens aplicadas automaticamente" value={formatNumber(ai.auto_applied)} />
            <Row
              label="Sugestões com resposta da base"
              value={`${formatNumber(ai.suggestions_answered)} de ${formatNumber(ai.suggestions)}`}
            />
            <Row label="Análises com falha" value={formatNumber(ai.failed_analyses)} />
            <Row
              label="Tempo economizado (estimativa)"
              value={formatMinutes(ai.estimated_minutes_saved)}
            />
          </dl>
        </Card>

        <Card title="Artigos mais citados">
          {ai.top_articles.length === 0 ? (
            <p className="text-sm text-text-muted">Nenhum artigo citado no período.</p>
          ) : (
            <ul className="space-y-3 text-sm">
              {ai.top_articles.map((article) => (
                <li key={article.code} className="flex items-start justify-between gap-3">
                  <span>
                    {article.article_id ? (
                      <Link
                        to={`/base-de-conhecimento/${article.article_id}`}
                        className="text-text hover:text-brand"
                      >
                        {article.code} — {article.title}
                      </Link>
                    ) : (
                      <span className="text-text-muted">
                        {article.code} — {article.title}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 tabular-nums text-text-muted">
                    {formatNumber(article.citations)}×
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <p className="mt-6 flex items-center gap-2 text-xs text-text-muted">
        <Clock aria-hidden className="size-3.5" />
        Fuso horário {data.timezone}. O tempo economizado é uma estimativa: 3 minutos por triagem
        aplicada e 5 minutos por sugestão respondida.
      </p>
    </>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
  tone,
  plain = false,
}: {
  icon?: ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "danger";
  plain?: boolean;
}) {
  const content = (
    <>
      <div className="flex items-center gap-2 text-sm text-text-muted">
        {icon && <span className={tone === "danger" ? "text-state-danger" : ""}>{icon}</span>}
        {label}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-text">{value}</p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </>
  );
  return plain ? <div>{content}</div> : <div className="card p-4">{content}</div>;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-medium tabular-nums text-text">{value}</dd>
    </div>
  );
}
