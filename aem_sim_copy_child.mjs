#!/usr/bin/env node
import { chromium } from 'playwright-core';

const args = parseArgs(process.argv.slice(2));
const apply = args.has('apply');

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});

async function main() {
  const host = required('host');
  const sourcePath = required('source-path');
  const destinationPath = required('destination-path');
  const siteCode = required('site-code');

  const browser = await chromium.connectOverCDP(process.env.CDP || 'http://127.0.0.1:9223');
  const context = browser.contexts()[0] || await browser.newContext();
  const page = await context.newPage();
  try {
    const ids = args.get('content-id') && args.get('request-id')
      ? { contentId: required('content-id'), requestId: required('request-id') }
      : await lookupIds(page, host, siteCode, required('slug'));

    console.log(`${apply ? 'POST' : 'DRY'} ${sourcePath} -> ${destinationPath} (${ids.contentId}/${ids.requestId})`);
    if (!apply) return;

    await page.goto(`${host}/libs/granite/csrf/token.json`, { waitUntil: 'domcontentloaded' });
    await post(page, `${host}/sim/support/helpcontentmgmt/v6/copy`, {
      sourcePath,
      destinationPath,
      contentId: ids.contentId,
      siteCode,
      requestId: ids.requestId,
    });
    await post(page, `${host}/sim/core/workflow/v6/updatewfcodeaftersave`, {
      siteCode,
      requestId: ids.requestId,
      requestUserId: '',
      contentId: ids.contentId,
    });

    console.log('Done.');
  } finally {
    await page.close();
    await browser.close();
  }
}

async function lookupIds(page, host, siteCode, slug) {
  const search = new URL('/mnt/overlay/granite/ui/content/shell/omnisearch/searchresults.html', host);
  search.search = new URLSearchParams({
    'p.guessTotal': '1000', fulltext: slug, _charset_: 'utf-8', orderby: 'path', path: '/',
    '2_payloadPath': '', '3_workflowModelPath': '', '5_property': 'type',
    '5_property.breadcrumbs': 'Type', '6_property': 'status',
    '6_property.breadcrumbs': 'Task Status', '7_property': 'ownerassignee',
    '7_property.breadcrumbs': 'Where I am', location: 'inbox', 'location.suggestion': 'Inbox',
  });
  const response = await page.goto(search.href, { waitUntil: 'domcontentloaded' });
  if (!response || !response.ok()) throw new Error(`Inbox search failed: ${response?.status() || 'no response'}`);
  const html = await page.content();
  const matches = [...html.matchAll(/data-product-custom-url="([^"]+)"/g)]
    .map((match) => new URL(match[1].replaceAll('&amp;', '&'), host))
    .filter((url) => url.searchParams.get('siteCdParam') === siteCode);
  if (matches.length !== 1) {
    throw new Error(`Expected one inbox result for ${siteCode}/${slug}, found ${matches.length}. Paste its SIM detail URL instead.`);
  }
  return {
    contentId: matches[0].searchParams.get('contentIdParam'),
    requestId: matches[0].searchParams.get('requestIdParam'),
  };
}

async function post(page, url, fields) {
  const result = await page.evaluate(async ({ url, fields }) => {
    const body = new URLSearchParams(fields);
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'content-type': 'application/x-www-form-urlencoded; charset=UTF-8' },
      body,
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`${response.status} ${text.slice(0, 500)}`);
    return text;
  }, { url, fields });
  console.log(result.slice(0, 200));
}

function parseArgs(argv) {
  const out = new Map();
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--apply') {
      out.set('apply', true);
    } else if (arg.startsWith('--')) {
      out.set(arg.slice(2), argv[++i] || '');
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return out;
}

function required(name) {
  const value = args.get(name);
  if (!value) throw new Error(`Missing --${name}`);
  return value;
}
