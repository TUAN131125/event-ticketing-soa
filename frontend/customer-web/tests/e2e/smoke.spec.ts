import { test, expect } from "@playwright/test";
test("event discovery remains honest when ESB is unavailable", async ({
  page,
}) => {
  await page.goto("/events");
  await expect(
    page.getByRole("heading", { name: /events worth showing up for/i }),
  ).toBeVisible();
  await expect(
    page.getByText(/event services are unavailable|no events found/i),
  ).toBeVisible({ timeout: 10000 });
});
test("protected bookings route sends guests to sign in", async ({ page }) => {
  await page.goto("/bookings");
  await expect(page).toHaveURL(/\/login\?next=/);
});

for (const route of ["/login", "/register"]) {
  test(`${route} keeps auth controls inside a padded card`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(route);
    const card = page.locator(".auth-card");
    await expect(card).toBeVisible();
    const padding = await card.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).paddingLeft),
    );
    expect(padding).toBeGreaterThanOrEqual(24);
    await expect(page.getByLabel("Email")).toHaveClass(/ui-control/);
    await expect(page.locator('input[name="password"]')).toHaveClass(
      /ui-control/,
    );
  });
}
