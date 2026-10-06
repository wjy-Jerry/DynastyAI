const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");
const path = require("node:path");

async function createProject(page) {
  await page.goto("/");
  await page
    .getByLabel("Story idea", { exact: true })
    .fill(
      "A young palace physician discovers a conspiracy against the emperor.",
    );
  await page.getByLabel("Output language").selectOption("English");
  await page.getByRole("button", { name: "Generate storyboard" }).click();
  await expect(page.locator(".scene")).toHaveCount(3);
}

test("character and style edits refresh all shared character prompts", async ({
  page,
}) => {
  await createProject(page);
  const first = page.getByLabel("Scene 1 final image prompt (sent verbatim)");
  const third = page.getByLabel("Scene 3 final image prompt (sent verbatim)");
  await expect(first).toHaveValue(/Facial features: Oval face/);
  await expect(third).toHaveValue(/Facial features: Oval face/);
  await page
    .getByLabel("shen-yue Facial features")
    .fill("Distinctive star-shaped mark on left cheek");
  await page
    .getByLabel("Historical era / dynasty")
    .fill("Fictional Song-inspired court");
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Refresh prompts" }).click();
  await expect(first).toHaveValue(/Distinctive star-shaped mark on left cheek/);
  await expect(third).toHaveValue(/Distinctive star-shaped mark on left cheek/);
  await expect(first).toHaveValue(/Fictional Song-inspired court/);
  await expect(page.locator("#status")).toContainText("prompts refreshed");
});

test("new scene character creates one editable Bible entry", async ({
  page,
}) => {
  await createProject(page);
  const names = page.getByLabel("Scene 1 characters (one per line)");
  await names.fill("Shen Yue\nLi Heng\n");
  await names.pressSequentially("Doctor Mei", { delay: 5 });
  await page.getByLabel("Scene 1 narration", { exact: true }).click();
  await expect(page.locator(".character-card")).toHaveCount(3);
  await expect(page.getByLabel(/character-[a-z0-9]+ Appearance/)).toHaveValue(
    /unspecified/,
  );
  await page.getByLabel("shen-yue Name").fill("Physician Shen");
  await expect(names).toHaveValue(/Physician Shen/);
  await expect(page.getByLabel("Scene 1 dialogue 1 speaker")).toHaveValue(
    "Physician Shen",
  );
});

test("generate all mock images, regenerate one, and preserve metadata in JSON", async ({
  page,
}) => {
  await createProject(page);
  await expect(page.locator("#image-mode")).toContainText("MOCK MODE");
  await page.getByRole("button", { name: "Generate All Scene Images" }).click();
  await expect(page.locator(".image-preview img")).toHaveCount(3);
  await expect(page.locator(".image-caption").first()).toContainText(
    "NOT AI GENERATED",
  );
  await expect(page.locator("#status")).toContainText(
    "3 of 3 scene images ready",
  );
  const before = await page
    .locator(".image-preview img")
    .evaluateAll((images) => images.map((image) => image.getAttribute("src")));
  await page
    .getByRole("button", { name: "Regenerate Image for scene 2" })
    .click();
  await expect
    .poll(() => page.locator(".image-preview img").nth(1).getAttribute("src"))
    .not.toBe(before[1]);
  const after = await page
    .locator(".image-preview img")
    .evaluateAll((images) => images.map((image) => image.getAttribute("src")));
  expect(after[0]).toBe(before[0]);
  expect(after[2]).toBe(before[2]);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save JSON" }).click();
  const download = await downloadPromise;
  const saved = JSON.parse(await fs.readFile(await download.path(), "utf8"));
  expect(saved.schema_version).toBe("2.0");
  expect(saved.character_bible).toHaveLength(2);
  expect(saved.visual_style.aspect_ratio).toBe("9:16");
  expect(saved.scenes[1].image_asset.url).toBe(after[1]);
  page.on("dialog", (dialog) => dialog.accept());
  await page.locator("#file").setInputFiles({
    name: "project.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(saved)),
  });
  await expect(page.locator(".image-preview img")).toHaveCount(3);
  await expect(page.locator(".image-preview img").nth(1)).toHaveAttribute(
    "src",
    after[1],
  );
});

test("old Phase 1 JSON migrates with explicit review message", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator("#file")
    .setInputFiles(path.join(__dirname, "../examples/demo-project.json"));
  await expect(page.locator(".scene")).toHaveCount(3);
  await expect(page.locator("#status")).toContainText(
    "Phase 1 project migrated to v2",
  );
  await expect(page.getByLabel("character-1 Appearance")).toHaveValue(
    /unspecified/,
  );
  await expect(page.locator("#image-mode")).toContainText("MOCK MODE");
});

test("one scene failure is visible and can be retried", async ({ page }) => {
  await createProject(page);
  let failed = false;
  await page.route("**/api/images/scenes/2", async (route) => {
    if (!failed) {
      failed = true;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Provider busy; retry this scene." }),
      });
    } else {
      await route.continue();
    }
  });
  await page.getByRole("button", { name: "Generate All Scene Images" }).click();
  await expect(page.locator("#scene-status-2")).toContainText("Provider busy");
  await expect(page.locator(".image-preview img")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Generate Image for scene 2" })
    .click();
  await expect(page.locator(".image-preview img")).toHaveCount(3);
});

test("mobile image previews stay within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await createProject(page);
  await page
    .getByRole("button", { name: "Generate Image for scene 1" })
    .click();
  await expect(page.locator(".image-preview img").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
