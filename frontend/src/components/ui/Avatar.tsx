import clsx from "clsx";

import { initials } from "@/lib/format";

export function Avatar({
  name,
  email,
  size = "md",
  className,
}: {
  name: string | null;
  email: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizes = {
    sm: "h-8 w-8 text-[11px]",
    md: "h-9 w-9 text-xs",
    lg: "h-12 w-12 text-sm",
  } as const;
  return (
    <span
      aria-hidden
      className={clsx(
        "inline-flex shrink-0 items-center justify-center rounded-full border border-line bg-gradient-to-br from-accent-soft to-teal-soft font-semibold text-accent",
        sizes[size],
        className,
      )}
    >
      {initials(name, email)}
    </span>
  );
}
