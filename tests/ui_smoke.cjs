/**
 * UI smoke test against a running P18 instance, driven through real Chrome.
 * Uses the locally installed Chrome (no browser download).
 *
 *   node tests/ui_smoke.cjs [baseUrl] [user] [password]
 */
const { chromium } = require('playwright-core');

const BASE = process.argv[2] || 'http://127.0.0.1:8896';
const USER = process.argv[3] || 'admin';
const PASS = process.argv[4] || 'p18-review-2026';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  // favicon is not part of the product; every other 4xx/5xx is a real failure.
  const badResponses = [];
  page.on('response', response => {
    const url = response.url();
    if (response.status() >= 400 && !url.endsWith('/favicon.ico')) badResponses.push(`${response.status()} ${url}`);
  });

  try {
    // 1. 登录页渲染
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
    check('登录页渲染', await page.locator('#login').count() === 1);

    // 2. 表单登录
    await page.fill('input[name="username"]', USER);
    await page.fill('input[name="password"]', PASS);
    await Promise.all([
      page.waitForURL(/\/library\//, { timeout: 15000 }),
      page.click('#login button'),
    ]);
    check('登录后跳转文件库', page.url().includes('/library/'), page.url());

    // 3. 文件表格渲染
    await page.waitForSelector('table', { timeout: 15000 });
    const rows = await page.locator('tbody tr').count();
    check('文件表格有数据行', rows > 0, `行数 ${rows}`);

    // 4. 文档名可见
    const body = await page.locator('body').innerText();
    check('文档名出现在页面', /虚构研发规范/.test(body));

    // 5. 打开详情抽屉
    const firstRow = page.locator('tbody tr').first();
    await firstRow.click();
    await page.waitForTimeout(800);
    const drawer = await page.locator('body').innerText();
    check('点击行后出现详情', /密级|部门|版本/.test(drawer));

    // 6. 检索页
    await page.goto(`${BASE}/?view=search`, { waitUntil: 'networkidle' });
    await page.waitForSelector('body[data-view="search"]', { timeout: 15000 });
    const searchInput = page.locator('#search').first();
    check('检索页有输入框', await searchInput.count() === 1);
    await searchInput.fill('晨间校准几分钟', { force: true });
    await page.keyboard.press('Enter');
    await page.waitForTimeout(4000);
    const searchBody = await page.locator('body').innerText();
    check('检索有结果', /晨间|18|适用范围/.test(searchBody));

    // 7. 无 JS 异常
    const noise = errors.filter(text => !/Failed to load resource/.test(text));
    check('无前端 JS 异常', noise.length === 0, noise.slice(0, 2).join(' | '));
    check('无 4xx/5xx 资源', badResponses.length === 0, badResponses.slice(0, 3).join(' | '));
  } catch (error) {
    check('测试执行未中断', false, String(error).slice(0, 200));
  } finally {
    await browser.close();
  }

  const failed = results.filter(item => !item.ok).length;
  console.log(`\n${results.length - failed}/${results.length} 通过`);
  process.exit(failed ? 1 : 0);
})();
