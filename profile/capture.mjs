import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const [source, destination] = process.argv.slice(2);
const browserPath = process.env.PROFILE_BROWSER || 'google-chrome';
const browserProfile = await mkdtemp(join(tmpdir(), 'anka-card-browser-'));
const browser = spawn(browserPath, [
  '--headless=new', '--disable-gpu', '--disable-dev-shm-usage', '--disable-background-networking',
  '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', `--user-data-dir=${browserProfile}`,
  'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'inherit'] });

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const selectors = {
  hero: '.hero',
  overview: '.overview-pair',
  activity: '.activity',
  details: '.profile-details-pair',
  achievements: 'section[aria-labelledby=achievements-title]',
  extras: '.profile-more',
};

let browserError;
browser.on('error', error => { browserError = error; });
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (browserError) throw browserError;
    if (browser.exitCode !== null) throw new Error(`Browser exited (${browser.exitCode})`);
    const data = await readFile(join(browserProfile, 'DevToolsActivePort'), 'utf8').catch(() => '');
    if (data) {
      [port] = data.split('\n');
      break;
    }
    await delay(100);
  }
  if (!port) throw new Error('The browser did not start a DevTools session');
  const tabs = await fetch(`http://127.0.0.1:${port}/json/list`).then(response => response.json());
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });

  let nextId = 0;
  const pending = new Map();
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    const handler = pending.get(message.id);
    if (!handler) return;
    pending.delete(message.id);
    clearTimeout(handler.timeout);
    if (message.error) handler.reject(new Error(message.error.message));
    else handler.resolve(message.result);
  });
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    const timeout = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Browser timed out running ${method}`));
    }, 20000);
    pending.set(id, { resolve, reject, timeout });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const response = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (response.exceptionDetails) throw new Error(response.result.description);
    return response.result.value;
  };

  const cards = new Map();
  for (const theme of ['light', 'dark']) {
    for (const [size, width] of [['desktop', 832], ['mobile', 390]]) {
      await cdp('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1.5, mobile: false });
      await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: theme }] });
      await cdp('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
      await cdp('Page.navigate', { url: pathToFileURL(source).href });
      for (let attempt = 0; attempt < 80; attempt++) {
        if (await evaluate(`document.readyState === 'complete' && Boolean(document.querySelector('.hero'))`)) break;
        if (attempt === 79) throw new Error('The card layout did not load');
        await delay(100);
      }
      const broken = await evaluate(`Promise.all(Array.from(document.images, async image => {
        try { await image.decode(); return null; } catch { return image.alt || 'missing image'; }
      })).then(images => images.filter(Boolean))`);
      if (broken.length) throw new Error(`Images did not load: ${broken.join(', ')}`);
      await delay(1600);

      for (const [name, selector] of Object.entries(selectors)) {
        const clip = await evaluate(`(() => {
          const {x, y, width, height} = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();
          return { x, y, width, height: Math.ceil(height), scale: 1 };
        })()`);
        if (clip.width <= 0 || clip.height <= 0 || clip.x + clip.width > width + 1) {
          throw new Error(`Unexpected bounds for ${name}: ${JSON.stringify(clip)}`);
        }
        const { data } = await cdp('Page.captureScreenshot', { format: 'webp', quality: 93, clip, captureBeyondViewport: true });
        cards.set(`${name}-${size}-${theme}.webp`, Buffer.from(data, 'base64'));
      }
    }
  }

  await mkdir(destination, { recursive: true });
  await Promise.all([...cards].map(([name, content]) => writeFile(join(destination, name), content)));
  console.log(`Rendered ${cards.size} profile cards`);
} finally {
  socket?.close();
  if (browser.exitCode === null) {
    browser.kill();
    await delay(300);
  }
  await rm(browserProfile, { recursive: true, force: true, maxRetries: 3 }).catch(() => {});
}
