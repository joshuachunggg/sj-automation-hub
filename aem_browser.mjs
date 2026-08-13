import { chromium, firefox } from 'playwright';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export async function openAemBrowser({ browserName = 'chromium', cdp, userDataDir }) {
  if (browserName === 'firefox') {
    const context = await firefox.launchPersistentContext(userDataDir || join(tmpdir(), 'sj-aem-firefox'), { headless: false });
    return { context, close: () => context.close() };
  }
  if (browserName === 'chromium') {
    const browser = await chromium.connectOverCDP(cdp);
    return {
      context: browser.contexts()[0] || await browser.newContext(),
      close: () => browser.close(),
    };
  }
  throw new Error(`Unknown browser: ${browserName}`);
}
