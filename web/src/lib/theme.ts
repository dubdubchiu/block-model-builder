export type ThemeChoice = "light" | "dark" | "system";

const KEY = "bm-theme";

interface ThemeRoot {
  setAttribute(name: string, value: string): void;
  removeAttribute(name: string): void;
}

/** Light and dark set data-theme on <html>; system removes it so the OS decides. */
export function applyTheme(choice: ThemeChoice, root: ThemeRoot = document.documentElement): void {
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function loadThemeChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // Storage can be unavailable (private mode, blocked site data); fall back to the default.
  }
  return "system";
}

export function saveThemeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    // Not persisted; the choice still applies for this visit.
  }
}
