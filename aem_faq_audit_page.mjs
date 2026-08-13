#!/usr/bin/env node
import { openAemBrowser, openTab } from './aem_browser.mjs';

const args = new Map(process.argv.slice(2).reduce((pairs, value, index, all) => {
  if (value.startsWith('--')) pairs.push([value.slice(2), all[index + 1]]);
  return pairs;
}, []));

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});

async function main() {
  const host = required('host');
  const path = required('path');
  const { context, close } = await openAemBrowser({ userDataDir: args.get('user-data-dir') });
  const page = await reviewPage(context);
  const response = await page.goto(`${host}${path}.infinity.json`, { waitUntil: 'domcontentloaded' });
  if (!response?.ok()) throw new Error(`Could not read ${path}: ${response?.status() || 'no response'}`);
  const pageJson = JSON.parse(await page.locator('body').innerText());
  const grid = pageJson?.['jcr:content']?.root?.responsivegrid?.responsivegrid;
  if (!grid) throw new Error(`No FAQ component grid at ${path}`);
  const components = Object.values(grid)
    .filter((node) => node && typeof node === 'object' && node['sling:resourceType'])
    .map((node) => ({
      type: node['sling:resourceType'],
      settings: settings(node),
      text: textValues(node),
      discoverColumnNew: discoverColumnNewValues(node),
    }));
  if (args.get('editor-url')) await page.goto(args.get('editor-url'), { waitUntil: 'domcontentloaded' }).catch(() => {});
  console.log(JSON.stringify({ components }));
  await close();
}

async function reviewPage(context) {
  for (const page of context.pages()) {
    if (await page.evaluate(() => window.name === 'aem-faq-review').catch(() => false)) return page;
  }
  const page = await openTab(context);
  await page.evaluate(() => { window.name = 'aem-faq-review'; });
  return page;
}

function settings(value, key = '') {
  if (Array.isArray(value)) return value.map((item) => settings(item, key));
  if (!value || typeof value !== 'object') return textKey(key) || key.startsWith('jcr:') ? undefined : value;
  const direct = {};
  const children = [];
  for (const [name, item] of Object.entries(value)) {
    if (name.startsWith('jcr:') || textKey(name) || assetKey(name)) continue;
    if (item && typeof item === 'object' && !Array.isArray(item)) children.push(settings(item, name));
    else direct[name] = settings(item, name);
  }
  return children.length ? { ...direct, children } : direct;
}

function textValues(value, path = '') {
  if (Array.isArray(value)) return value.flatMap((item, index) => textValues(item, `${path}/${index}`));
  if (!value || typeof value !== 'object') return textKey(path.split('/').pop()) && typeof value === 'string' ? [value] : [];
  return Object.entries(value).flatMap(([key, item]) => textValues(item, `${path}/${key}`));
}

function discoverColumnNewValues(value) {
  if (!value || typeof value !== 'object') return [];
  return Object.entries(value).flatMap(([key, item]) => /discover.*column.*new/i.test(key) ? strings(item) : discoverColumnNewValues(item));
}

function strings(value) {
  if (Array.isArray(value)) return value.flatMap(strings);
  if (value && typeof value === 'object') return Object.values(value).flatMap(strings);
  return typeof value === 'string' ? [value] : [];
}

function textKey(key = '') {
  return /(?:description|headline|title|text|label|caption|alternative|alt)$/i.test(key);
}

function assetKey(key = '') {
  return /(?:image(?:ref|reference)?|fileReference)$/i.test(key);
}

function required(name) {
  const value = args.get(name);
  if (!value) throw new Error(`Missing --${name}`);
  return value;
}
