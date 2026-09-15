/** Brazilian formatting: dates, relative time, durations, numbers and percentages. */

const dateTime = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" });
const relative = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });

export function formatDateTime(value: string | Date): string {
  return dateTime.format(new Date(value));
}

export function formatDay(value: string | Date): string {
  return dateOnly.format(new Date(value));
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

export function formatRelative(value: string | Date, now: Date = new Date()): string {
  const seconds = (new Date(value).getTime() - now.getTime()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "agora";
}

/** 2.5 -> "2h30", 0.5 -> "30min", 30 -> "1d 6h" */
export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—";
  // Everything is derived from the rounded minutes, so 3h59m59s reads "4h", never "3h".
  const totalMinutes = Math.round(hours * 60);
  if (totalMinutes < 60) return `${totalMinutes}min`;
  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 24) {
    const minutes = totalMinutes % 60;
    return minutes ? `${totalHours}h${String(minutes).padStart(2, "0")}` : `${totalHours}h`;
  }
  const days = Math.floor(totalHours / 24);
  const rest = totalHours % 24;
  return rest ? `${days}d ${rest}h` : `${days}d`;
}

export function formatMinutes(minutes: number): string {
  return formatHours(minutes / 60);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits).replace(".", ",")}%`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

/** Remaining SLA time: "2h30 restantes" or "atrasado há 1h". */
export function formatDeadline(dueAt: string, now: Date = new Date()): string {
  const hours = (new Date(dueAt).getTime() - now.getTime()) / 3_600_000;
  return hours >= 0 ? `${formatHours(hours)} restantes` : `atrasado há ${formatHours(-hours)}`;
}
