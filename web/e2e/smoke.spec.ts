import { mkdirSync, writeFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";

const SHOTS = "e2e-screens";
const TOTAL_REVENUE = "121f5ae3-4f9c-4590-9b58-e332ae7e52b0";

async function openDemo(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId(`preview-${TOTAL_REVENUE}-result`)).toBeVisible();
}

test("demo model loads and shows evaluated values", async ({ page }) => {
  await openDemo(page);
  await expect(page.getByTestId(`preview-${TOTAL_REVENUE}-result`)).toHaveText("650, 700, 750, … (8 periods)");
  await expect(page.getByText("series<currency> USD").first()).toBeVisible();
  await expect(page.getByText("Sample data").first()).toBeVisible();
  const titleBlock = page.getByLabel("Title block");
  await expect(titleBlock).toContainText("Prototype");
  await expect(titleBlock).toContainText("Sample");
  await expect(page.getByRole("tab", { name: "Summary" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add Growth" })).toBeVisible();
});

test("latency check runs and passes the gate", async ({ page }) => {
  await page.goto("/?dev=latency");
  await page.getByRole("button", { name: "Run latency check" }).click();
  await expect(page.getByTestId("gate")).toBeVisible({ timeout: 45_000 });
  const read = async (id: string) => (await page.getByTestId(id).textContent())?.trim();
  const table = await page.getByTestId("latency-table").innerText();
  mkdirSync(SHOTS, { recursive: true });
  writeFileSync(`${SHOTS}/latency.txt`, table + "\n");
  console.log(`\n${table}`);
  expect(await read("gate")).toBe("Pass");
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 375]) {
    test(`screenshot ${theme} ${width}`, async ({ page }) => {
      // Reduced motion: no 120ms color transition caught mid-way, and it checks the no-motion rule holds.
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.setViewportSize({ width, height: width > 400 ? 1000 : 812 });
      await openDemo(page);
      await page.getByLabel(theme === "light" ? "Light" : "Dark").check();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      if (width < 400) {
        await expect(page.getByText("Editing is desktop only.")).toBeVisible();
        await expect(page.getByRole("button", { name: "Add Growth" })).toHaveCount(0);
        await expect(page.getByRole("button", { name: "Save model" })).toHaveCount(0);
      }
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth, "no horizontal page scroll").toBeLessThanOrEqual(width);
      await page.screenshot({ path: `${SHOTS}/${theme}-${width}.png`, fullPage: true });
    });
  }
}

test("keyboard reaches the theme toggle and toolbar with a visible focus ring", async ({ page }) => {
  await openDemo(page);
  const reached = new Set<string>();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return null;
      const style = getComputedStyle(el);
      const isThemeRadio = el instanceof HTMLInputElement && el.name === "theme";
      return { text: isThemeRadio ? "theme radio" : el.textContent?.trim() || el.tagName, outline: style.outlineStyle };
    });
    if (!info) continue;
    if (info.text === "Save model" || info.text === "theme radio") {
      expect(info.outline, `focus ring on ${info.text}`).not.toBe("none");
      reached.add(info.text);
    }
  }
  expect([...reached].sort()).toEqual(["Save model", "theme radio"]);
});

test("screenshot the reference model with a block selected", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open model" }).first().click();
  await page.getByRole("dialog").locator(".bm-list__item", { hasText: "SaaS company" }).getByRole("button").click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  await page.getByLabel("Find block").fill("Customer acquisition");
  await page.getByLabel("Find block").press("Enter");
  await expect(page.getByRole("heading", { name: "Customer acquisition cost (fully loaded)", exact: true, level: 2 })).toBeVisible();
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText("series<currency>");
  await page.screenshot({ path: `${SHOTS}/reference-inspector-1440.png`, fullPage: true });
});
