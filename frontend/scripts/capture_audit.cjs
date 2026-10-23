const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';
const OUTPUT_DIR = process.env.OUTPUT_DIR || path.resolve(__dirname, '../../../../.gemini/antigravity-ide/brain/fab0df27-64b8-4322-ac6c-d8734ea47601/screenshots/before');

const VIEWPORTS = [
  { name: '1440px', width: 1440, height: 900 },
  { name: '768px', width: 768, height: 1024 },
  { name: '375px', width: 375, height: 812 }
];

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function capture() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  console.log(`Saving screenshots to: ${OUTPUT_DIR}`);

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();

  // Helper to take screenshot across all 3 viewports
  async function snapAll(viewName, setupFn) {
    for (const vp of VIEWPORTS) {
      await page.setViewport({ width: vp.width, height: vp.height });
      await sleep(400);
      if (setupFn) {
        await setupFn(vp);
        await sleep(300);
      }
      const filename = path.join(OUTPUT_DIR, `${viewName}_${vp.name}.png`);
      await page.screenshot({ path: filename, fullPage: false });
      console.log(`Saved: ${viewName}_${vp.name}.png`);
    }
  }

  // 1. Landing Page
  console.log('\n--- 1. Landing Page ---');
  await page.goto(BASE_URL, { waitUntil: 'networkidle2' });
  await snapAll('01_landing');

  // 2. Login Modal
  console.log('\n--- 2. Login Modal ---');
  await page.goto(BASE_URL, { waitUntil: 'networkidle2' });
  // Click Sign In or Login button
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const loginBtn = btns.find(b => b.textContent.includes('Sign In') || b.textContent.includes('Login'));
    if (loginBtn) loginBtn.click();
  });
  await sleep(600);
  await snapAll('02_login_modal');

  // 3. Login to get session
  console.log('\n--- Logging in ---');
  await page.evaluate(() => {
    const userInp = document.getElementById('input-login-username') || document.querySelector('input[type="text"]');
    const passInp = document.getElementById('input-login-password') || document.querySelector('input[type="password"]');
    if (userInp) {
      userInp.value = 'reviewer';
      userInp.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (passInp) {
      passInp.value = 'password123';
      passInp.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  await sleep(300);
  await page.evaluate(() => {
    const submitBtn = document.getElementById('btn-login-submit') || document.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.click();
  });
  await sleep(1500);

  // 4. Dashboard View
  console.log('\n--- 3. Dashboard View ---');
  await snapAll('03_dashboard');

  // 5. Disputes List
  console.log('\n--- 4. Disputes List ---');
  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('nav button, button'));
    const dTab = tabs.find(t => t.textContent.trim().toLowerCase() === 'disputes');
    if (dTab) dTab.click();
  });
  await sleep(1200);
  await snapAll('04_disputes_list');

  // Helper to open case detail
  async function openCase(caseId, viewPrefix) {
    console.log(`\n--- Case Detail: ${caseId} ---`);
    await page.evaluate((cid) => {
      // Find row with case ID or navigate directly via click
      const rows = Array.from(document.querySelectorAll('tr, div[class*="cursor-pointer"]'));
      const targetRow = rows.find(r => r.textContent.includes(cid));
      if (targetRow) {
        targetRow.click();
      } else {
        // Fallback: look for button or link
        const btns = Array.from(document.querySelectorAll('button'));
        const inspectBtn = btns.find(b => b.textContent.includes('Inspect') || b.textContent.includes('Review'));
        if (inspectBtn) inspectBtn.click();
      }
    }, caseId);
    await sleep(1500);
    await snapAll(viewPrefix);
  }

  // 6. Case disp_0001_hbrpoi
  await openCase('disp_0001_hbrpoi', '05_case_disp_0001_hbrpoi');

  // Return to disputes list and open disp_0002_r3xkxw
  await page.evaluate(() => {
    const backBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Disputes') || b.textContent.includes('Back'));
    if (backBtn) backBtn.click();
  });
  await sleep(1000);
  await openCase('disp_0002_r3xkxw', '06_case_disp_0002_r3xkxw');

  // Return to disputes list and open disp_0004_9ooaed (prompt injection)
  await page.evaluate(() => {
    const backBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Disputes') || b.textContent.includes('Back'));
    if (backBtn) backBtn.click();
  });
  await sleep(1000);
  await openCase('disp_0004_9ooaed', '07_case_disp_0004_9ooaed_injection');

  // 7. Review Queue View
  console.log('\n--- 8. Review Queue View ---');
  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('nav button, button'));
    const rqTab = tabs.find(t => t.textContent.trim().toLowerCase().includes('review'));
    if (rqTab) rqTab.click();
  });
  await sleep(1200);
  await snapAll('08_review_queue');

  // 8. Audit Ledger View
  console.log('\n--- 9. Audit Ledger View ---');
  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('nav button, button'));
    const aTab = tabs.find(t => t.textContent.trim().toLowerCase().includes('audit'));
    if (aTab) aTab.click();
  });
  await sleep(1200);
  await snapAll('09_audit_ledger');

  // 9. Settings View
  console.log('\n--- 10. Settings View ---');
  await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('nav button, button'));
    const sTab = tabs.find(t => t.textContent.trim().toLowerCase().includes('setting'));
    if (sTab) sTab.click();
  });
  await sleep(1200);
  await snapAll('10_settings');

  await browser.close();
  console.log('\nAudit screenshots successfully captured!');
}

capture().catch(err => {
  console.error('Capture error:', err);
  process.exit(1);
});
