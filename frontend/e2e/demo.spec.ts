// Needs: npx playwright install chromium. Not run in the authoring sandbox.
import { expect, test } from "@playwright/test";

test.describe("demo path (DEMO mode, fake camera)", () => {
  test.use({ permissions: ["camera", "microphone"] });

  test("guest -> session -> observation -> step -> verification decision -> history -> handoff", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /continue as guest/i }).click();
    await expect(page.getByText(/DEMO MODE/)).toBeVisible();                      // demo is visibly labelled
    await page.getByRole("button", { name: /start a new session/i }).click();
    await page.getByRole("button", { name: /start camera/i }).click();
    await page.getByRole("button", { name: /capture frame/i }).click();
    await page.getByLabel("Your message").fill("My internet is not working and the router light is orange.");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText("[Simulated demo]").first()).toBeVisible();
    await page.getByLabel("Your message").fill("Beginner. Here is the router.");
    await page.getByRole("button", { name: /capture frame/i }).click();
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(/Verified on camera:/)).toBeVisible();
    await page.getByRole("button", { name: /i've done this step/i }).click();
    await expect(page.getByText(/not verified|Demo only/i).first()).toBeVisible();   // never claims verification in demo
    await page.getByRole("button", { name: /end & review session/i }).click();
    await expect(page.getByText("Transcript")).toBeVisible();
    await page.getByRole("button", { name: /preview report/i }).click();
    await expect(page.getByText(/unconfirmed/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /download \.md/i })).toBeDisabled();   // needs explicit consent
  });

  test("hazard text triggers a safety stop", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /continue as guest/i }).click();
    await page.getByRole("button", { name: /start a new session/i }).click();
    await page.getByLabel("Your message").fill("I can smell gas near the stove");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(/Safety stop/)).toBeVisible();
  });
});

test("camera permission denied shows a clear error", async ({ browser }) => {
  const ctx = await browser.newContext({ permissions: [] });
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("denied", "NotAllowedError"));
  });
  await page.goto("/");
  await page.getByRole("button", { name: /continue as guest/i }).click();
  await page.getByRole("button", { name: /start a new session/i }).click();
  await page.getByRole("button", { name: /start camera/i }).click();
  await expect(page.getByRole("alert").filter({ hasText: /permission was denied/i })).toBeVisible();
  await page.getByRole("button", { name: "Speak" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /microphone permission was denied/i })).toBeVisible();
  await expect(page.getByLabel("Your message")).toBeEnabled();                     // typed fallback still works
});
