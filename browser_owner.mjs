import net from 'node:net';
import { readFileSync } from 'node:fs';
import { firefox } from 'playwright';
import { openTab, closeTab } from './aem_browser.mjs';

const profile = process.env.AEM_PROFILE || '.firefox-profile';
const env = Object.fromEntries(readFileSync('.env', 'utf8').split(/\r?\n/).map(line => line.split(/=(.*)/s)).filter(([k]) => k));
const context = await firefox.launchPersistentContext(profile, { headless: false, slowMo: 100, args: ['--allow-downgrade'], firefoxUserPrefs: { 'browser.link.open_newwindow': 3, 'browser.link.open_newwindow.restriction': 0 } });
let home = context.pages()[0] || await context.newPage(), reviewPage;
let finishLogin = () => {};
let transitioning = Promise.resolve();
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
  if (request.action === 'done') return finishLogin();
  if (request.action === 'open') return openEditor(request.url);
  if (request.action === 'audit') return audit(request);
  if (request.action === 'copy') return copy(request);
  if (request.action === 'exists') return exists(request);
  if (request.action === 'publish') return publish(request);
  if (request.action === 'storage_state') return context.storageState();
  if (request.action === 'jira_ready') return jiraReady();
  if (request.action === 'live') return live(request);
  throw new Error(`Unknown browser action: ${request.action}`);
}
async function openEditor(url) {
  reviewPage = await openTab(context);
  await reviewPage.goto(url, { waitUntil: 'domcontentloaded' });
  await reviewPage.bringToFront();
  return true;
}
async function login() {
  let release;
  const done = new Promise(resolve => release = resolve);
  finishLogin = () => release('done');
  await home.goto('https://wds.samsung.com/wds/sso/login/forwardLogin.do', { waitUntil: 'domcontentloaded' });
  const support = home.getByRole('link', { name: 'Support' }).first();
  const email = home.getByRole('textbox', { name: 'Login ID (e-mail)' });
  try {
    let state = await loginState(support, email, done, 30000);
    if (!state) {
      await home.getByRole('row', { name: 'To login, please click on' }).getByRole('link').click();
      await home.locator('#loginButton').click();
      state = await loginState(support, email, done, 30000);
      if (!state) throw new Error('Login page did not become ready within 30s.');
    }
    if (state !== 'form') return 'WMC home ready';
    await email.fill(process.env.WMC_USERNAME || env.WMC_USERNAME);
    await home.getByRole('textbox', { name: 'Password' }).fill(process.env.WMC_PASSWORD || env.WMC_PASSWORD);
    await home.getByRole('button', { name: 'Sign In', exact: true }).click();
    if (!await loginState(support, email, done, 300000)) throw new Error('Login did not finish within 300s.');
    return 'WMC home ready';
  } finally { finishLogin = () => {}; }
}
async function loginState(support, email, done, timeout) {
  const ready = await Promise.race([
    support.waitFor({ state: 'visible', timeout }).then(() => 'home'),
    email.waitFor({ state: 'visible', timeout }).then(() => 'form'),
    done,
  ]).catch(() => null);
  return ready;
}
async function exists({ host, path }) {
  const page = await openTab(context);
  try { return (await page.goto(`${host}${path}.infinity.json`, { waitUntil: 'domcontentloaded' }))?.ok() ?? false; }
  finally { await closeTab(context, page); }
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
    return { components: Object.values(grid).filter(x => x?.['sling:resourceType']).map(x => ({ type: x['sling:resourceType'], settings: settings(x), text: textValues(x), descriptions: descriptionValues(x), discoverColumnNew: discoverColumnNewValues(x) })) };
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
async function publish(request) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try { return await publishOnce(request); }
    catch (error) {
      if (attempt === 3 || !transientBrowserError(error)) throw error;
      await new Promise(resolve => setTimeout(resolve, attempt * 750));
    }
  }
}
async function publishOnce({ siteCode, slug }) {
  const page = await openTab(context);
  try {
    await page.goto('https://jira.secext.samsung.net/', { waitUntil: 'domcontentloaded' });
    await dismissNotice(page);
    const tickets = await ensureJiraLogin(page);
    const ticketsUrl = await tickets.getAttribute('href');
    if (!ticketsUrl) throw new Error('Jira ticket navigation has no URL.');
    await page.goto(new URL(ticketsUrl, page.url()).href, { waitUntil: 'domcontentloaded' });
    const search = page.getByRole('textbox', { name: 'Contains text' });
    await search.waitFor({ state: 'visible', timeout: 30000 });
    await search.fill(`${siteCode} ${slug}`);
    await search.press('Enter');
    let searchResult = await ticketMatches(page, new RegExp(`^${escapeRe(siteCode)}\\b`, 'i'), slug);
    if (!searchResult.matches.length) {
      await search.fill(slug); await search.press('Enter');
      const fallback = await ticketMatches(page, new RegExp(`\\[${escapeRe(siteCode)}\\]|\\b${escapeRe(siteCode)}\\b`, 'i'), slug);
      searchResult = { ...fallback, searches: [searchResult, fallback] };
    }
    if (!searchResult.matches.length) return classified('not_found', siteCode, slug, searchResult);
    if (searchResult.matches.length !== 1) return classified('ambiguous', siteCode, slug, searchResult);
    const issueUrl = await searchResult.matches[0].getAttribute('href');
    if (!issueUrl) throw new Error(`Jira search result for ${siteCode} has no issue URL.`);
    await page.goto(new URL(issueUrl, page.url()).href, { waitUntil: 'domcontentloaded' });
    return transition(async () => {
      if (await isLive(page)) return { status: 'done' };
      if (!await production(page).isVisible().catch(() => false)) {
        await uiClick(page.getByRole('button', { name: 'New Request' }));
        await uiClick(page.getByRole('menuitem').filter({ hasText: 'Start AEM Workflow' }));
        await confirm(page, 'Start AEM Workflow');
      }
      await uiClick(production(page));
      await uiClick(page.getByRole('menuitem').filter({ hasText: 'Go To Live' }));
      await confirm(page, 'Go To Live', () => isLive(page));
      return { status: 'done' };
    });
  } finally { await closeTab(context, page); }
}
async function live({ url }) {
  const target = url.startsWith('http') ? url : `https://${url}`;
  const page = await openTab(context);
  try { return (await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 30000 }))?.status() === 200; }
  catch { return false; } finally { await closeTab(context, page); }
}
async function jiraReady() {
  await home.goto('https://jira.secext.samsung.net/', { waitUntil: 'domcontentloaded' });
  await dismissNotice(home);
  await ensureJiraLogin(home);
  return true;
}
async function dismissNotice(page) {
  const dismissed = await page.evaluate(() => {
    const button = document.querySelector('#hideTodayBtn, #closeBtn');
    if (!button) return false;
    button.click();
    return true;
  });
  if (dismissed) await page.locator('#noticeOverlay').waitFor({ state: 'hidden', timeout: 10000 });
}
async function ensureJiraLogin(page) {
  const tickets = page.getByRole('link', { name: 'tickets Assigned to Me' });
  if (await tickets.isVisible().catch(() => false)) return tickets;
  if (await tickets.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false)) return tickets;
  if (await page.getByText('Log in', { exact: true }).isVisible().catch(() => false)) throw new Error('Jira session expired in the shared Firefox session. Use Sign in, then retry.');
  throw new Error('Jira did not finish loading its ticket navigation within 30 seconds.');
}
function production(page) { return page.locator('#opsbar-transitions_more').filter({ hasText: /\bPRODUCTION\b/i }); }
async function isLive(page) { const label = page.locator('#opsbar-transitions_more .dropdown-text'); return await label.isVisible().catch(() => false) && (await label.innerText()).trim().toUpperCase() === 'LIVE'; }
function transition(work) {
  const task = transitioning.then(work);
  transitioning = task.catch(() => {});
  return task;
}
async function uiClick(locator) {
  await locator.waitFor({ state: 'visible', timeout: 20000 });
  await locator.click();
  await new Promise(resolve => setTimeout(resolve, 300));
}
async function confirm(page, name, success = null) {
  const dialog = page.locator('section[role="dialog"]').filter({ has: page.getByRole('heading', { name, exact: true }) });
  const button = dialog.locator('#issue-workflow-transition-submit');
  await button.waitFor({ state: 'visible', timeout: 20000 });
  for (let i = 0; i < 6; i++) {
    await uiClick(button).catch(() => {});
    if (await dialog.waitFor({ state: 'hidden', timeout: 5000 }).then(() => true).catch(() => false)) return;
    if (success && i >= 2 && await success()) return;
  }
  if (!success || !await success()) throw new Error(`Clicked '${name}' 6 times, but its modal never closed.`);
}
function escapeRe(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
function exactSlug(text, slug) { return new RegExp(`(^|[^A-Za-z0-9_-])${escapeRe(slug)}($|[^A-Za-z0-9_-])`).test(text); }
async function exactSlugRows(rows, slug) { const matches = []; for (let i = 0; i < await rows.count(); i++) if (exactSlug(await rows.nth(i).innerText(), slug)) matches.push(rows.nth(i)); return matches; }
async function ticketMatches(page, match, slug) {
  await page.waitForLoadState('networkidle');
  let rows = page.getByRole('link', { name: match });
  let matches = await exactSlugRows(rows, slug);
  const candidates = await candidateTexts(rows);
  if (!matches.length) {
    const next = page.locator('a[data-page="2"]');
    if (await next.isVisible().catch(() => false)) {
      await next.click();
      await page.waitForLoadState('networkidle');
      rows = page.getByRole('link', { name: match });
      matches = await exactSlugRows(rows, slug);
      candidates.push(...await candidateTexts(rows));
    }
  }
  return { matches, candidates };
}
async function candidateTexts(rows) { return (await rows.allInnerTexts()).map(text => text.replace(/\s+/g, ' ').trim()).filter(Boolean).slice(0, 12); }
function classified(status, siteCode, slug, result) {
  const searches = result.searches || [result];
  return { status, detail: { siteCode, slug, searches: searches.map(({ candidates, matches }) => ({ candidates, exactSlugMatches: matches.length })) } };
}
function transientBrowserError(error) { return /(detached from the DOM|Timeout .*exceeded|Navigation|net::ERR|Target page, context or browser has been closed)/i.test(String(error)); }
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
function discoverColumnNewValues(value) { if (!value || typeof value !== 'object') return []; return Object.entries(value).flatMap(([key, item]) => /discover.*column.*new/i.test(key) ? strings(item) : discoverColumnNewValues(item)); }
function strings(value) { return Array.isArray(value) ? value.flatMap(strings) : value && typeof value === 'object' ? Object.values(value).flatMap(strings) : typeof value === 'string' ? [value] : []; }
function textKey(key = '') { return /(?:description|headline|title|text|label|caption|alternative|alt)$/i.test(key); }
function assetKey(key = '') { return /(?:image(?:ref|reference)?|fileReference)$/i.test(key); }
