import { useEffect, useState } from "react";
import { applyTheme, loadThemeChoice, saveThemeChoice, type ThemeChoice } from "../lib/theme";

const CHOICES: { value: ThemeChoice; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(loadThemeChoice);

  useEffect(() => {
    applyTheme(choice);
    saveThemeChoice(choice);
  }, [choice]);

  return (
    <fieldset className="bm-theme">
      <legend className="bm-theme__legend">Theme</legend>
      {CHOICES.map((c) => (
        <label key={c.value} className="dt-choice">
          <input
            type="radio"
            name="theme"
            value={c.value}
            checked={choice === c.value}
            onChange={() => setChoice(c.value)}
          />
          {c.label}
        </label>
      ))}
    </fieldset>
  );
}
