/**
 * Chart primitives.
 *
 * Palettes were validated with the data-viz validator against this app's own surfaces
 * (#ffffff light, #171a21 dark):
 * - two series (created vs resolved): categorical blue + orange, passes in both modes;
 * - priority: single-hue ordinal blue ramp (priority is an ordered scale, not categories);
 * - SLA met vs breached: diverging blue/red. Green vs red failed the colour-blind check
 *   (ΔE 4.1 for deuteranopia), so the "traffic light" pairing is deliberately not used.
 */

import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatNumber } from "../lib/format";
import { useTheme } from "../theme/ThemeProvider";

type Palette = {
  series: [string, string];
  single: string;
  ordinal: [string, string, string, string];
  positive: string;
  negative: string;
  grid: string;
  axis: string;
};

const LIGHT: Palette = {
  series: ["#2a78d6", "#eb6834"],
  single: "#2a78d6",
  ordinal: ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"],
  positive: "#2a78d6",
  negative: "#d03b3b",
  grid: "#e1e0d9",
  axis: "#898781",
};

const DARK: Palette = {
  series: ["#3987e5", "#d95926"],
  single: "#3987e5",
  ordinal: ["#184f95", "#256abf", "#3987e5", "#86b6ef"],
  positive: "#3987e5",
  negative: "#e66767",
  grid: "#2c2c2a",
  axis: "#898781",
};

export function usePalette(): Palette {
  return useTheme().theme === "dark" ? DARK : LIGHT;
}

const AXIS_TICK = { fontSize: 12, fill: "currentColor" };

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-4 text-xs text-text-muted">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-full"
            style={{ backgroundColor: item.color }}
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: ReactNode }[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-text">{title}</p>
      {rows.map((row) => (
        <p key={row.label} className="flex items-center justify-between gap-4 text-text-muted">
          <span>{row.label}</span>
          <span className="font-medium tabular-nums text-text">{row.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Tickets opened and resolved per day. Both series share one axis (same unit). */
export function DailyChart({
  data,
  labels,
}: {
  data: { date: string; created: number; resolved: number }[];
  labels: [string, string];
}) {
  const palette = usePalette();
  const formatted = data.map((point) => ({
    ...point,
    day: new Date(`${point.date}T12:00:00`).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
    }),
  }));

  return (
    <>
      <Legend
        items={[
          { label: labels[0], color: palette.series[0] },
          { label: labels[1], color: palette.series[1] },
        ]}
      />
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={formatted} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={palette.grid} vertical={false} />
          <XAxis
            dataKey="day"
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={{ stroke: palette.grid }}
            className="text-text-muted"
            minTickGap={24}
          />
          <YAxis
            tick={AXIS_TICK}
            tickLine={false}
            axisLine={false}
            className="text-text-muted"
            width={44}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ stroke: palette.axis, strokeWidth: 1 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipBox
                  title={String(label)}
                  rows={payload.map((item, index) => ({
                    label: labels[index] ?? String(item.dataKey),
                    value: formatNumber(Number(item.value)),
                  }))}
                />
              ) : null
            }
          />
          <Line
            type="monotone"
            dataKey="created"
            stroke={palette.series[0]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
          <Line
            type="monotone"
            dataKey="resolved"
            stroke={palette.series[1]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

/** Horizontal ranking. One series, so one hue and no legend: the title names it. */
export function RankingChart({
  data,
  unit = "chamados",
}: {
  data: { label: string; count: number }[];
  unit?: string;
}) {
  const palette = usePalette();
  const height = Math.max(160, data.length * 34);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={palette.grid} horizontal={false} />
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="label"
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={140}
          className="text-text-muted"
        />
        <Tooltip
          cursor={{ fill: palette.grid, fillOpacity: 0.35 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox
                title={String(payload[0].payload.label)}
                rows={[{ label: unit, value: formatNumber(Number(payload[0].value)) }]}
              />
            ) : null
          }
        />
        <Bar dataKey="count" fill={palette.single} radius={[0, 4, 4, 0]} barSize={18} isAnimationActive={false}>
          <LabelList dataKey="count" position="right" className="fill-text-muted text-xs" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Priority is an ordered scale, so it uses one hue stepped from light to dark. */
export function OrdinalChart({ data }: { data: { label: string; count: number }[] }) {
  const palette = usePalette();

  return (
    <ResponsiveContainer width="100%" height={Math.max(160, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={palette.grid} horizontal={false} />
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="label"
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={90}
          className="text-text-muted"
        />
        <Tooltip
          cursor={{ fill: palette.grid, fillOpacity: 0.35 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox
                title={String(payload[0].payload.label)}
                rows={[{ label: "chamados", value: formatNumber(Number(payload[0].value)) }]}
              />
            ) : null
          }
        />
        <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={18} isAnimationActive={false}>
          <LabelList dataKey="count" position="right" className="fill-text-muted text-xs" />
          {data.map((item, index) => (
            <Cell key={item.label} fill={palette.ordinal[index] ?? palette.single} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Two opposite outcomes as one proportion bar, with the numbers written on it. */
export function ProportionBar({
  positive,
  negative,
  positiveLabel,
  negativeLabel,
}: {
  positive: number;
  negative: number;
  positiveLabel: string;
  negativeLabel: string;
}) {
  const palette = usePalette();
  const total = positive + negative;
  if (total === 0) {
    return <p className="text-sm text-text-muted">Sem dados no período.</p>;
  }
  const share = (positive / total) * 100;

  return (
    <div>
      <div className="mb-2 flex items-end justify-between gap-3">
        <p className="text-2xl font-semibold tracking-tight text-text">
          {share.toFixed(0).replace(".", ",")}%
        </p>
        <p className="text-xs text-text-muted">{formatNumber(total)} chamados resolvidos</p>
      </div>
      {/* 2px gap between the two fills, as the mark spec asks for. */}
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full">
        <div style={{ width: `${share}%`, backgroundColor: palette.positive }} />
        <div style={{ width: `${100 - share}%`, backgroundColor: palette.negative }} />
      </div>
      <ul className="mt-3 flex flex-wrap gap-4 text-xs text-text-muted">
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-full"
            style={{ backgroundColor: palette.positive }}
          />
          {positiveLabel}: <span className="font-medium text-text">{formatNumber(positive)}</span>
        </li>
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2.5 rounded-full"
            style={{ backgroundColor: palette.negative }}
          />
          {negativeLabel}: <span className="font-medium text-text">{formatNumber(negative)}</span>
        </li>
      </ul>
    </div>
  );
}
