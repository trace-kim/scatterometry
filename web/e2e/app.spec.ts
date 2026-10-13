import { expect, type Page, test } from "@playwright/test";

// Console noise from libraries that is not an application error.
const IGNORED = [/THREE\.Clock: This module has been deprecated/];

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !IGNORED.some((p) => p.test(message.text()))) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  return errors;
}

async function openTab(page: Page, title: string) {
  await page.locator(".dv-tab", { hasText: title }).click();
}

async function loadPreset(page: Page, name: RegExp) {
  await page.getByRole("button", { name: "File" }).click();
  await page.getByRole("menuitem", { name }).click();
  // Earlier toasts may still be on screen; wait for this preset's.
  await expect(page.getByText(new RegExp(`Loaded preset .*${name.source}`)).first()).toBeVisible();
}

test("solves the default preset and renders every view without errors", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await expect(page.getByText("Layers (incident side first)")).toBeVisible();

  // Geometry needs no solve: the cross-section and 3D view render straight away.
  await expect(page.getByText("Cross-section", { exact: true })).toBeVisible();
  await expect(page.locator("section", { hasText: "3D stack" }).locator("canvas")).toBeVisible();

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Solved in/)).toBeVisible({ timeout: 60_000 });

  await openTab(page, "Diffraction");
  await expect(page.getByText("R total (TE)")).toBeVisible();
  await expect(page.locator(".ag-row").first()).toBeVisible();

  await openTab(page, "Near field");
  await expect(page.getByText("Field cross-section")).toBeVisible();
  await expect(page.locator("section", { hasText: "Field cross-section" }).locator("canvas").first()).toBeVisible();

  await openTab(page, "Dielectric ε");
  await expect(page.getByText(/Convolution matrix/)).toBeVisible();

  await openTab(page, "Python views");
  await expect(page.getByText("Fourier spectrum of ε (first patterned slice)").last()).toBeVisible();
  await expect(page.locator("section", { hasText: "Fourier spectrum" }).locator("canvas").first()).toBeVisible();

  await page.waitForTimeout(500);
  expect(errors).toEqual([]);
});

test("stack edits update the views and undo restores them", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  const thickness = page.locator('.ag-row[row-index="0"] [col-id="thickness_nm"]');
  await expect(thickness).toHaveText("60");

  await thickness.dblclick();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("75");
  await page.keyboard.press("Enter");
  await expect(thickness).toHaveText("75");
  // The stack summary follows the edit: 75 + 2.5 + 40 x 6.89 nm.
  await expect(page.getByText("353.1 nm")).toBeVisible();

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(thickness).toHaveText("60");
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(thickness).toHaveText("75");
  expect(errors).toEqual([]);
});

test("contact holes solve in 2D and a sweep streams its points", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await loadPreset(page, /contact holes/);

  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Solved in/)).toBeVisible({ timeout: 90_000 });
  await openTab(page, "Near field");
  await expect(page.getByText("Field top view")).toBeVisible();

  await loadPreset(page, /L\/S on Ru/);
  await openTab(page, "Sweep");
  await page.getByRole("button", { name: "Run sweep" }).click();
  await expect(page.getByText(/Finished in/)).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/13 of 13 points/)).toBeVisible();
  expect(errors).toEqual([]);
});
