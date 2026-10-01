import { expect, type Page, test } from "@playwright/test";

async function openReference(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open model" }).first().click();
  await page.getByRole("dialog").locator(".bm-list__item", { hasText: "SaaS company" }).getByRole("button").click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
}

test("the reference model's summary shows its headline values and exports", async ({ page }) => {
  await openReference(page);
  await page.getByRole("tab", { name: "Summary" }).click();
  const single = page.getByRole("region", { name: "Single values" });
  await expect(single.getByRole("row", { name: /^NPV/ })).toContainText("$51,239,655");
  await expect(single.getByRole("row", { name: /IRR/ })).toContainText("53.4%");
  const perPeriod = page.getByRole("region", { name: "Per period" });
  await expect(perPeriod.getByRole("columnheader", { name: "2034Q4" })).toBeVisible();
  await expect(page.getByText("Sample data", { exact: true }).last()).toBeVisible();

  const xlsx = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export XLSX" }).click();
  expect((await xlsx).suggestedFilename()).toBe("Reference_model__saas_company.xlsx");
  const csv = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await csv).suggestedFilename()).toBe("Reference_model__saas_company.csv");
});

test("add, rename, reorder and remove summary rows", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("compute-state")).toHaveText("Up to date");
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByText("The summary is empty.")).toBeVisible();

  await page.getByRole("tab", { name: "Diagram" }).click();
  for (const name of ["Total revenue", "Product revenue"]) {
    await page.getByLabel("Find block").fill(name);
    await page.getByLabel("Find block").press("Enter");
    await page.getByRole("button", { name: "Add to summary" }).click();
    await expect(page.getByRole("button", { name: "Remove from summary" })).toBeVisible();
  }

  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByTestId("summary-row-0")).toContainText("Total revenue");
  await expect(page.getByTestId("summary-row-0")).toContainText("$650");
  await page.getByText("Edit summary rows").click();
  await page.getByRole("button", { name: "Move up" }).nth(1).click();
  await expect(page.getByTestId("summary-row-0")).toContainText("Product revenue");
  const label = page.getByLabel("Row 1 label");
  await label.fill("Revenue from units");
  await label.press("Enter");
  await expect(page.getByTestId("summary-row-0")).toContainText("Revenue from units");
  await page.getByRole("button", { name: "Remove row" }).first().click();
  await expect(page.getByTestId("summary-row-0")).toContainText("Total revenue");
});

test("phone view reads the summary without editing controls", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await openReference(page);
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByRole("region", { name: "Single values" }).getByRole("row", { name: /^NPV/ })).toContainText("$51,239,655");
  await expect(page.getByRole("button", { name: "Save model" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Move up" })).toHaveCount(0);
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth, "the table scrolls inside its container, not the page").toBeLessThanOrEqual(375);
  await page.screenshot({ path: "e2e-screens/summary-375.png", fullPage: true });
});

test("screenshot the summary on desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await openReference(page);
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByRole("region", { name: "Single values" })).toBeVisible();
  await page.screenshot({ path: "e2e-screens/summary-1280.png", fullPage: true });
});
