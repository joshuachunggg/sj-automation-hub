#!/usr/bin/env node
import { chromium, firefox } from 'playwright-core';
import { createInterface } from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';

const options = parseArgs(process.argv.slice(2));
const apply = options.has('apply');
const yes = options.has('yes');
const overwrite = options.has('overwrite');
let sourceUrl = options.get('source');
let targetUrl = options.get('target');
const cdp = process.env.CDP || 'http://127.0.0.1:9223';
const browserName = options.get('browser') || 'chromium';
const userDataDir = options.get('user-data-dir') || `/tmp/aem-${browserName}`;

const skipKeys = new Set([
  'jcr:primaryType',
  'jcr:created',
  'jcr:createdBy',
  'jcr:lastModified',
  'jcr:lastModifiedBy',
  'cq:lastModified',
  'cq:lastModifiedBy',
]);

main().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});

async function main() {
  const setupPrompt = !sourceUrl || !targetUrl ? createInterface({ input, output }) : null;
  sourceUrl ||= await ask(setupPrompt, 'Source/read page URL: ');
  targetUrl ||= await ask(setupPrompt, 'Target/write page URL: ');
  setupPrompt?.close();

  const sourceRoot = pagePath(sourceUrl);
  const targetRoot = pagePath(targetUrl);
  const requestedRelPath = options.get('container-path') || 'jcr:content/root/responsivegrid/responsivegrid';

  const { browser, context } = await browserContext(browserName, cdp, userDataDir);
  const sourcePage = await getOrOpenPage(context, sourceUrl);
  await sourcePage.goto(sourceUrl, { waitUntil: 'domcontentloaded' });
  const targetPage = await getOrOpenPage(context, targetUrl);
  await targetPage.goto(targetUrl, { waitUntil: 'domcontentloaded' });

  const sourceComponentsPath = await resolveComponentsPath(sourcePage, sourceRoot, requestedRelPath, {
    requireJson: true,
  });
  const sourceRelPath = sourceComponentsPath.slice(sourceRoot.length + 1);
  const targetComponentsPath = `${targetRoot}/${sourceRelPath}`;
  if (!await targetContainerExists(targetPage, targetComponentsPath)) {
    throw new Error(`Target container does not exist: ${targetComponentsPath}`);
  }

  if (!sourceComponentsPath.startsWith('/content/samsung/')) {
    throw new Error(`Refusing to run: source path looks wrong: ${sourceComponentsPath}`);
  }
  assertSafeTarget(sourceComponentsPath, targetComponentsPath);
  console.log(`Source container: ${sourceComponentsPath}`);
  console.log(`Target container: ${targetComponentsPath}`);

  const source = await aemJson(sourcePage, sourceComponentsPath);
  const target = await aemJsonOrEmpty(targetPage, targetComponentsPath);
  const sourceNames = childNames(source);
  const targetNames = new Set(childNames(target));
  const namesToCopy = overwrite
    ? sourceNames
    : sourceNames.filter((name) => !targetNames.has(name));

  console.log(`Source components: ${sourceNames.join(', ')}`);
  console.log(`Target components: ${[...targetNames].join(', ') || '(none)'}`);
  console.log(`${apply ? 'Will import' : 'Dry run'}: ${namesToCopy.join(', ') || '(nothing)'}`);

  if (!apply || namesToCopy.length === 0) {
    await browser.close();
    return;
  }

  const prompt = yes ? null : createInterface({ input, output });
  const csrf = await csrfToken(targetPage);
  for (const name of namesToCopy) {
    if (prompt) {
      const answer = await prompt.question(`Press Enter to import ${name}, or type s to skip: `);
      if (answer.trim().toLowerCase() === 's') {
        console.log(`Skipped ${name}`);
        continue;
      }
    }
    await importNode(targetPage, csrf, sourceComponentsPath, targetComponentsPath, name, cleanNode(source[name]));
    console.log(`Imported ${name}`);
  }
  prompt?.close();

  await targetPage.goto(targetUrl, { waitUntil: 'domcontentloaded' });
  await targetPage.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  const after = await aemJsonOrEmpty(targetPage, targetComponentsPath);
  const renderedNames = new Set(await overlayChildNames(targetPage, targetComponentsPath));
  const missing = namesToCopy.filter((name) => !after[name] && !renderedNames.has(name));
  if (missing.length) throw new Error(`Import did not stick for: ${missing.join(', ')}`);
  console.log('Done. Reloaded target page and verified imported nodes exist.');
  await browser.close();
}

function parseArgs(argv) {
  const options = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--apply' || arg === '--yes' || arg === '--overwrite') {
      options.set(arg.slice(2), true);
    } else if (arg === '--source' || arg === '--target' || arg === '--container-path' || arg === '--browser' || arg === '--user-data-dir') {
      options.set(arg.slice(2), argv[++index]);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return options;
}

function usage() {
  console.error(`Usage:
  node copy-aem-components.mjs
  node copy-aem-components.mjs --apply

Options:
  --source URL   optional; prompts when omitted
  --target URL   optional; prompts when omitted
  --apply       write missing source components to target
  --yes         do not prompt before each import
  --overwrite   import all source components, replacing matching target nodes
  --browser chromium|firefox
                chromium attaches to CDP; firefox launches a persistent Playwright browser
  --user-data-dir PATH
                profile dir for --browser firefox
  --container-path PATH
                component container under the page path
                default: jcr:content/root/responsivegrid/responsivegrid`);
  process.exit(1);
}

