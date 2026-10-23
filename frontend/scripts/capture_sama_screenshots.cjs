const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';
const ARTIFACTS_DIR = 'C:\\Users\\Karthick Vel\\.gemini\\antigravity-ide\\brain\\3d14895c-b06b-41e2-a9de-3f38039f62b6';

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function captureAll() {
  console.log('Connecting to Chrome...');
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // 1. Landing Page
  console.log('1. Capturing Landing Page...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle0' });
  await sleep(1500);
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_landing_page.png') });

  // 2. Click Enter ODR Portal to open login modal
  console.log('2. Opening Login Modal...');
  const heroLaunchBtn = await page.$('#btn-hero-launch');
  if (heroLaunchBtn) {
    await heroLaunchBtn.click();
    await sleep(1000);
  }

  // Save screenshot of the Login Modal itself!
  console.log('2b. Capturing Login Modal...');
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_login_modal.png') });

  // Click "Operations Reviewer" quick button
  console.log('3. Authenticating with Operations Reviewer...');
  const buttons = await page.$$('button');
  let loggedIn = false;
  for (const b of buttons) {
    const text = await page.evaluate(el => el.textContent, b);
    if (text.includes('Operations Reviewer')) {
      await b.click();
      loggedIn = true;
      break;
    }
  }

  if (!loggedIn) {
    // Fill credentials manually
    const userInput = await page.$('input[type="text"]');
    if (userInput) await userInput.type('reviewer');
    const passInput = await page.$('input[type="password"]');
    if (passInput) await passInput.type('password123');
    const submitBtn = await page.$('button[type="submit"]');
    if (submitBtn) await submitBtn.click();
  }

  await sleep(3000);

  // 4. Dashboard View
  console.log('4. Capturing Dashboard...');
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_dashboard.png') });

  // 5. Disputes View
  console.log('5. Capturing Disputes View...');
  const navDisputes = await page.$('#nav-disputes');
  if (navDisputes) {
    await navDisputes.click();
    await sleep(2500);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_disputes.png') });
  }

  // 6. Review Queue View
  console.log('6. Capturing Review Queue...');
  const navReview = await page.$('#nav-review-queue');
  if (navReview) {
    await navReview.click();
    await sleep(2500);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_review_queue.png') });
  }

  // 7. Case Detail View
  console.log('7. Opening Case Detail View...');
  if (navDisputes) {
    await navDisputes.click();
    await sleep(1500);
    const firstRow = await page.$('tbody tr td button');
    if (firstRow) {
      await firstRow.click();
      await sleep(3000);
      await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_case_detail.png') });
    }
  }

  // 8. Audit Ledger View
  console.log('8. Capturing Audit Ledger View...');
  const navAudit = await page.$('#nav-audit');
  if (navAudit) {
    await navAudit.click();
    await sleep(2500);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_audit_ledger.png') });
  }

  // 9. Settings View
  console.log('9. Capturing Settings View...');
  const navSettings = await page.$('#nav-settings');
  if (navSettings) {
    await navSettings.click();
    await sleep(2500);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'sama_settings.png') });
  }

  console.log('All views successfully captured in Sama aesthetic!');
  await browser.close();
}

captureAll().catch(err => {
  console.error('Error during capture:', err);
  process.exit(1);
});
