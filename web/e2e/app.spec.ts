import path from "node:path";
import { expect, type Page, test } from "@playwright/test";

// Console noise from libraries that is not an application error.
const IGNORED = [/THREE\.Clock: This module has been deprecated/];

function collectErrors(page: Page, expected: RegExp[] = []): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error" && ![...IGNORED, ...expected].some((p) => p.test(text))) errors.push(text);
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  return errors;
}

async function openTab(page: Page, title: string) {
  await page.locator(".dv-tab", { hasText: title }).click();
}

// The top bar's Run button (the setup panel's footer has one too).
const runButton = (page: Page) => page.getByRole("banner").getByRole("button", { name: "Run", exact: true });

async function loadPreset(page: Page, name: RegExp) {
  await page.getByRole("button", { name: "File" }).click();
  await page.getByRole("menuitem", { name }).click();
  // Earlier toasts may still be on screen; wait for this preset's.
  await expect(page.getByText(new RegExp(`Loaded preset .*${name.source}`)).first()).toBeVisible();
}

test("solves the default preset and renders every view without errors", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^Layer stack/ })).toBeVisible();

  // Geometry needs no solve: the cross-section and 3D view render straight away.
  await expect(page.getByText("Cross-section", { exact: true })).toBeVisible();
  await expect(page.locator("section", { hasText: "3D stack" }).locator("canvas")).toBeVisible();

  await runButton(page).click();
  await expect(page.getByText(/Solved in/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("The results match this setup.")).toBeVisible();

  await openTab(page, "Diffraction");
  await expect(page.getByText("R total (TE)")).toBeVisible();
  await expect(page.locator(".ag-row").first()).toBeVisible();

  // The Pupil card's camera mode projects the same orders onto a sensor.
  const pupilCard = page.locator("section", { has: page.getByRole("group", { name: "Pupil view" }) });
  await pupilCard.getByRole("button", { name: "Camera", exact: true }).click();
  await expect(pupilCard.getByText(/orders on the sensor/)).toBeVisible();
  await expect(pupilCard.getByRole("textbox", { name: "Camera distance" })).toBeVisible();
  await expect(pupilCard.locator("canvas").first()).toBeVisible();
  // The mode is remembered, and the chart must render before the pupil data arrives.
  await page.reload();
  await expect(pupilCard.getByText(/orders on the sensor/)).toBeVisible();
  await pupilCard.getByRole("button", { name: "Pupil", exact: true }).click();
  await expect(pupilCard.getByText(/color = phase/)).toBeVisible();

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
  const thickness = page.getByRole("textbox", { name: "Thickness of Absorber" });
  await expect(thickness).toHaveValue("60");

  await thickness.fill("75");
  await thickness.press("Enter");
  await expect(thickness).toHaveValue("75");
  // The stack summary follows the edit: 75 + 2.5 + 40 x 6.89 nm.
  await expect(page.getByText("353.1 nm")).toBeVisible();

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(thickness).toHaveValue("60");
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(thickness).toHaveValue("75");
  expect(errors).toEqual([]);
});

test("the setup panel keeps groups intact, warns, and explains what blocks a run", async ({ page }) => {
  // An invalid project makes the view endpoints answer 422 until the views catch up.
  const errors = collectErrors(page, [/status of 422/]);
  await page.goto("/");
  const footer = page.locator("footer");
  await expect(footer.getByText("Ready to run.")).toBeVisible();

  // Moving a layer down steps over the whole Mo/Si group instead of splitting it.
  const names = page.getByRole("textbox", { name: /^Name of (?!the repeat group)/ });
  const order = () =>
    names.evaluateAll((inputs) => inputs.map((input) => (input as unknown as { value: string }).value));
  await page.getByRole("button", { name: "More actions for Cap" }).click();
  await page.getByRole("menuitem", { name: "Move down" }).click();
  await expect.poll(order).toEqual(["Absorber", "ML Si", "ML Mo", "Cap"]);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect.poll(order).toEqual(["Absorber", "Cap", "ML Si", "ML Mo"]);

  // Too few Fourier orders for the 19 propagating ones: a warning, not a blocker.
  const orders = page.getByRole("textbox", { name: "Fourier orders N" });
  await orders.fill("5");
  await orders.press("Enter");
  await expect(page.getByText("orders cut off")).toBeVisible();
  // m = −8 … 10 at 6°: the pupil-centred window (centre m = 1) reaches them all with N = 9.
  await expect(page.getByText(/Use N ≥ 9\./)).toBeVisible();
  await expect(runButton(page)).toBeEnabled();

  // An invalid layer blocks the run, and the footer says why.
  const thickness = page.getByRole("textbox", { name: "Thickness of Absorber" });
  await thickness.fill("0");
  await thickness.press("Enter");
  await expect(footer.getByRole("button", { name: "Layer 'Absorber' needs a positive thickness." })).toBeVisible();
  await expect(footer.getByRole("button", { name: "Run", exact: true })).toBeDisabled();
  await expect(runButton(page)).toBeDisabled();

  await page.getByRole("button", { name: "Undo" }).click();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(footer.getByText("Ready to run.")).toBeVisible();
  await expect(page.getByText("orders cut off")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("contact holes solve in 2D and a sweep streams its points", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await loadPreset(page, /contact holes/);

  await runButton(page).click();
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

test("opens a measured CCD file and browses its frames", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await openTab(page, "Measurement");
  await expect(page.getByText("No measurement open")).toBeVisible();

  // fixtures/ccd-demo.spe: masksim.spe.write_spe of 3 frames, 160 x 120 px binned 2 x 2 at
  // sensor pixel (512, 600), five diffraction-like spots, one saturated pixel in frame 2.
  await page.getByTestId("measurement-file").setInputFiles(path.join(import.meta.dirname, "fixtures", "ccd-demo.spe"));
  await expect(page.getByText("Opened ccd-demo.spe")).toBeVisible();
  const frameCard = page.locator("section", { has: page.getByRole("heading", { name: "Frame", exact: true }) });
  await expect(frameCard.getByText(/160 × 120 px · frame 1 of 3 · uint16 · binned 2×2/)).toBeVisible();
  await expect(frameCard.locator("canvas").first()).toBeVisible();
  await expect(page.getByText("Sensor temperature")).toBeVisible();
  await expect(page.getByText("-70.0 °C").first()).toBeVisible();

  // Frame 2 holds a saturated pixel; the mean of all frames is float data without saturation.
  const frameNumber = page.getByRole("textbox", { name: "Frame number" });
  await frameNumber.fill("2");
  await frameNumber.press("Enter");
  await expect(page.getByText("1 saturated px")).toBeVisible();
  await page.getByRole("switch", { name: "Mean of all frames" }).click();
  await expect(frameCard.getByText(/mean of 3 frames · float32/)).toBeVisible();
  await expect(page.getByText(/saturated px/)).toHaveCount(0);

  // Every setting the file records is searchable.
  await page.getByRole("textbox", { name: "Filter settings" }).fill("exposuretime");
  await expect(page.locator(".ag-row")).toHaveCount(1);
  await expect(page.locator(".ag-row").first()).toContainText("20");

  await page.getByRole("button", { name: "Remove file" }).click();
  await expect(page.getByText("No measurement open")).toBeVisible();
  expect(errors).toEqual([]);
});
