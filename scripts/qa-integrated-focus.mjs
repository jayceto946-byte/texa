/** Integration QA: run the existing disposable Focus fixture on :18042 and neighbour fixture on :18053. */
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)('playwright');
const base = 'http://127.0.0.1:18042';
const out = resolve(process.argv[2] || 'artifacts/integrated-focus');
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const results = [];
const snapshot = async () => (await (await fetch(base + '/api/focus')).json()).data;
try {
  for (const [width, height] of [[1280, 820], [1024, 768], [760, 820], [390, 844]]) {
    const context = await browser.newContext({ viewport: { width, height }, reducedMotion: 'reduce' });
    await context.addInitScript(() => localStorage.setItem('texa:setup-complete:v3', '1'));
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const shot = async name => {
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: resolve(out, `${width}-${name}.png`) });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width} ${name} horizontal overflow`);
    };
    await page.goto(base + '/goals?goal=goal-qa');
    await page.locator('.study-task-row .app-secondary-button').first().click();
    const panel = page.locator('.focus-mini-panel');
    await panel.getByRole('button', { name: /^(开始专注|开始新一段)$/ }).click();
    await panel.getByRole('button', { name: '暂停', exact: true }).waitFor();
    const session = (await snapshot()).current_session.id;
    await shot('goals-running');
    await page.goto(base + '/books');
    await page.getByRole('button', { name: /^展开专注面板/ }).click();
    await panel.getByRole('button', { name: '暂停', exact: true }).click();
    await panel.getByRole('button', { name: '继续', exact: true }).waitFor();
    assert.equal((await snapshot()).current_session.id, session);
    assert.equal((await snapshot()).status, 'paused');
    await shot('books-paused');
    await page.goto(base + '/?conversation_id=visual-session-0');
    await page.getByRole('button', { name: '选择学习范围', exact: true }).waitFor();
    await page.getByRole('button', { name: /^展开专注面板/ }).click();
    await panel.getByRole('button', { name: '继续', exact: true }).click();
    await panel.getByRole('button', { name: '暂停', exact: true }).waitFor();
    assert.equal((await snapshot()).current_session.id, session);
    await shot('chat-resumed');
    await panel.getByRole('button', { name: '结束本次', exact: true }).click();
    await page.getByRole('button', { name: /^展开专注面板/ }).waitFor({ state: 'hidden' });
    const ended = await snapshot();
    assert.equal(ended.current_session.status, 'ended');
    assert.equal(ended.current_task.status, 'pending');
    await page.goto(base + '/settings');
    if (width === 390) {
      await page.getByRole('button', { name: '返回设置', exact: true }).click();
      await page.getByRole('button', { name: '偏好', exact: true }).click();
    }
    await page.getByRole('radiogroup', { name: '主题色', exact: true }).waitFor();
    assert.equal(await page.locator('.appearance-theme-description').count(), 0);
    assert.equal(await page.getByRole('radiogroup', { name: '主题色', exact: true }).getByRole('radio').count(), 5);
    await shot('settings-audit-retained');
    assert.deepEqual(errors, []);
    results.push({ width, height, sessionPreservedAcrossRoutes: true, endedWithoutCompletingTask: true, themeDescriptionsRemoved: true, errors });
    await context.close();
  }
} finally {
  writeFileSync(resolve(out, 'results.json'), JSON.stringify(results, null, 2));
  await browser.close();
}
console.log(JSON.stringify(results));
