const dateFormatter = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" });
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
const monthFormatter = new Intl.DateTimeFormat(undefined, { month: "short", year: "numeric" });
const relativeFormatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/** The API stores naive UTC timestamps; parse them as UTC unless an offset is present. */
export function parseDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  const hasZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return dateFormatter.format(parseDate(value));
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return dateTimeFormatter.format(parseDate(value));
}

export function formatMonth(value: string | Date): string {
  return monthFormatter.format(parseDate(value));
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = parseDate(value);
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (abs < minute) return "just now";
  if (abs < hour) return relativeFormatter.format(Math.round(diffMs / minute), "minute");
  if (abs < day) return relativeFormatter.format(Math.round(diffMs / hour), "hour");
  if (abs < 30 * day) return relativeFormatter.format(Math.round(diffMs / day), "day");
  if (abs < 365 * day) return relativeFormatter.format(Math.round(diffMs / (30 * day)), "month");
  return relativeFormatter.format(Math.round(diffMs / (365 * day)), "year");
}

export function formatDayLabel(value: string): string {
  const date = parseDate(value);
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(date);
}

export function labelize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .split(/[_\s]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function initials(name: string | null | undefined, email: string): string {
  const source = (name ?? "").trim();
  if (source) {
    const parts = source.split(/\s+/).slice(0, 2);
    return parts.map((part) => part[0]?.toUpperCase() ?? "").join("");
  }
  return email.slice(0, 2).toUpperCase();
}

export function formatSalaryRange(
  min: string | number | null | undefined,
  max: string | number | null | undefined,
  currency: string | null | undefined,
  period: string | null | undefined,
): string | null {
  if (min == null && max == null) return null;
  const fmt = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 0,
    notation: "compact",
  });
  const range =
    min != null && max != null
      ? `${fmt.format(Number(min))} – ${fmt.format(Number(max))}`
      : fmt.format(Number(min ?? max));
  return period ? `${range} / ${period}` : range;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function truncate(value: string, length: number): string {
  if (value.length <= length) return value;
  return `${value.slice(0, length - 1).trimEnd()}…`;
}

/** Turns a local date input value (yyyy-mm-dd) into an ISO date string, or null. */
export function dateInputToIso(value: string | null | undefined): string | null {
  if (!value) return null;
  return value;
}

export function toDateInputValue(value: string | null | undefined): string {
  if (!value) return "";
  return value.slice(0, 10);
}

export function greeting(date = new Date()): string {
  const hour = date.getHours();
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}
