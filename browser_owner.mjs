import net from 'node:net';
import { readFileSync } from 'node:fs';
import { firefox } from 'playwright';
import { openTab, closeTab } from './aem_browser.mjs';

const profile = process.env.AEM_PROFILE || '.firefox-profile';
const env = Object.fromEntries(readFileSync('.env', 'utf8').split(/\r?\n/).map(line => line.split(/=(.*)/s)).filter(([k]) => k));
const context = await firefox.launchPersistentContext(profile, { headless: false, args: ['--allow-downgrade'] });
let home = context.pages()[0] || await context.newPage(), reviewPage;
const server = net.createServer(socket => {
  let text = '';
  socket.on('data', async chunk => {
    text += chunk;
    while (text.includes('\n')) {
      const line = text.slice(0, text.indexOf('\n')); text = text.slice(text.indexOf('\n') + 1);
      try { socket.write(JSON.stringify({ ok: true, result: await handle(JSON.parse(line)) }) + '\n'); }
      catch (error) { socket.write(JSON.stringify({ ok: false, error: error.stack || String(error) }) + '\n'); }
    }
  });
});
server.listen(8766, '127.0.0.1');

async function handle(request) {
  if (request.action === 'login') return login();
  if (request.action === 'done') return true;
  if (request.action === 'open') return openEditor(request.url);
  if (request.action === 'audit') return audit(request);
  if (request.action === 'copy') return copy(request);
  throw new Error(`Unknown browser action: ${request.action}`);
}
async function openEditor(url) {
  reviewPage = await context.newPage();
  await reviewPage.goto(url, { waitUntil: 'domcontentloaded' });
  await reviewPage.bringToFront();
  return true;
}
async function login() {
  await home.goto('https://wds.samsung.com/wds/sso/login/forwardLogin.do', { waitUntil: 'domcontentloaded' });
  const support = home.getByRole('link', { name: 'Support' }).first();
  if (await support.isVisible().catch(() => false)) return 'WMC home ready';
  for (let retry = 0; retry < 30; retry++) {
    if (await support.isVisible().catch(() => false)) return 'WMC home ready';
    await waitForLoginModal();
    await home.getByRole('row', { name: 'To login, please click on' }).getByRole('link').click({ timeout: 1000 }).catch(() => {});
    await home.locator('#loginButton').click({ timeout: 1000 }).catch(() => {});
    const email = home.getByRole('textbox', { name: 'Login ID (e-mail)' });
    if (await email.isVisible().catch(() => false)) {
      await email.fill(process.env.WMC_USERNAME || env.WMC_USERNAME);
      await home.getByRole('textbox', { name: 'Password' }).fill(process.env.WMC_PASSWORD || env.WMC_PASSWORD);
      await home.getByRole('button', { name: 'Sign In', exact: true }).click();
      break;
    }
    await home.waitForTimeout(1000);
  }
  await support.waitFor({ timeout: 300000 });
  return 'WMC home ready';
}
async function waitForLoginModal() {
  const modal = home.locator('[role="dialog"]:visible').first();
  if (await modal.count()) await modal.waitFor({ state: 'hidden', timeout: 300000 });
}
async function audit({ host, path, editorUrl }) {
  const page = editorUrl ? (!reviewPage || reviewPage.isClosed() ? reviewPage = await openTab(context) : reviewPage) : await openTab(context);
  try {
    const response = await page.goto(`${host}${path}.infinity.json`, { waitUntil: 'domcontentloaded' });
    const body = await page.locator('body').innerText();
    if (!response?.ok() || !body.startsWith('{')) throw new Error(`Not authorized for ${host}; return to WMC home and finish Support login.`);
    const grid = JSON.parse(body)?.['jcr:content']?.root?.responsivegrid?.responsivegrid;
    if (!grid) throw new Error(`No FAQ component grid at ${path}`);
    if (editorUrl) await openEditor(editorUrl);
    return { components: Object.values(grid).filter(x => x?.['sling:resourceType']).map(x => ({ type: x['sling:resourceType'], settings: settings(x), text: textValues(x), descriptions: descriptionValues(x) })) };
  } finally { if (page !== reviewPage) await closeTab(context, page); }
}
async function copy({ host, sourcePath, destinationPath, siteCode, slug }) {
  const page = await openTab(context);
  try {
    const search = new URL('/mnt/overlay/granite/ui/content/shell/omnisearch/searchresults.html', host);
    search.search = new URLSearchParams({ 'p.guessTotal': '1000', fulltext: slug, _charset_: 'utf-8', orderby: 'path', path: '/', '5_property': 'type', '6_property': 'status', '7_property': 'ownerassignee', location: 'inbox' });
    const response = await page.goto(search.href, { waitUntil: 'domcontentloaded' });
    if (!response?.ok()) throw new Error(`Inbox search failed: ${response?.status() || 'no response'}`);
    const matches = [...(await page.content()).matchAll(/data-product-custom-url="([^"]+)"/g)].map(x => new URL(x[1].replaceAll('&amp;', '&'), host)).filter(x => x.searchParams.get('siteCdParam') === siteCode);
    if (matches.length !== 1) throw new Error(`Expected one inbox result for ${siteCode}/${slug}, found ${matches.length}`);
    const fields = { sourcePath, destinationPath, contentId: matches[0].searchParams.get('contentIdParam'), siteCode, requestId: matches[0].searchParams.get('requestIdParam') };
    await post(page, `${host}/sim/support/helpcontentmgmt/v6/copy`, fields);
    await post(page, `${host}/sim/core/workflow/v6/updatewfcodeaftersave`, { ...fields, requestUserId: '', contentId: fields.contentId });
    return true;
  } finally { await closeTab(context, page); }
}
async function post(page, url, fields) {
  await page.goto(`${new URL(url).origin}/libs/granite/csrf/token.json`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(async ({ url, fields }) => { const r = await fetch(url, { method: 'POST', credentials: 'include', headers: { 'content-type': 'application/x-www-form-urlencoded; charset=UTF-8' }, body: new URLSearchParams(fields) }); if (!r.ok) throw new Error(`${r.status} ${await r.text()}`); }, { url, fields });
}
function settings(value, key = '') {
  if (Array.isArray(value)) return value.map(item => settings(item, key));
  if (!value || typeof value !== 'object') return textKey(key) || key.startsWith('jcr:') ? undefined : value;
  const direct = {}, children = [];
  for (const [name, item] of Object.entries(value)) {
    if (name.startsWith('jcr:') || textKey(name) || assetKey(name)) continue;
    if (item && typeof item === 'object' && !Array.isArray(item)) children.push(settings(item, name)); else direct[name] = settings(item, name);
  }
  return children.length ? { ...direct, children } : direct;
}
function textValues(value, path = '') { if (Array.isArray(value)) return value.flatMap((item, index) => textValues(item, `${path}/${index}`)); if (!value || typeof value !== 'object') return textKey(path.split('/').pop()) && typeof value === 'string' ? [value] : []; return Object.entries(value).flatMap(([key, item]) => textValues(item, `${path}/${key}`)); }
function descriptionValues(value) { if (Array.isArray(value)) return value.flatMap(descriptionValues); if (!value || typeof value !== 'object') return []; return Object.entries(value).flatMap(([key, item]) => key.toLowerCase() === 'description' && typeof item === 'string' ? [item] : descriptionValues(item)); }
function textKey(key = '') { return /(?:description|headline|title|text|label|caption|alternative|alt)$/i.test(key); }
function assetKey(key = '') { return /(?:image(?:ref|reference)?|fileReference)$/i.test(key); }
