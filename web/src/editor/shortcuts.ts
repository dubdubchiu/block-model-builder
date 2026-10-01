import { useEffect } from "react";
import { useEditor } from "./store";

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/** Delete, undo, redo, copy, paste and save, ignored while typing in a field. */
export function useShortcuts(enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const s = useEditor.getState();
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        s.save();
        return;
      }
      if (typing(e.target) || document.querySelector("dialog[open]")) return;
      const key = e.key.toLowerCase();
      if (e.key === "Delete" || e.key === "Backspace") {
        if (s.selection.length || s.selectedWires.length) {
          e.preventDefault();
          s.deleteSelection();
        }
      } else if (mod && key === "z" && !e.shiftKey) {
        e.preventDefault();
        s.undo();
      } else if (mod && (key === "y" || (key === "z" && e.shiftKey))) {
        e.preventDefault();
        s.redo();
      } else if (mod && key === "c") {
        s.copySelection();
      } else if (mod && key === "v") {
        e.preventDefault();
        s.pasteClip();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
