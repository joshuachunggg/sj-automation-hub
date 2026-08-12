import { chromium } from 'playwright-core';

const required = ["WMC_LOGIN_URL", "WMC_USERNAME", "WMC_PASSWORD"];
for (const name of required) {
  if (!process.env[name]) throw new Error(`Missing ${name} in .env`);
}

const browser = await chromium.connectOverCDP(process.env.CDP || "http://127.0.0.1:9222");
const context = browser.contexts()[0];
const page = await context.newPage();

await page.goto(process.env.WMC_LOGIN_URL, { waitUntil: "domcontentloaded" });
if (await page.getByText(/^Hi,/).first().isVisible().catch(() => false)) {
  console.log("WMC SESSION READY");
  await page.close();
  process.exit(0);
}

const loginLink = page.getByRole("row", { name: /To login/i }).getByRole("link");
if (await loginLink.isVisible().catch(() => false)) await loginLink.click();
await page.locator("#loginButton").click();
await page.getByRole("textbox", { name: "Login ID (e-mail)" }).fill(process.env.WMC_USERNAME);
await page.getByRole("textbox", { name: "Password" }).fill(process.env.WMC_PASSWORD);
await page.getByRole("button", { name: "Sign In", exact: true }).click();

console.log("MFA READY");
await new Promise(resolve => process.stdin.once("data", resolve));
await page.goto("https://wds.samsung.com/wds/sso/login/ssoLoginSuccess.do", { waitUntil: "domcontentloaded" });
await page.getByText(/^Hi,/).first().click().catch(() => {});
const support = page.getByRole("link", { name: "Support" }).first();
if (await support.isVisible().catch(() => false)) await support.click();
console.log("WMC LOGIN READY");
