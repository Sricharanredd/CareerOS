import clsx from "clsx";
import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("h-4 w-4 animate-spin text-muted", className)} aria-hidden />;
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted">
      <Spinner />
      {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-surface-2", className)} />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-col items-center justify-center gap-3 px-6 py-16 text-center", className)}>
      {icon && (
        <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-surface-2 text-muted">
          {icon}
        </div>
      )}
      <div>
        <p className="text-sm font-semibold text-fg">{title}</p>
        {description && <p className="mt-1 max-w-sm text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <p className="text-sm font-medium text-danger">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-sm font-medium text-accent underline-offset-4 hover:underline"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function InlineAlert({
  tone = "danger",
  title,
  children,
}: {
  tone?: "danger" | "warning" | "success" | "accent";
  title?: ReactNode;
  children?: ReactNode;
}) {
  const tones = {
    danger: "border-danger/30 bg-danger-soft text-danger",
    warning: "border-warning/30 bg-warning-soft text-warning",
    success: "border-success/30 bg-success-soft text-success",
    accent: "border-accent/30 bg-accent-soft text-accent",
  } as const;
  return (
    <div className={clsx("rounded-xl border px-3.5 py-3 text-sm", tones[tone])} role="alert">
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={clsx(title && "mt-1", "opacity-90")}>{children}</div>}
    </div>
  );
}
