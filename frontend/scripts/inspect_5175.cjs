const puppeteer = require('puppeteer-core');
const path = require('path');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL_5175 = 'http://127.0.0.1:5175';
const ARTIFACTS_DIR = 'C:\\Users\\Karthick Vel\\.gemini\\antigravity-ide\\brain\\3d14895c-b06b-41e2-a9de-3f38039f62b6';

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function inspect5175() {
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  console.log('Navigating to 5175...');
  await page.goto(URL_5175, { waitUntil: 'networkidle0' });
  await sleep(1500);

  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'ref_5175_home.png') });
  console.log('Saved ref_5175_home.png');

  // Let's also scroll down and capture
  await page.evaluate(() => window.scrollBy(0, 800));
  await sleep(800);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'ref_5175_scroll1.png') });

  // Let's check navigation or buttons on 5175
  const title = await page.title();
  console.log('5175 Page Title:', title);

  const navLinks = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('a, button')).map(el => ({
      tag: el.tagName,
      text: el.innerText.trim(),
      id: el.id,
      className: el.className
    })).filter(x => x.text.length > 0 && x.text.length < 50);
  });
  console.log('Links/Buttons on 5175:', JSON.stringify(navLinks.slice(0, 15), null, 2));

  await browser.close();
}

inspect5175().catch(err => {
  console.error('Error inspecting 5175:', err);
  process.exit(1);
});
