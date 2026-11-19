import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import type {
  ComponentPropsWithoutRef,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { createContext, useContext, useId } from "react";

const CONTROL =
  "w-full rounded-lg border border-line bg-surface px-3 text-sm text-fg shadow-sm transition-colors " +
  "placeholder:text-subdued hover:border-line-strong focus:border-accent focus:outline-none " +
  "focus:ring-2 focus:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-60";

export interface FieldProps {
  label?: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}

interface FieldControl {
  id: string;
  describedBy?: string;
  invalid?: boolean;
}

const FieldContext = createContext<FieldControl | null>(null);

export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  const generatedId = useId();
  const controlId = htmlFor ?? generatedId;
  const hintId = `${controlId}-hint`;
  const errorId = `${controlId}-error`;
  const describedBy = error ? errorId : hint ? hintId : undefined;

  function labelText() {
    return (
      <>
        {label}
        {required && <span className="text-danger">*</span>}
      </>
    );
  }

  return (
    <div className={clsx("space-y-1.5", className)}>
      {label &&
        (controlId ? (
          <label htmlFor={controlId} className="flex items-center gap-1 text-[13px] font-medium text-fg">
            {labelText()}
          </label>
        ) : (
          <p className="flex items-center gap-1 text-[13px] font-medium text-fg">{labelText()}</p>
        ))}
      <FieldContext.Provider value={{ id: controlId, describedBy, invalid: Boolean(error) }}>
        {children}
      </FieldContext.Provider>
      {error ? (
        <p id={errorId} className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-xs text-subdued">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function useFieldControl(): FieldControl | null {
  return useContext(FieldContext);
}

export function Input({
  className,
  id,
  "aria-describedby": describedBy,
  "aria-invalid": invalid,
  ...rest
}: ComponentPropsWithoutRef<"input">) {
  const field = useContext(FieldContext);
  return (
    <input
      id={id ?? field?.id}
      aria-describedby={describedBy ?? field?.describedBy}
      aria-invalid={invalid ?? (field?.invalid || undefined)}
      className={clsx(CONTROL, "h-10", className)}
      {...rest}
    />
  );
}

export function Textarea({
  className,
  id,
  "aria-describedby": describedBy,
  "aria-invalid": invalid,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const field = useContext(FieldContext);
  return (
    <textarea
      id={id ?? field?.id}
      aria-describedby={describedBy ?? field?.describedBy}
      aria-invalid={invalid ?? (field?.invalid || undefined)}
      className={clsx(CONTROL, "min-h-24 py-2 leading-relaxed", className)}
      {...rest}
    />
  );
}

export function Select({
  className,
  children,
  id,
  "aria-describedby": describedBy,
  "aria-invalid": invalid,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const field = useContext(FieldContext);
  return (
    <div className="relative">
      <select
        id={id ?? field?.id}
        aria-describedby={describedBy ?? field?.describedBy}
        aria-invalid={invalid ?? (field?.invalid || undefined)}
        className={clsx(CONTROL, "h-10 appearance-none pr-9", className)}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subdued"
        aria-hidden
      />
    </div>
  );
}

export function Checkbox({
  label,
  hint,
  className,
  ...rest
}: ComponentPropsWithoutRef<"input"> & { label: ReactNode; hint?: ReactNode }) {
  const id = useId();
  return (
    <label
      htmlFor={rest.id ?? id}
      className={clsx("flex cursor-pointer items-start gap-2.5 text-sm text-fg", className)}
    >
      <input
        type="checkbox"
        id={rest.id ?? id}
        className="mt-0.5 h-4 w-4 rounded border-line-strong text-accent accent-[var(--accent)] focus:ring-accent/30"
        {...rest}
      />
      <span>
        <span className="font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-subdued">{hint}</span>}
      </span>
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-sm text-fg disabled:opacity-60"
    >
      <span
        className={clsx(
          "relative inline-flex h-5 w-9 items-center rounded-full border transition-colors",
          checked ? "border-accent bg-accent" : "border-line-strong bg-surface-3",
        )}
      >
        <span
          className={clsx(
            "inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform dark:bg-[#0b0f17]",
            checked ? "translate-x-[18px]" : "translate-x-[3px]",
          )}
        />
      </span>
      <span className="text-muted">{label}</span>
    </button>
  );
}
