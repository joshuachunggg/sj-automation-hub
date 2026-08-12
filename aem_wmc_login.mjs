import { chromium } from 'playwright-core';

const browser = await chromium.connectOverCDP(process.env.CDP || "http://127.0.0.1:9223");
const context = browser.contexts()[0];
const page = await context.newPage();

for (const name of ["WMC_LOGIN_URL", "WMC_USERNAME", "WMC_PASSWORD"]) {
  if (!process.env[name]) throw new Error(`Missing ${name} in .env`);
}
await page.goto(process.env.WMC_LOGIN_URL, { waitUntil: "domcontentloaded" });
const wmcSession = await waitForWmcState(page);
if (!wmcSession) {
  await page.getByRole("textbox", { name: "Login ID (e-mail)" }).fill(process.env.WMC_USERNAME);
  await page.getByRole("textbox", { name: "Password" }).fill(process.env.WMC_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
}
console.log("SERVER SETUP READY");
await new Promise(resolve => process.stdin.once("data", resolve));
console.log("AEM SESSION READY");
process.exit(0);

async function waitForWmcState(page) {
  const home = page.getByText(/^Hi,/).first();
  const email = page.getByRole("textbox", { name: "Login ID (e-mail)" });
  const loginLink = page.getByRole("row", { name: /To login/i }).getByRole("link");
  const loginButton = page.locator("#loginButton");
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await home.isVisible().catch(() => false)) return true;
    if (await email.isVisible().catch(() => false)) return false;
    if (await loginButton.isVisible().catch(() => false)) {
      await loginButton.click({ force: true, timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(500);
      continue;
    }
    if (await loginLink.isVisible().catch(() => false)) {
      await loginLink.click({ force: true, timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(500);
      continue;
    }
    await page.waitForTimeout(250);
  }
  throw new Error("WMC did not show a signed-in homepage or login form");
}
