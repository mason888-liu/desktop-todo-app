const { chromium } = require('playwright');
const http = require('http');

let stepNum = 0;
function log(msg) { console.log(`[${new Date().toLocaleTimeString()}] ${msg}`); }
function step(msg) { stepNum++; log(`✅ 第${stepNum}步: ${msg}`); }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getWsUrl() {
  return new Promise((resolve, reject) => {
    http.get('http://localhost:9222/json/version', (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        try { resolve(JSON.parse(d).webSocketDebuggerUrl); }
        catch(e) { reject(e); }
      });
    }).on('error', reject);
  });
}

// Find element by exact text and click via JS
async function clickByText(page, text) {
  const clicked = await page.evaluate((t) => {
    const all = document.querySelectorAll('a, button, span, div, li, dd, dt, label, [class*="tab"], [class*="btn"], [class*="item"], [class*="option"]');
    for (const el of all) {
      const txt = el.textContent?.trim();
      if (txt === t || el.innerText?.trim() === t) {
        // Find the most specific clickable element
        const clickTarget = el.closest('a') || el.closest('button') || el.closest('[class*="tab"]') || el.closest('[class*="item"]') || el;
        clickTarget.click();
        return true;
      }
    }
    return false;
  }, text);
  return clicked;
}

// Click element containing text
async function clickByContains(page, text) {
  const clicked = await page.evaluate((t) => {
    const all = document.querySelectorAll('a, button, span, div, li, dd, dt, label, option, [class*="tab"], [class*="btn"], [class*="item"], [class*="option"], [class*="nav"]');
    for (const el of all) {
      const txt = el.textContent?.trim() || '';
      if (txt.includes(t) && txt.length < 100) {
        const clickTarget = el.closest('a') || el.closest('button') || el.closest('[class*="tab"]') || el.closest('[class*="item"]') || el;
        clickTarget.click();
        return true;
      }
    }
    return false;
  }, text);
  return clicked;
}

// Find visible text on page
async function hasText(page, text) {
  return page.evaluate((t) => {
    return document.body.innerText.includes(t);
  }, text);
}

// Check if table has data rows
async function hasTableData(page) {
  return page.evaluate(() => {
    const rows = document.querySelectorAll('table tbody tr, [class*="table"] [class*="row"]');
    for (const r of rows) {
      const txt = r.textContent?.trim();
      if (txt && txt.length > 5) return true;
    }
    return false;
  });
}

// Check all checkboxes
async function checkAll(page) {
  const done = await page.evaluate(() => {
    const cb = document.querySelector('thead input[type="checkbox"]');
    if (cb) { cb.click(); return true; }
    const cb2 = document.querySelector('[class*="check-all"] input');
    if (cb2) { cb2.click(); return true; }
    return false;
  });
  if (done) { log('  ✓ 全选'); return true; }
  // Fallback: click "全选" text
  return clickByText(page, '全选');
}

