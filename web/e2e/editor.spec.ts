import { expect, type Locator, type Page, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const node = (page: Page, title: string): Locator =>
  page.locator(".react-flow__node").filter({ has: page.locator(".bm-node__title", { hasText: title }) });

async function blankModel(page: Page) {
  await page.goto("/");
  await expect(page.getByText("Up to date")).toBeVisible();
  await page.getByRole("button", { name: "New model" }).click();
  await expect(page.getByRole("heading", { name: "Untitled model" })).toBeVisible();
}

async function dropFromPalette(page: Page, title: string, x: number, y: number) {
  const surface = page.locator(".bm-canvas__surface");
  await page.getByRole("button", { name: `Add ${title}`, exact: true }).dragTo(surface, { targetPosition: { x, y } });
  await expect(node(page, title)).toBeVisible();
}

async function nodeId(n: Locator): Promise<string> {
  return (await n.getAttribute("data-id")) as string;
}

test("build, wire, edit, undo, save and reopen a model", async ({ page }) => {
  await blankModel(page);
  await dropFromPalette(page, "Constant", 60, 40);
  await dropFromPalette(page, "Multiply", 400, 40);
  const constant = node(page, "Constant");
  const multiply = node(page, "Multiply");
  const multiplyId = await nodeId(multiply);

  // Set the constant's value in the inspector.
  await constant.click();
  const value = page.getByLabel("Value", { exact: true });
  await value.fill("3");
  await value.press("Enter");

  // Wire the constant into Multiply's a by dragging handle to handle.
  await constant.locator(".react-flow__handle.source").dragTo(multiply.locator('.react-flow__handle.target[data-handleid="a"]'));
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);

  // Set b inline; the server recomputes 3 * 4.
  await multiply.click();
  const b = page.getByLabel("Value of b");
  await b.fill("4");
  await b.press("Enter");
  const preview = page.getByTestId(`preview-${multiplyId}-result`);
  await expect(preview).toHaveText("12");

  // Undo restores b's default of 1; redo brings back 4.
  await page.locator(".bm-canvas__surface").click({ position: { x: 20, y: 20 } });
  await page.keyboard.press("Control+z");
  await expect(preview).toHaveText("3");
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(preview).toHaveText("12");

  // A refused connection explains itself.
  await dropFromPalette(page, "Period flag", 60, 200);
  await node(page, "Period flag").locator(".react-flow__handle.source").dragTo(multiply.locator('.react-flow__handle.target[data-handleid="b"]'));
  await expect(page.getByTestId("canvas-message")).toContainText("If block");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);

  // Save, then reopen from the server.
  await page.getByRole("button", { name: "Save model" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Open model" }).first().click();
  const dialog = page.getByRole("dialog");
  const saved = dialog.locator(".bm-list__item", { hasText: "Untitled model" }).first();
  await expect(saved).toBeVisible();
  await saved.getByRole("button", { name: "Open model" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId(`preview-${multiplyId}-result`)).toHaveText("12");

  // Export JSON downloads the model.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  expect((await download).suggestedFilename()).toBe("Untitled_model.json");
});

test("wire and delete with the keyboard only", async ({ page }) => {
  await blankModel(page);
  const filter = page.getByLabel("Filter blocks");
  await filter.focus();
  await page.keyboard.type("constant");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Add Constant" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(node(page, "Constant")).toBeVisible();

  await filter.fill("");
  await filter.focus();
  await page.keyboard.type("accumulate");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Add Accumulate" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(node(page, "Accumulate")).toBeVisible();

  // The new block is selected; wire its x from the constant with the "Wire x from" select.
  const wireFrom = page.getByLabel("Wire x from");
  await wireFrom.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await expect(wireFrom).toHaveValue(/:value$/);

  // Delete the selected block from the inspector with the keyboard.
  await page.getByRole("button", { name: "Delete block" }).focus();
  await page.keyboard.press("Enter");
  await expect(node(page, "Accumulate")).toHaveCount(0);
  await expect(page.locator(".react-flow__edge")).toHaveCount(0);
});

test("the reference model opens and evaluates without errors", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open model" }).first().click();
  await page.getByRole("dialog").locator(".bm-list__item", { hasText: "SaaS company" }).getByRole("button").click();
  await expect(page.getByRole("heading", { name: /saas_company/ })).toBeVisible();
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  await expect(page.locator(".react-flow__node")).toHaveCount(161);
  await expect(page.locator(".dt-tag--danger")).toHaveCount(0);
});

test("export all models downloads a backup zip with the saved model in it", async ({ page }) => {
  await blankModel(page);
  await page.getByRole("button", { name: "Save model" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  const json = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  const { id } = JSON.parse(readFileSync((await (await json).path()) as string, "utf8"));

  await page.getByRole("button", { name: "Open model" }).first().click();
  const dialog = page.getByRole("dialog");
  const zip = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Export all models" }).click();
  const file = await zip;
  expect(file.suggestedFilename()).toMatch(/^block-model-builder-backup-\d{8}-\d{6}\.zip$/);
  await expect(dialog.getByText(/^Downloaded block-model-builder-backup-/)).toBeVisible();
  // File names sit uncompressed in a zip's directory, so they can be checked without unzipping.
  const bytes = readFileSync((await file.path()) as string);
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
  expect(bytes.includes("manifest.json")).toBe(true);
  expect(bytes.includes(`models/${id}.json`)).toBe(true);
});
