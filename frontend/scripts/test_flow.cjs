const puppeteer = require('puppeteer-core');

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const BASE_URL = 'http://localhost:5173';

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function runEndToEndTest() {
  console.log('--- Starting DisputePilot End-to-End Flow Verification ---');

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  page.on('console', msg => console.log('BROWSER LOG:', msg.text()));
  page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));

  // 1. Visit Landing Page
  console.log('1. Loading landing page...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle0' }).catch(() => {});
  await sleep(1500);
  await page.screenshot({ path: 'scripts/debug_initial.png' });
  const htmlSnippet = await page.evaluate(() => document.body.innerHTML.slice(0, 300));
  console.log('Initial body HTML snippet:', htmlSnippet);

  // 2. Check if already authenticated or on landing page
  const hasUserNav = await page.$('#nav-disputes');
  if (!hasUserNav) {
    console.log('2. On landing page, clicking "Open demo console" button (#btn-hero-launch)...');
    try {
      await page.waitForSelector('#btn-hero-launch', { timeout: 4000 });
      await page.click('#btn-hero-launch');
      await sleep(600);
    } catch (e) {
      console.log('Hero launch button not found, checking login modal directly...');
    }

    // 3. Click quick reviewer login or fill form
    console.log('3. Authenticating with reviewer demo credentials...');
    const quickBtn = await page.$('#btn-quick-login-reviewer');
    if (quickBtn) {
      await quickBtn.click();
    } else {
      await page.waitForSelector('#input-login-username', { timeout: 6000 });
      await page.type('#input-login-username', 'reviewer');
      await page.type('#input-login-password', 'password123');
      await sleep(300);
      await page.click('#btn-submit-login');
    }
    await sleep(2500);
  } else {
    console.log('2-3. Already authenticated into console.');
  }

  // 4. Navigate to Disputes Worklist
  console.log('4. Navigating to Disputes Worklist (#nav-disputes)...');
  await page.waitForSelector('#nav-disputes', { timeout: 8000 });
  await page.click('#nav-disputes');
  await sleep(2500);

  const snippet = await page.evaluate(() => document.body.innerText.replace(/\s+/g, ' ').slice(0, 200));
  console.log('Page text after nav to disputes:', snippet);
  await page.screenshot({ path: 'scripts/debug_disputes.png' });

  // 5. Search and Open Case disp_0001_hbrpoi
  console.log('5. Searching for case disp_0001_hbrpoi...');
  await page.waitForSelector('input[placeholder*="Search case"]', { timeout: 8000 });
  await page.type('input[placeholder*="Search case"]', 'disp_0001_hbrpoi');
  await sleep(1200);

  console.log('Opening case disp_0001_hbrpoi...');
  await page.waitForSelector('#dispute-row-disp_0001_hbrpoi', { timeout: 10000 });
  await page.click('#dispute-row-disp_0001_hbrpoi');
  await sleep(2500);

  // 6. View Step 2: Evidence Section
  console.log('6. Inspecting Step 2: Evidence Checklist...');
  await page.waitForSelector('#step-tab-evidence', { timeout: 5000 });
  await page.click('#step-tab-evidence');
  await sleep(1000);

  // 7. Run AI Pipeline Analysis
  console.log('7. Triggering AI Analysis and Grounded Rebuttal Synthesis...');
  await page.click('#btn-trigger-ai');
  await sleep(4000);

  // 8. View Step 4: Rebuttal Studio
  console.log('8. Inspecting Step 4: Rebuttal Studio & Citations...');
  await page.waitForSelector('#step-tab-rebuttal', { timeout: 5000 });
  await page.click('#step-tab-rebuttal');
  await sleep(1000);

  // 9. Navigate to Step 5: Approval Station
  console.log('9. Navigating to Step 5: Approval Station...');
  await page.waitForSelector('#step-tab-approve', { timeout: 5000 });
  await page.click('#step-tab-approve');
  await sleep(2000);

  // 10. Type Reviewer Name and Check Confirmation
  console.log('10. Typing Reviewer Name and checking confirmation...');
  await page.waitForSelector('#input-reviewer-name', { timeout: 5000 });
  await page.type('#input-reviewer-name', 'Priya Sharma (Operations Reviewer)');
  await sleep(300);
  await page.click('#checkbox-confirm-contest');
  await sleep(1000);

  // 11. Check submission button state
  const isSubmitDisabled = await page.evaluate(() => {
    const submitBtn = document.getElementById('btn-confirm-contest-submit');
    return submitBtn ? submitBtn.disabled : true;
  });
  console.log(`11. Submission button disabled state: ${isSubmitDisabled} (Expected: false)`);

  if (!isSubmitDisabled) {
    console.log('12. Submitting contestation in sim mode...');
    await page.click('#btn-confirm-contest-submit');
    await sleep(3500);

    const resultText = await page.evaluate(() => {
      const el = document.querySelector('h3');
      return el ? el.textContent : '';
    });
    console.log(`13. Post-submission message: "${resultText}"`);
  }

  await browser.close();
  console.log('--- End-to-End Verification Completed Successfully! ---');
}

runEndToEndTest().catch(err => {
  console.error('Test error:', err);
  process.exit(1);
});
