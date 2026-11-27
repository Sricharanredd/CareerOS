import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Modal } from "@/components/ui/Overlay";

function renderModal(onClose = vi.fn()) {
  render(
    <Modal open onClose={onClose} title="Delete application" footer={<button type="button">Confirm</button>}>
      <input aria-label="First field" />
    </Modal>,
  );
  return onClose;
}

function Nested({ open, onOuter = vi.fn(), onInner = vi.fn() }: { open: boolean; onOuter?: () => void; onInner?: () => void }) {
  return (
    <Modal open={open} onClose={onOuter} title="Outer">
      <Modal open={open} onClose={onInner} title="Inner">
        <input aria-label="Inner field" />
      </Modal>
    </Modal>
  );
}

describe("Modal", () => {
  beforeEach(() => {
    document.body.style.overflow = "";
  });

  it("is a labelled dialog that closes on Escape", () => {
    const onClose = renderModal();
    expect(screen.getByRole("dialog", { name: "Delete application" })).toHaveAttribute(
      "aria-modal",
      "true",
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("keeps Tab focus inside the dialog", () => {
    renderModal();
    const dialog = screen.getByRole("dialog");
    const first = screen.getByRole("button", { name: "Close" });
    const last = screen.getByRole("button", { name: "Confirm" });

    expect(document.activeElement).toBe(dialog);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("locks page scrolling while open and restores it on close", () => {
    const { rerender } = render(<Nested open={false} />);
    expect(document.body.style.overflow).toBe("");

    rerender(<Nested open />);
    expect(document.body.style.overflow).toBe("hidden");

    rerender(<Nested open={false} />);
    expect(document.body.style.overflow).toBe("");
  });

  it("restores the overflow value it found, not an empty string", () => {
    document.body.style.overflow = "scroll";
    const { unmount } = render(
      <Modal open onClose={vi.fn()} title="Settings">
        <input aria-label="Field" />
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("scroll");
  });

  it("keeps the background locked while a nested dialog closes but its parent stays open", () => {
    const { rerender } = render(<Nested open />);
    expect(document.body.style.overflow).toBe("hidden");

    rerender(
      <Modal open onClose={vi.fn()} title="Outer">
        <Modal open={false} onClose={vi.fn()} title="Inner">
          <input aria-label="Inner field" />
        </Modal>
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("restores page scrolling when a nested dialog closes with its parent", () => {
    const { rerender } = render(<Nested open />);
    expect(document.body.style.overflow).toBe("hidden");

    rerender(<Nested open={false} />);
    expect(document.body.style.overflow).toBe("");
  });

  it("Escape reaches only the topmost dialog", () => {
    const outer = vi.fn();
    const inner = vi.fn();
    render(<Nested open onOuter={outer} onInner={inner} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(inner).toHaveBeenCalledOnce();
    expect(outer).not.toHaveBeenCalled();
  });
});
