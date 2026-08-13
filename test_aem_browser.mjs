import assert from 'node:assert/strict';
import { openTab } from './aem_browser.mjs';

let id = 0, listeners = [];
const first = { url: () => 'https://wds.samsung.com', evaluate: async () => listeners.shift()({ id: ++id }) };
const context = { pages: () => [first], waitForEvent: () => new Promise(resolve => listeners.push(resolve)) };
const [one, two] = await Promise.all([openTab(context), openTab(context)]);
assert.notEqual(one, two);
