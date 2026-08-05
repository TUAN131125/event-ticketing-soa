import { test, expect } from '@playwright/test';
test('unauthenticated admin is directed to sign in', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: /run every event/i })).toBeVisible();
});

test('admin email and password share the same input treatment', async ({ page }) => {
  await page.goto('/login');
  const email = page.getByLabel('Email');
  const password = page.locator('input[name="password"]');
  await expect(email).toHaveClass(/ui-control/);
  await expect(password).toHaveClass(/ui-control/);
  const emailStyle = await email.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      borderWidth: style.borderWidth,
      borderStyle: style.borderStyle,
      borderRadius: style.borderRadius,
      height: style.height,
      paddingLeft: style.paddingLeft,
      backgroundColor: style.backgroundColor,
    };
  });
  const passwordStyle = await password.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      borderWidth: style.borderWidth,
      borderStyle: style.borderStyle,
      borderRadius: style.borderRadius,
      height: style.height,
      paddingLeft: style.paddingLeft,
      backgroundColor: style.backgroundColor,
    };
  });
  expect(emailStyle).toEqual(passwordStyle);
  expect(emailStyle.borderWidth).toBe('1px');
  expect(emailStyle.borderStyle).toBe('solid');
});
