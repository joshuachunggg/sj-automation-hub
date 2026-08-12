import { chromium } from 'playwright-core';

const browser = await chromium.connectOverCDP(process.env.CDP || "http://127.0.0.1:9223");
const context = browser.contexts()[0];
const page = await context.newPage();
const hosts = [
  "https://p6spp-ap-author.samsung.com",
  "https://p6spp-eu-author.samsung.com",
  "https://p6spp-us-author.samsung.com",
];

if (await Promise.all(hosts.map(host => signedIn(context, host))).then(results => results.every(Boolean))) {
  console.log("AEM SESSION READY");
  process.exit(0);
}
console.log("AEM SESSION MISSING - starting WMC login");

for (const name of ["WMC_LOGIN_URL", "WMC_USERNAME", "WMC_PASSWORD"]) {
  if (!process.env[name]) throw new Error(`No AEM session and missing ${name} in .env`);
}
await page.goto(process.env.WMC_LOGIN_URL, { waitUntil: "domcontentloaded" });
const wmcSession = await waitForWmcState(page);
if (!wmcSession) {
  await page.getByRole("textbox", { name: "Login ID (e-mail)" }).fill(process.env.WMC_USERNAME);
  await page.getByRole("textbox", { name: "Password" }).fill(process.env.WMC_PASSWORD);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
}
console.log(wmcSession ? "MFA CHECK" : "MFA READY");
await new Promise(resolve => process.stdin.once("data", resolve));
await page.goto("https://wds.samsung.com/wds/sso/login/ssoLoginSuccess.do", { waitUntil: "domcontentloaded", timeout: 15000 });

for (const host of hosts) {
  const support = await context.newPage();
  try {
    const response = await support.goto(`${host}/aemapi/user/login_sso`, { waitUntil: "load", timeout: 30000 });
    if (!response?.ok()) throw new Error(`Support activation failed for ${host}`);
    await support.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  } finally {
    await support.close();
  }
}

console.log("AEM SESSION READY");

async function signedIn(context, host) {
  const probe = await context.newPage();
  try {
    const response = await probe.goto(`${host}/libs/cq/security/userinfo.json`, { waitUntil: "domcontentloaded", timeout: 15000 });
    const user = await response?.json().catch(() => null);
    return response?.ok() && user?.userID && user.userID !== "anonymous";
  } catch {
    return false;
  } finally {
    await probe.close();
  }
}

async function waitForWmcState(page) {
  const home = page.getByText(/^Hi,/).first();
  const email = page.getByRole("textbox", { name: "Login ID (e-mail)" });
  const loginLink = page.getByRole("row", { name: /To login/i }).getByRole("link");
  const loginButton = page.locator("#loginButton");
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await home.isVisible().catch(() => false)) return true;
    if (await email.isVisible().catch(() => false)) return false;
    if (await loginLink.isVisible().catch(() => false)) {
      await loginLink.click();
      continue;
    }
    if (await loginButton.isVisible().catch(() => false)) {
      await loginButton.click();
      continue;
    }
    await page.waitForTimeout(250);
  }
  throw new Error("WMC did not show a signed-in homepage or login form");
}
