import { createInterface } from 'node:readline';
import { openAemBrowser } from './aem_browser.mjs';

const profile = process.argv[2];
const { context, close } = await openAemBrowser({ browserName: 'firefox', userDataDir: profile });
const login = await context.newPage();
await loginToWmc(login);
reply({ ready: true });

createInterface({ input: process.stdin }).on('line', async (line) => {
  try {
    const request = JSON.parse(line);
    if (request.action === 'close') {
      await close();
      process.exit(0);
    }
    reply({ ok: true, result: request.action === 'audit' ? await audit(request) : await copy(request) });
  } catch (error) {
    reply({ ok: false, error: error.stack || String(error) });
  }
});

function reply(value) { process.stdout.write(`${JSON.stringify(value)}\n`); }

async function loginToWmc(page) {
  for (const name of ['WMC_LOGIN_URL', 'WMC_USERNAME', 'WMC_PASSWORD']) if (!process.env[name]) throw new Error(`Missing ${name} in .env`);
  await page.goto(process.env.WMC_LOGIN_URL, { waitUntil: 'domcontentloaded' });
  const home = page.getByText(/^Hi,/).first();
  const email = page.getByRole('textbox', { name: 'Login ID (e-mail)' });
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (await home.isVisible().catch(() => false)) return;
    if (await email.isVisible().catch(() => false)) {
      await email.fill(process.env.WMC_USERNAME);
      await page.getByRole('textbox', { name: 'Password' }).fill(process.env.WMC_PASSWORD);
      await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    }
    await page.waitForTimeout(250);
  }
  throw new Error('WMC did not finish login');
}

async function audit({ host, path, editorUrl }) {
  const page = await context.newPage();
  try {
    const response = await page.goto(`${host}${path}.infinity.json`, { waitUntil: 'domcontentloaded' });
    if (!response?.ok()) throw new Error(`Could not read ${path}: ${response?.status() || 'no response'}`);
    const grid = JSON.parse(await page.locator('body').innerText())?.['jcr:content']?.root?.responsivegrid?.responsivegrid;
    if (!grid) throw new Error(`No FAQ component grid at ${path}`);
    if (editorUrl) await page.goto(editorUrl, { waitUntil: 'domcontentloaded' }).catch(() => {});
    return { components: Object.values(grid).filter(node => node && typeof node === 'object' && node['sling:resourceType']).map(node => ({ type: node['sling:resourceType'], settings: settings(node), text: textValues(node) })) };
  } finally { await page.close(); }
}

async function copy({ host, sourcePath, destinationPath, siteCode, slug }) {
  const page = await context.newPage();
  try {
    const search = new URL('/mnt/overlay/granite/ui/content/shell/omnisearch/searchresults.html', host);
    search.search = new URLSearchParams({ 'p.guessTotal': '1000', fulltext: slug, _charset_: 'utf-8', orderby: 'path', path: '/', '5_property': 'type', '6_property': 'status', '7_property': 'ownerassignee', location: 'inbox' });
    const response = await page.goto(search.href, { waitUntil: 'domcontentloaded' });
    if (!response?.ok()) throw new Error(`Inbox search failed: ${response?.status() || 'no response'}`);
    const matches = [...(await page.content()).matchAll(/data-product-custom-url="([^"]+)"/g)].map(match => new URL(match[1].replaceAll('&amp;', '&'), host)).filter(url => url.searchParams.get('siteCdParam') === siteCode);
    if (matches.length !== 1) throw new Error(`Expected one inbox result for ${siteCode}/${slug}, found ${matches.length}`);
    const fields = { sourcePath, destinationPath, contentId: matches[0].searchParams.get('contentIdParam'), siteCode, requestId: matches[0].searchParams.get('requestIdParam') };
    await post(page, `${host}/sim/support/helpcontentmgmt/v6/copy`, fields);
    await post(page, `${host}/sim/core/workflow/v6/updatewfcodeaftersave`, { ...fields, requestUserId: '', contentId: fields.contentId });
    return true;
  } finally { await page.close(); }
}

async function post(page, url, fields) {
  await page.goto(`${new URL(url).origin}/libs/granite/csrf/token.json`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(async ({ url, fields }) => {
    const response = await fetch(url, { method: 'POST', credentials: 'include', headers: { 'content-type': 'application/x-www-form-urlencoded; charset=UTF-8' }, body: new URLSearchParams(fields) });
    if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  }, { url, fields });
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
function textKey(key = '') { return /(?:description|headline|title|text|label|caption|alternative|alt)$/i.test(key); }
function assetKey(key = '') { return /(?:image(?:ref|reference)?|fileReference)$/i.test(key); }
