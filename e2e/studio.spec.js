const { test, expect } = require("@playwright/test");
const fs = require("node:fs/promises");

async function generate(page) {
  await page.goto("/");
  await expect(page.locator("#mode")).toHaveText("DEMO MODE");
  await page
    .getByLabel("Story idea", { exact: true })
    .fill(
      "A young palace physician uncovers a secret plot against the emperor.",
    );
  await page.getByLabel("Output language").selectOption("English");
  await page.getByRole("button", { name: "Generate storyboard" }).click();
  await expect(page.locator(".scene")).toHaveCount(3);
  await expect(page.locator("#status")).toContainText("fixed sample");
}

test("generate, edit every scene field, export and reopen JSON", async ({
  page,
}) => {
  await generate(page);
  await page.getByLabel("PROJECT TITLE").fill("The physician’s choice");
  await page
    .getByLabel("Scene 1 narration", { exact: true })
    .fill("A revised opening with 中文.");
  await page
    .getByLabel("Scene 1 characters (one per line)", { exact: true })
    .fill("Doctor Mei\nLi Heng");
  await page
    .getByLabel("Scene 1 dialogue 1 speaker", { exact: true })
    .fill("Doctor Mei");
  await page
    .getByLabel("Scene 1 dialogue 1 line", { exact: true })
    .fill("The truth must be heard.");
  await page
    .getByLabel("Scene 1 visual prompt", { exact: true })
    .fill("Moonlit palace, silk hanfu, 9:16.");
  await page
    .getByLabel("Scene 1 camera description", { exact: true })
    .fill("Close-up on the letter.");
  await page.locator("#duration-1").fill("21");
  await page.locator("#duration-2").fill("19");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save JSON" }).click();
  const download = await downloadPromise;
  const saved = JSON.parse(await fs.readFile(await download.path(), "utf8"));
  expect(saved.title).toBe("The physician’s choice");
  expect(saved.scenes[0]).toMatchObject({
    duration: 21,
    narration: "A revised opening with 中文.",
    characters: ["Doctor Mei", "Li Heng"],
    dialogue: [{ character: "Doctor Mei", line: "The truth must be heard." }],
    visual_prompt: "Moonlit palace, silk hanfu, 9:16.",
    camera_description: "Close-up on the letter.",
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.locator("#file").setInputFiles({
    name: "project.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(saved)),
  });
  await expect(page.getByLabel("PROJECT TITLE")).toHaveValue(saved.title);
  await expect(
    page.getByLabel("Scene 1 narration", { exact: true }),
  ).toHaveValue(saved.scenes[0].narration);
  await expect(page.locator("#summary")).toHaveText("3 scenes · 60s / 60s");
});

test("invalid edits and JSON do not lose the current storyboard", async ({
  page,
}) => {
  await generate(page);
  await page.locator("#duration-1").fill("25");
  await page.getByRole("button", { name: "Save JSON" }).click();
  await expect(page.locator("#status")).toContainText("Cannot save");
  await expect(page.locator(".scene")).toHaveCount(3);
  page.on("dialog", (dialog) => dialog.accept());
  await page.locator("#file").setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from("{}"),
  });
  await expect(page.locator("#status")).toContainText("Cannot open project");
  await expect(page.locator("#duration-1")).toHaveValue("25");
});

test("dialogue can be added and removed", async ({ page }) => {
  await generate(page);
  const scene = page.locator(".scene").first();
  await scene.getByRole("button", { name: "Add dialogue" }).click();
  await expect(
    page.getByLabel("Scene 1 dialogue 2 line", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Remove dialogue 2 from scene 1" })
    .click();
  await expect(
    page.getByLabel("Scene 1 dialogue 2 line", { exact: true }),
  ).toHaveCount(0);
});

test("mobile layout has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await generate(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(page.getByRole("button", { name: "Save JSON" })).toBeVisible();
});

test("generation failures are actionable and permit retry", async ({
  page,
}) => {
  await page.goto("/");
  await page.route("**/api/storyboards", (route) =>
    route.fulfill({
      status: 504,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "The LLM request timed out. Please try again.",
      }),
    }),
  );
  await page
    .getByLabel("Story idea", { exact: true })
    .fill("A secret conspiracy within an ancient palace.");
  await page.getByRole("button", { name: "Generate storyboard" }).click();
  await expect(page.locator("#status")).toContainText("timed out");
  await expect(
    page.getByRole("button", { name: "Generate storyboard" }),
  ).toBeEnabled();
});