async function browserContext(name, cdp, userDataDir) {
  if (name === 'chromium') {
    const browser = await chromium.connectOverCDP(cdp);
    return { browser, context: browser.contexts()[0] || await browser.newContext() };
  }
  if (name === 'firefox') {
    const context = await firefox.launchPersistentContext(userDataDir, { headless: false });
    return { browser: { close: () => context.close() }, context };
  }
  throw new Error(`Unknown browser: ${name}`);
}

async function ask(prompt, question) {
  if (!prompt) throw new Error(`Missing ${question.trim()}`);
  const answer = await prompt.question(question);
  if (!answer.trim()) throw new Error(`Missing ${question.trim()}`);
  return answer.trim();
}

function pagePath(url) {
  return new URL(url).pathname.replace(/^\/editor\.html/, '').replace(/\.html$/, '');
}

async function getOrOpenPage(context, url) {
  const wanted = new URL(url);
  const page = context.pages().find((candidate) => {
    try {
      const current = new URL(candidate.url());
      return current.host === wanted.host && current.pathname === wanted.pathname;
    } catch {
      return false;
    }
  });
  return page || await context.newPage();
}

async function aemJson(page, path) {
  return await page.evaluate(async (path) => {
    const response = await fetch(`${path}.infinity.json`, { credentials: 'include' });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${path}`);
    return response.json();
  }, path);
}

async function aemJsonOrEmpty(page, path) {
  return await page.evaluate(async (path) => {
    const response = await fetch(`${path}.infinity.json`, { credentials: 'include' });
    if (response.status === 404) return {};
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${path}`);
    return response.json();
  }, path);
}

async function aemJsonMaybe(page, path) {
  return await page.evaluate(async (path) => {
    const response = await fetch(`${path}.infinity.json`, { credentials: 'include' });
    return response.ok;
  }, path);
}

async function resolveComponentsPath(page, root, requestedRelPath, { requireJson }) {
  const requestedPath = `${root}/${requestedRelPath}`;
  if (await aemJsonMaybe(page, requestedPath)) return requestedPath;
  if (!requireJson && await overlayPathExists(page, requestedPath)) return requestedPath;
  if (options.has('container-path')) {
    throw new Error(`Configured container path does not exist: ${requestedPath}`);
  }

  await page.waitForSelector('[data-path$="/*"]', { timeout: 8000 }).catch(() => {});
  const candidates = await page.evaluate((root) => {
    return [...document.querySelectorAll('[data-path$="/*"]')]
      .map((element) => element.getAttribute('data-path').replace(/\/\*$/, ''))
      .filter((path) => path.startsWith(`${root}/`))
      .sort((a, b) => a.length - b.length);
  }, root);

  for (const candidate of [...new Set(candidates)]) {
    if (await aemJsonMaybe(page, candidate)) return candidate;
    if (!requireJson) return candidate;
  }

  throw new Error(
    `Could not find component container for ${root}. Tried ${requestedPath}${
      candidates.length ? ` and overlays: ${candidates.join(', ')}` : ''
    }`,
  );
}

async function overlayPathExists(page, path) {
  await page.waitForSelector('[data-path$="/*"]', { timeout: 8000 }).catch(() => {});
  return await page.evaluate((path) => {
    return [...document.querySelectorAll('[data-path$="/*"]')]
      .some((element) => element.getAttribute('data-path') === `${path}/*`);
  }, path);
}

async function targetContainerExists(page, path) {
  return await aemJsonMaybe(page, path) || await overlayPathExists(page, path);
}

async function overlayChildNames(page, parentPath) {
  return await page.evaluate((parentPath) => {
    const prefix = `${parentPath}/`;
    return [...document.querySelectorAll('[data-path]')]
      .map((element) => element.getAttribute('data-path'))
      .filter((path) => path.startsWith(prefix) && !path.endsWith('/*'))
      .map((path) => path.slice(prefix.length).split('/')[0])
      .filter((name) => name && name !== 'iparsys_fake_par');
  }, parentPath);
}

async function csrfToken(page) {
  const token = await page.evaluate(async () => {
    const response = await fetch('/libs/granite/csrf/token.json', { credentials: 'include' });
    if (!response.ok) return '';
    const json = await response.json();
    return json.token || '';
  });
  if (!token) throw new Error('Could not get AEM CSRF token');
  return token;
}

async function importNode(page, csrf, sourcePath, parentPath, name, node) {
  assertSafeTarget(sourcePath, parentPath);
  await page.evaluate(
    async ({ csrf, parentPath, name, node }) => {
      const body = new FormData();
      body.set(':operation', 'import');
      body.set(':contentType', 'json');
      body.set(':name', name);
      body.set(':replace', 'true');
      body.set(':content', JSON.stringify(node));

      const response = await fetch(parentPath, {
        method: 'POST',
        credentials: 'include',
        headers: { 'CSRF-Token': csrf },
        body,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Import failed for ${name}: ${response.status} ${text.slice(0, 500)}`);
      }
    },
    { csrf, parentPath, name, node },
  );
}

function assertSafeTarget(sourcePath, targetPath) {
  if (!targetPath.startsWith('/content/samsung/')) {
    throw new Error(`Refusing to write outside Samsung content: ${targetPath}`);
  }
  if (targetPath === sourcePath) {
    throw new Error('Refusing to write to the same path as the source');
  }
}

function childNames(node) {
  return Object.keys(node).filter((key) => node[key] && typeof node[key] === 'object');
}

function cleanNode(value) {
  if (Array.isArray(value)) return value.map(cleanNode);
  if (!value || typeof value !== 'object') return value;

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !skipKeys.has(key))
      .map(([key, nested]) => [key, cleanNode(nested)]),
  );
}
