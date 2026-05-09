const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');

console.log('关闭已有 Tabbit 进程...');
try {
  execSync('taskkill /F /IM "Tabbit Browser.exe"', { timeout: 8000, stdio: 'pipe' });
} catch {}

const TABBIT_EXE = 'C:/Users/Administrator/AppData/Local/Tabbit Browser/Application/Tabbit Browser.exe';
const USER_DATA_DIR = 'C:/Users/Administrator/AppData/Local/Tabbit Browser/User Data';
const DOUYIN_URL = 'https://fxg.jinritemai.com/ffa/mshop/homepage/index';
const OUTPUT = 'E:/first_cc/douyin_selectors.txt';

let stepNum = 0;
let clickCount = 0;
let inputCount = 0;

const injectRecorder = `(() => {
  if (window.__recorderInjected) return;
  window.__recorderInjected = true;

  document.addEventListener('click', function(e) {
    const el = e.target;
    let target = el;
    for (let i = 0; i < 5; i++) {
      if (!target) break;
      const tn = target.tagName;
      if (tn === 'BUTTON' || tn === 'A' || tn === 'LABEL' || tn === 'SPAN' || tn === 'LI' || tn === 'DIV') {
        if ((target.innerText || '').trim().length > 0) break;
      }
      if (tn === 'INPUT' || tn === 'TEXTAREA' || tn === 'SELECT') break;
      target = target.parentElement;
    }
    if (!target) target = el;
    const info = {
      tag: target.tagName,
      type: target.type || '',
      placeholder: target.placeholder || '',
      class: (target.className || '').toString().slice(0, 250),
      text: (target.innerText || '').replace(/\\n/g, ' ').trim().slice(0, 200),
      id: target.id || '',
      name: target.getAttribute('name') || '',
      ariaLabel: target.getAttribute('aria-label') || '',
      role: target.getAttribute('role') || '',
      href: target.href || '',
      dataTestid: target.getAttribute('data-testid') || '',
      parentClass: (target.parentElement ? target.parentElement.className : '').toString().slice(0, 250),
      url: location.href.slice(0, 200),
    };
    window.__recordClick(JSON.stringify(info));
  }, true);

  document.addEventListener('change', function(e) {
    const el = e.target;
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
      const info = {
        tag: el.tagName,
        type: el.type || '',
        placeholder: el.placeholder || '',
        value: (el.value || '').slice(0, 200),
        class: (el.className || '').toString().slice(0, 250),
        id: el.id || '',
        name: el.getAttribute('name') || '',
        ariaLabel: el.getAttribute('aria-label') || '',
        url: location.href.slice(0, 200),
      };
      window.__recordInput(JSON.stringify(info));
    }
  }, true);
})()`;

(async () => {
  fs.writeFileSync(OUTPUT, `=== 抖店选择器记录 ===\n${new Date().toISOString()}\n\n`);

  console.log('等待进程退出...');
  await new Promise(r => setTimeout(r, 3000));

  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: TABBIT_EXE,
    headless: false,
    viewport: { width: 1440, height: 900 },
  });

  const page = context.pages()[0] || await context.newPage();

  await page.exposeFunction('__recordClick', (json) => {
    clickCount++;
    const info = JSON.parse(json);
    const entry = [
      '',
      '--- 点击 #' + clickCount + ' ---',
      '  URL:         ' + (info.url || 'N/A'),
      '  Tag:         ' + info.tag,
      '  Text:        ' + info.text,
      '  Class:       ' + info.class,
      '  Type:        ' + info.type,
      '  Placeholder: ' + info.placeholder,
      '  ID:          ' + info.id,
      '  Name:        ' + info.name,
      '  ARIA Label:  ' + info.ariaLabel,
      '  Role:        ' + info.role,
      '  Href:        ' + info.href,
      '  Data-TestID: ' + info.dataTestid,
      '  ParentClass: ' + info.parentClass,
      '',
    ].join('\n');
    fs.appendFileSync(OUTPUT, entry);
    console.log('[录] 点击 #' + clickCount + ': <' + info.tag + '> "' + info.text.slice(0, 60) + '"');
  });

  await page.exposeFunction('__recordInput', (json) => {
    inputCount++;
    const info = JSON.parse(json);
    const entry = [
      '',
      '--- 输入 #' + inputCount + ' ---',
      '  URL:         ' + (info.url || 'N/A'),
      '  Tag:         ' + info.tag,
      '  Type:        ' + info.type,
      '  Placeholder: ' + info.placeholder,
      '  Value:       ' + info.value,
      '  Class:       ' + info.class,
      '  ID:          ' + info.id,
      '  Name:        ' + info.name,
      '  ARIA Label:  ' + info.ariaLabel,
      '',
    ].join('\n');
    fs.appendFileSync(OUTPUT, entry);
    console.log('[录] 输入 #' + inputCount + ': <' + info.tag + '> "' + info.value.slice(0, 60) + '"');
  });

  await page.addInitScript(injectRecorder);

  page.on('load', async () => {
    stepNum++;
    const url = page.url();
    const title = await page.title().catch(() => '(无法获取标题)');
    const entry = '\n## 步骤' + stepNum + ': 页面导航\n  URL: ' + url + '\n  Title: ' + title + '\n  Time: ' + new Date().toISOString() + '\n';
    fs.appendFileSync(OUTPUT, entry);
    console.log('[录] 页面 #' + stepNum + ': ' + (title || url.slice(0, 80)));
  });

  await page.goto(DOUYIN_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  console.log('\n========================================');
  console.log('  抖店录制已就绪！请在浏览器中操作。');
  console.log('  每步操作都会实时输出到终端和文件。');
  console.log('  文件: ' + OUTPUT);
  console.log('  完成后关闭浏览器或按 Ctrl+C。');
  console.log('========================================\n');
})();
