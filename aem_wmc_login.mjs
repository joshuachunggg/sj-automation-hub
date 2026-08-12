import { chromium } from 'playwright-core';

const editorUrl = process.argv.at(-1);
if (!editorUrl?.startsWith("https://")) throw new Error("Missing --editor-url");

const browser = await chromium.connectOverCDP(process.env.CDP || "http://127.0.0.1:9222");
const context = browser.contexts()[0];
const page = await context.newPage();

const author = new URL(editorUrl).origin;
const session = await page.goto(`${author}/libs/cq/security/userinfo.json`, { waitUntil: "domcontentloaded", timeout: 15000 }).catch(() => null);
const user = await session?.json().catch(() => null);
if (session?.ok() && user?.userID && user.userID !== "anonymous") {
  await page.goto(editorUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
  console.log("AEM SESSION READY");
  process.exit(0);
}
console.log("AEM SESSION MISSING - starting WMC login");

for (const name of ["WMC_LOGIN_URL", "WMC_USERNAME", "WMC_PASSWORD"]) {
  if (!process.env[name]) throw new Error(`No AEM session and missing ${name} in .env`);
}
await page.goto(process.env.WMC_LOGIN_URL, { waitUntil: "domcontentloaded" });
if (!await page.getByText(/^Hi,/).first().isVisible().catch(() => false)) {
  const loginLink = page.getByRole("row", { name: /To login/i }).getByRole("link");
  if (await loginLink.isVisible().catch(() => false)) await loginLink.click();
  await page.locator("#loginButton").click();
  await page.getByRole("textbox", { name: "Login ID (e-mail)" }).fill(process.env.WMC_USERNAME);
  await page.getByRole("textbox", { name: "Password" }).fill(process.env.WMC_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  console.log("MFA READY");
  await new Promise(resolve => process.stdin.once("data", resolve));
  await page.goto("https://wds.samsung.com/wds/sso/login/ssoLoginSuccess.do", { waitUntil: "domcontentloaded", timeout: 15000 });
}

for (const host of [
  "https://p6spp-ap-author.samsung.com",
  "https://p6spp-eu-author.samsung.com",
  "https://p6spp-us-author.samsung.com",
]) {
  const support = await context.newPage();
  try {
    const response = await support.goto(`${host}/aemapi/user/login_sso`, { waitUntil: "domcontentloaded", timeout: 15000 });
    if (!response?.ok()) throw new Error(`Support activation failed for ${host}`);
  } finally {
    await support.close();
  }
}

await page.goto(editorUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
console.log("AEM SESSION READY");
