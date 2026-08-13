import { firefox } from 'playwright';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const profile = join(dirname(fileURLToPath(import.meta.url)), '.firefox-profile');

export async function openAemBrowser({ userDataDir } = {}) {
  const context = await firefox.launchPersistentContext(userDataDir || process.env.AEM_PROFILE || profile, {
    headless: false,
    args: ['--allow-downgrade'],
  });
  return { context, close: () => context.close() };
}

export async function openTab(context) {
  return context.pages().find((page) => page.url() === 'about:blank') || context.newPage();
}

export async function closeTab(context, page) {
  if (context.pages().length === 1) await page.goto('about:blank');
  else await page.close();
}