// Fill input by placeholder or label
async function fillByLabel(page, searchText, value) {
  const done = await page.evaluate(({ s, v }) => {
    // Try placeholder
    const inputs = document.querySelectorAll('input[type="text"], input:not([type]), textarea');
    for (const inp of inputs) {
      const ph = (inp.placeholder || '').toLowerCase();
      if (ph.includes(s.toLowerCase())) {
        inp.value = v;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    // Try by nearby label text
    const labels = document.querySelectorAll('label, span, div');
    for (const lbl of labels) {
      if ((lbl.textContent || '').trim().includes(s) && lbl.textContent.trim().length < 30) {
        const inp = lbl.parentElement?.querySelector('input, textarea');
        if (inp) {
          inp.value = v;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          inp.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }
      }
    }
    return false;
  }, { s: searchText, v: value });
  return done;
}

async function main() {
  log('========================================');
  log('  自动化脚本 - 最终版');
  log('========================================');

  const wsUrl = await getWsUrl();
  const browser = await chromium.connectOverCDP(wsUrl);
  const context = browser.contexts()[0];

  // Find or create pages
  let djgPage = context.pages().find(p => p.url().includes('fxali.dgjapp.com'));
  let dyPage = context.pages().find(p => p.url().includes('jinritemai.com'));

  // Get token from current DJG URL
  const tokenMatch = djgPage.url().match(/token=([^&]+)/);
  const token = tokenMatch ? tokenMatch[1] : '';

  try {
    // ==========================================
    // 店管家ERP
    // ==========================================
    log('\n========== 店管家ERP操作 ==========');

    // Step 1: Navigate directly to 所有订单
    log('\n--- 1. 进入所有订单 ---');
    await djgPage.goto(`https://fxali.dgjapp.com/Common/Page/NewOrder-AllOrder?token=${token}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await sleep(3000);
    log(`  页面: ${await djgPage.title()}`);
    step('进入订单管理 -> 所有订单');

    // Step 2: 同步订单
    log('\n--- 2. 同步订单 ---');
    const synced2 = await clickByContains(djgPage, '同步订单');
    log(`  点击同步订单: ${synced2}`);
    if (synced2) {
      log('  等待同步完成...');
      for (let i = 0; i < 20; i++) {
        const stillSync = await hasText(djgPage, '同步订单中') || await hasText(djgPage, '同步中');
        if (!stillSync) break;
        log('  同步中...');
        await sleep(3000);
      }
    }
    await sleep(2000);
    step('同步订单完成');

    // Step 3: 点击待发货 -> 自营订单
    log('\n--- 3. 待发货 + 自营订单 ---');
    let clickedDfh = await clickByText(djgPage, '待发货');
    log(`  点击待发货: ${clickedDfh}`);
    await sleep(1500);

    // Click the 全部订单 dropdown filter (3rd option)
    let clickedAll = await clickByContains(djgPage, '全部订单');
    log(`  点击全部订单: ${clickedAll}`);
    await sleep(1000);
    let clickedZy = await clickByText(djgPage, '自营订单');
    log(`  点击自营订单: ${clickedZy}`);
    await sleep(1500);
    step('待发货 + 自营订单');

    // Step 4: 确认 + 查询
    log('\n--- 4. 确认 + 查询 ---');
    const hasZy = await hasText(djgPage, '自营订单');
    const hasDfh = await hasText(djgPage, '待发货');
    log(`  确认: 自营=${hasZy}, 待发货=${hasDfh}`);
    if (!hasZy || !hasDfh) {
      log('  ⚠ 重新设置筛选...');
      await clickByText(djgPage, '待发货');
      await sleep(1000);
      await clickByContains(djgPage, '全部订单');
      await sleep(800);
      await clickByText(djgPage, '自营订单');
      await sleep(1000);
    }
    await clickByContains(djgPage, '查询');
    await sleep(3000);
    step('筛选确认+查询');

    // Step 5: 批量退审
    log('\n--- 5. 批量退审 ---');
    if (await hasTableData(djgPage)) {
      await checkAll(djgPage);
      await sleep(600);
      await clickByContains(djgPage, '批量操作');
      await sleep(800);
      await clickByContains(djgPage, '批量退审');
      await sleep(3000);
      step('批量退审（有订单）');
    } else {
      step('无订单，跳过批量退审');
    }

    // Step 6: 重置 -> 待审核
    log('\n--- 6. 重置 -> 待审核 ---');
    await clickByContains(djgPage, '重置');
    await sleep(1500);
    await clickByText(djgPage, '待审核');
    await sleep(2000);
    step('切换到待审核');

    // Step 7: 商品编码 "陈坡"
    log('\n--- 7. 陈坡筛选 ---');
    await fillByLabel(djgPage, '商品编码', '陈坡');
    await sleep(1000);
    await clickByContains(djgPage, '查询');
    await sleep(3000);
    step('陈坡筛选查询');

    // Step 8: 分配陈坡
    log('\n--- 8. 分配陈坡 ---');
    if (await hasTableData(djgPage)) {
      await checkAll(djgPage);
      await sleep(600);
      await clickByContains(djgPage, '批量操作');
      await sleep(800);
      await clickByContains(djgPage, '批量分配厂家');
      await sleep(1500);
      await clickByText(djgPage, '陈坡');
      await sleep(3000);
      step('分配陈坡（有订单）');
    } else {
      step('无订单，跳过陈坡分配');
    }

    // Step 9: 重置
    log('\n--- 9. 重置 ---');
    await clickByContains(djgPage, '重置');
    await sleep(1500);
    step('重置完成');

    // Step 10: -JD + 省份
    log('\n--- 10. -JD + 省份 ---');
    await fillByLabel(djgPage, '商品编码', '-JD');
    await sleep(1000);
    await clickByContains(djgPage, '所有省份');
    await sleep(1000);
    // Click 3rd option: 包含黑龙江
    await clickByContains(djgPage, '黑龙江');
    await sleep(1000);
    await clickByContains(djgPage, '查询');
    await sleep(3000);
    step('-JD+省份查询');

    // Step 11a: 批量备注
    log('\n--- 11a. 批量卖家备注 ---');
    if (await hasTableData(djgPage)) {
      await checkAll(djgPage);
      await sleep(600);
      await clickByContains(djgPage, '批量操作');
      await sleep(800);
      await clickByContains(djgPage, '批量卖家备注');
      await sleep(1500);
      const ta = djgPage.locator('textarea').first();
      if (await ta.count() > 0) {
        await ta.fill('发富硒虫草蛋普快稻壳，具体枚数以规格为准');
      }
      await sleep(500);
      await clickByContains(djgPage, '确认');
      await sleep(3000);
      step('批量备注（有订单）');

      // 11b: 再次分配陈坡
      log('\n--- 11b. 再次分配陈坡 ---');
      await checkAll(djgPage);
      await sleep(600);
      await clickByContains(djgPage, '批量操作');
      await sleep(800);
      await clickByContains(djgPage, '批量分配厂家');
      await sleep(1500);
      await clickByText(djgPage, '陈坡');
      await sleep(3000);
      step('再次分配陈坡');
    } else {
      step('无订单，跳过备注和分配');
    }

    // Step 12: 重置
    log('\n--- 12. 重置 ---');
    await clickByContains(djgPage, '重置');
    await sleep(1500);
    step('重置完成');

    // Step 13: -JD查询
    log('\n--- 13. -JD 查询 ---');
    await fillByLabel(djgPage, '商品编码', '-JD');
    await sleep(1000);
    await clickByContains(djgPage, '查询');
    await sleep(3000);
    step('-JD查询');

    // Step 14: 分配杨建
    log('\n--- 14. 分配杨建 ---');
    if (await hasTableData(djgPage)) {
      await checkAll(djgPage);
      await sleep(600);
      await clickByContains(djgPage, '批量操作');
      await sleep(800);
      await clickByContains(djgPage, '批量分配厂家');
      await sleep(1500);
      await clickByText(djgPage, '杨建');
      await sleep(3000);
      step('分配杨建（有订单）');
    } else {
      step('无订单，跳过杨建分配');
    }

    // Step 15: 重置
    log('\n--- 15. 重置 ---');
    await clickByContains(djgPage, '重置');
    await sleep(1500);
    step('重置完成');

    // Step 16: 60g
    log('\n--- 16. 60g ---');
    await fillByLabel(djgPage, '商品名称', '60g');
    await sleep(1000);
    await clickByContains(djgPage, '查询');
    await sleep(3000);
    step('60g查询');

    // Step 17: 发顺丰
    log('\n--- 17. 发顺丰备注 ---');
    if (await hasTableData(djgPage)) {
      await checkAll(djgPage);
      await sleep(600);
      await clickByContains(djgPage, '批量操作');
      await sleep(800);
      await clickByContains(djgPage, '批量卖家备注');
      await sleep(1500);
      const ta17 = djgPage.locator('textarea').first();
      if (await ta17.count() > 0) await ta17.fill('发顺丰');
      await sleep(500);
      await clickByContains(djgPage, '确认');
      await sleep(3000);
      step('发顺丰备注（有订单）');
    } else {
      step('无订单，跳过发顺丰备注');
    }

    // ==========================================
    // 抖音小店
    // ==========================================
    log('\n========== 抖音小店后台操作 ==========');

    // DY1: 切换豫南缘
    log('\n--- DY1. 切换到豫南缘 ---');
    if (!dyPage) dyPage = context.pages().find(p => p.url().includes('jinritemai.com'));
    // Hover shop name area (top right)
    await dyPage.bringToFront();
    await sleep(1000);
    await dyPage.mouse.move(1300, 30);
    await sleep(1500);
    await clickByContains(dyPage, '切换店铺');
    await sleep(1500);
    await clickByText(dyPage, '豫南缘');
    await sleep(3000);
    step('切换到豫南缘');

    // DY2: 进入代发订单
    log('\n--- DY2. 进入代发订单 ---');
    // Navigate to 订单发货 first
    await dyPage.goto('https://fxg.jinritemai.com/ffa/mshop/homepage/index', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await sleep(2000);
    await clickByContains(dyPage, '订单');
    await sleep(1500);
    await clickByContains(dyPage, '订单发货');
    await sleep(1500);
    await clickByContains(dyPage, '发货中心');
    await sleep(1500);
    await clickByContains(dyPage, '厂家代发');
    await sleep(1500);
    await clickByContains(dyPage, '代发订单');
    await sleep(3000);
    step('进入代发订单');

    // DY3: 三个筛选
    log('\n--- DY3. 设置筛选 ---');
    await clickByContains(dyPage, '待发货');
    await sleep(1500);
    await clickByContains(dyPage, '未分配');
    await sleep(1500);
    await clickByContains(dyPage, '售后状态');
    await sleep(1000);
    await clickByText(dyPage, '全部');
    await sleep(1500);
    await clickByContains(dyPage, '查询');
    await sleep(3000);
    step('三个筛选条件查询');

    // DY4: 仅展示有备注 + 60g
    log('\n--- DY4. 仅备注 + 60g ---');
    await clickByContains(dyPage, '仅展示有备注');
    await sleep(1000);
    await fillByLabel(dyPage, '商品名', '60g');
    await sleep(1000);
    await clickByContains(dyPage, '查询');
    await sleep(3000);
    step('60g+仅备注查询');

    // DY5: 分配我老家
    log('\n--- DY5. 分配我老家官方旗舰店 ---');
    if (await hasTableData(dyPage)) {
      await checkAll(dyPage);
      await sleep(600);
      await clickByContains(dyPage, '批量分配');
      await sleep(1500);
      await clickByContains(dyPage, '我老家');
      await sleep(3000);
      step('分配我老家（有订单）');
    } else {
      step('无订单，跳过分配');
    }

    // DY6: 切换百姓安心蛋
    log('\n--- DY6. 切换百姓安心蛋 ---');
    await dyPage.mouse.move(1300, 30);
    await sleep(1500);
    await clickByContains(dyPage, '切换店铺');
    await sleep(1500);
    await clickByText(dyPage, '百姓安心蛋');
    await sleep(3000);
    step('切换到百姓安心蛋');

    // DY7: 确认在代发订单 + 筛选
    log('\n--- DY7. 确认筛选 ---');
    const hasDfd = await hasText(dyPage, '代发订单');
    if (!hasDfd) {
      await dyPage.goto('https://fxg.jinritemai.com/ffa/mshop/homepage/index', { waitUntil: 'domcontentloaded', timeout: 15000 });
      await sleep(2000);
      await clickByContains(dyPage, '订单发货');
      await sleep(1500);
      await clickByContains(dyPage, '发货中心');
      await sleep(1500);
      await clickByContains(dyPage, '厂家代发');
      await sleep(1500);
      await clickByContains(dyPage, '代发订单');
      await sleep(3000);
    }
    await clickByContains(dyPage, '待发货');
    await sleep(1500);
    await clickByContains(dyPage, '未分配');
    await sleep(1500);
    await clickByContains(dyPage, '全部');
    await sleep(1500);
    step('筛选条件确认');

    // DY8: 商品名 + 规格
    log('\n--- DY8. 商品名 + 规格 ---');
    await fillByLabel(dyPage, '商品名', '京东上门20/30/40枚新鲜高山散养富硒虫草蛋可生吞谷物土鸡蛋6枚');
    await sleep(1000);
    await fillByLabel(dyPage, '规格', '6枚试吃装');
    await sleep(1000);
    await clickByContains(dyPage, '查询');
    await sleep(3000);
    step('商品名+规格查询');

    // DY9: 分配燕归谷
    log('\n--- DY9. 分配燕归谷 ---');
    if (await hasTableData(dyPage)) {
      await checkAll(dyPage);
      await sleep(600);
      await clickByContains(dyPage, '批量分配');
      await sleep(1500);
      await clickByContains(dyPage, '燕归谷');
      await sleep(3000);
      step('分配燕归谷（有订单）');
    } else {
      step('无订单，跳过燕归谷分配');
    }

    log('\n========================================');
    log(`  🎉 全部完成！(${stepNum}步)`);
    log('========================================');

  } catch (e) {
    log(`❌ 出错: ${e.message}`);
    console.error(e.stack);
  }
  log('\n浏览器保持打开，核查后关闭。');
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
