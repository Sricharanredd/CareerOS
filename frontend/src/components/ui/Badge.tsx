import clsx from "clsx";
import type { ReactNode } from "react";

import { STATUS_DOT, STATUS_LABEL, STATUS_TONE } from "@/lib/constants";
import type { ApplicationStatus } from "@/lib/types";

type Tone = "neutral" | "accent" | "teal" | "success" | "warning" | "danger" | "outline";

const TONES: Record<Tone, string> = {
  neutral: "border-line bg-surface-2 text-muted",
  accent: "border-accent/25 bg-accent-soft text-accent",
  teal: "border-teal/25 bg-teal-soft text-teal",
  success: "border-success/30 bg-success-soft text-success",
  warning: "border-warning/25 bg-warning-soft text-warning",
  danger: "border-danger/25 bg-danger-soft text-danger",
  outline: "border-line-strong bg-transparent text-muted",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        STATUS_TONE[status],
      )}
    >
      <span className={clsx("h-1.5 w-1.5 rounded-full", STATUS_DOT[status])} aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}
