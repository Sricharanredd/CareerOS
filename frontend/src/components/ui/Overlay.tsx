import clsx from "clsx";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { Button, IconButton } from "@/components/ui/Button";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// One body scroll lock for all overlays: the last one out restores the saved value,
// so a nested dialog closing with its parent cannot leave the page locked.
let lockCount = 0;
let savedOverflow = "";
let nextSequence = 0;
// Every open overlay. Depth comes from nesting, sequence breaks sibling ties;
// the highest pair is the topmost overlay and owns Escape and the focus trap.
const openOverlays: { id: symbol; depth: number; sequence: number }[] = [];
const OverlayDepth = createContext(0);

function isTopmost(id: symbol): boolean {
  if (openOverlays.length === 0) return false;
  let top = openOverlays[0];
  for (const entry of openOverlays) {
    if (entry.depth > top.depth || (entry.depth === top.depth && entry.sequence > top.sequence)) top = entry;
  }
  return top.id === id;
}

// Shared dialog behaviour: Escape, scroll lock, initial focus, focus trap, focus return.
export function useOverlay(open: boolean, onClose: () => void) {
  const previous = useRef<HTMLElement | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  const idRef = useRef<symbol | null>(null);
  if (!idRef.current) idRef.current = Symbol("overlay");
  const id = idRef.current;
  const depth = useContext(OverlayDepth);

  useEffect(() => {
    close.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    previous.current = document.activeElement as HTMLElement | null;
    openOverlays.push({ id, depth, sequence: nextSequence++ });
    if (lockCount === 0) {
      savedOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    lockCount += 1;
    panel.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTopmost(id)) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = Array.from(panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!panel.current?.contains(active) || active === panel.current) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      const index = openOverlays.findIndex((entry) => entry.id === id);
      if (index !== -1) openOverlays.splice(index, 1);
      lockCount -= 1;
      if (lockCount === 0) document.body.style.overflow = savedOverflow;
      previous.current?.focus?.();
    };
  }, [open, id, depth]);

  return panel;
}

const SIZES = {
  sm: "max-w-md",
  md: "max-w-xl",
  lg: "max-w-3xl",
  xl: "max-w-5xl",
} as const;

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  size?: keyof typeof SIZES;
  footer?: ReactNode;
  children: ReactNode;
}

export function Modal({ open, onClose, title, description, size = "md", footer, children }: ModalProps) {
  const panel = useOverlay(open, onClose);
  const depth = useContext(OverlayDepth);
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-8">
      <div
        className="fixed inset-0 bg-[#0a0e16]/55 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        className={clsx(
          "relative z-10 my-auto flex max-h-[calc(100dvh-2rem)] w-full flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-pop outline-none sm:max-h-[calc(100dvh-4rem)]",
          SIZES[size],
        )}
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-fg">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="scroll-area min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <OverlayDepth.Provider value={depth + 1}>{children}</OverlayDepth.Provider>
        </div>
        {footer && (
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-line px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  width = "max-w-xl",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const panel = useOverlay(open, onClose);
  const depth = useContext(OverlayDepth);
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-[#0a0e16]/45 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        className={clsx(
          "absolute inset-y-0 right-0 flex w-full flex-col border-l border-line bg-surface shadow-pop outline-none",
          width,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-fg">{title}</h2>
            {subtitle && <div className="mt-0.5 text-sm text-muted">{subtitle}</div>}
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="scroll-area min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <OverlayDepth.Provider value={depth + 1}>{children}</OverlayDepth.Provider>
        </div>
        {footer && (
          <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-line bg-surface-2/50 px-6 py-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  loading = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  loading?: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-relaxed text-muted">{description}</div>
    </Modal>
  );
}
