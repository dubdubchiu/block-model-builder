import { expect, type Page, test } from "@playwright/test";

async function openExample(page: Page, text: string) {
  await page.goto("/");
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  await page.getByRole("button", { name: "Open model" }).first().click();
  await page.getByRole("dialog").locator(".bm-list__item", { hasText: text }).getByRole("button").click();
  // The dialog closes once the model has loaded; only then does "Up to date" describe it.
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
}

async function find(page: Page, label: string) {
  await page.getByLabel("Find block").fill(label);
  await page.getByLabel("Find block").press("Enter");
}

const npvRow = (page: Page) => page.getByRole("region", { name: "Single values" }).getByRole("row", { name: /^NPV/ });

test("switch and compare scenarios on the reference model", async ({ page }) => {
  await openExample(page, "SaaS company");
  await expect(page.locator(".dt-tag--danger")).toHaveCount(0);
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(npvRow(page)).toContainText("$51,239,655");

  await page.getByLabel("Scenario", { exact: true }).selectOption({ label: "High average revenue per account (monthly)" });
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  await expect(npvRow(page)).not.toContainText("$51,239,655");
  await page.getByLabel("Compare with").selectOption({ label: "Base case" });
  const comparison = page.getByRole("region", { name: "Scenario comparison" });
  await expect(comparison.getByRole("row", { name: /^NPV/ })).toContainText("$51,239,655");
  await page.screenshot({ path: "e2e-screens/scenario-compare-1280.png", fullPage: true });
});

test("values edited in a scenario override only that scenario", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  const product = page.locator('[data-testid="preview-5c818392-f705-482c-a78b-cae77ebfc7ed-result"]');
  await expect(product).toHaveText("500, 550, 600, … (8 periods)");

  await page.getByRole("button", { name: "New scenario" }).click();
  await find(page, "Price per unit");
  const value = page.getByLabel("Value", { exact: true });
  await value.fill("20");
  await value.press("Enter");
  await expect(page.getByText("Overridden")).toBeVisible();
  await expect(product).toHaveText("800, 880, 960, … (8 periods)");

  await page.getByLabel("Scenario", { exact: true }).selectOption({ label: "Base case" });
  await expect(product).toHaveText("500, 550, 600, … (8 periods)");
});

test("group blocks into a subsystem, edit inside, and ungroup", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  const nodes = page.locator(".react-flow__node");
  await nodes.filter({ hasText: "Product revenue" }).click();
  await nodes.filter({ hasText: "Total revenue" }).click({ modifiers: ["Control"] });
  await page.getByRole("button", { name: "Group into subsystem" }).click();
  await expect(nodes).toHaveCount(3);
  const instance = nodes.filter({ hasText: "Subsystem 1" });
  await expect(instance).toContainText("650, 700, 750");

  await page.getByRole("button", { name: "Open subsystem" }).click();
  await expect(page.getByRole("heading", { name: "Inside Subsystem 1" })).toBeVisible();
  await expect(nodes).toHaveCount(2);
  await expect(nodes.filter({ hasText: "Total revenue" })).toContainText("650, 700, 750");
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  await page.screenshot({ path: "e2e-screens/subsystem-inside-1280.png", fullPage: true });

  // Edit inside: other income 150 -> 250 changes the instance's output.
  await nodes.filter({ hasText: "Total revenue" }).click();
  const b = page.getByLabel("Value of b");
  await b.fill("250");
  await b.press("Enter");
  await expect(nodes.filter({ hasText: "Total revenue" })).toContainText("750, 800, 850");
  await page.getByRole("button", { name: "Back to model" }).first().click();
  await expect(instance).toContainText("750, 800, 850");

  await instance.click();
  await page.getByRole("button", { name: "Ungroup" }).click();
  await expect(nodes).toHaveCount(4);
  await expect(page.locator(".dt-tag--danger")).toHaveCount(0);
});

test("the feedback example solves its loop", async ({ page }) => {
  await openExample(page, "feedback loop");
  await expect(page.locator(".dt-tag--danger")).toHaveCount(0);
  await find(page, "Cash at end of quarter");
  await expect(page.getByRole("region", { name: "Inspector" })).toContainText("1,958,920.64");
});
