---
name: Tabbit Browser 操作录制
description: 启动 Tabbit 浏览器并注入操作录制脚本，实时记录用户在店管家/DJ 或抖店平台上的所有点击和输入操作，输出结构化选择器文件供后续自动化脚本使用。
---

# Tabbit Browser 操作录制器

启动 Tabbit 浏览器（复用持久化登录态），注入 JS 录制脚本，记录用户全部操作到选择器文件。

## 使用方式

用户调用时需指定平台：
- `djg` / `店管家` → 录制店管家操作
- `douyin` / `抖店` → 录制抖店操作

可选参数：
- `--url <URL>` 自定义起始页面

## 录制输出

输出文件：`E:/first_cc/<platform>_selectors.txt`

格式：
- `## 步骤N: 页面导航` — 页面加载事件
- `--- 点击 #N ---` — 点击事件，含 Tag/Text/Class/ID/Name/ARIA/ParentClass/URL
- `--- 输入 #N ---` — 输入事件，含 Tag/Type/Value/Placeholder/ID/Name

## 执行流程

1. 关闭已有的 Tabbit 进程（释放 User Data 目录锁）
2. 通过 `launchPersistentContext` 启动 Tabbit，复用 `C:/Users/Administrator/AppData/Local/Tabbit Browser/User Data`
3. 注入录制脚本（`addInitScript` — 跨导航持久化）
4. 导航至目标平台首页
5. 终端输出实时录制日志，同时追加写入选择器文件
6. 用户操作完成后关闭浏览器窗口，脚本自动退出

## 录制脚本实现

使用统一的 Node.js 脚本 `E:/first_cc/record_<platform>.js`：

```js
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');

const TABBIT_EXE = 'C:/Users/Administrator/AppData/Local/Tabbit Browser/Application/Tabbit Browser.exe';
const USER_DATA_DIR = 'C:/Users/Administrator/AppData/Local/Tabbit Browser/User Data';

// Kill existing Tabbit
try { execSync('taskkill /F /IM "Tabbit Browser.exe"', { timeout: 8000, stdio: 'pipe' }); } catch {}

// Platform configs
const PLATFORMS = {
  dgj: {
    url: 'https://tfxportal.dgjapp.com/FFAccount?...',
    output: 'E:/first_cc/dgj_selectors.txt',
  },
  douyin: {
    url: 'https://fxg.jinritemai.com/ffa/mshop/homepage/index',
    output: 'E:/first_cc/douyin_selectors.txt',
  },
};

const config = PLATFORMS[process.argv[2] || 'dgj'];

// Inject recorder (IIFE with injection guard)
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
      tag: target.tagName, type: target.type || '',
      placeholder: target.placeholder || '',
      class: (target.className || '').toString().slice(0, 250),
      text: (target.innerText || '').replace(/\\n/g, ' ').trim().slice(0, 200),
      id: target.id || '', name: target.getAttribute('name') || '',
      ariaLabel: target.getAttribute('aria-label') || '',
      role: target.getAttribute('role') || '', href: target.href || '',
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
        tag: el.tagName, type: el.type || '',
        placeholder: el.placeholder || '', value: (el.value || '').slice(0, 200),
        class: (el.className || '').toString().slice(0, 250),
        id: el.id || '', name: el.getAttribute('name') || '',
        ariaLabel: el.getAttribute('aria-label') || '',
        url: location.href.slice(0, 200),
      };
      window.__recordInput(JSON.stringify(info));
    }
  }, true);
})()`;

(async () => {
  fs.writeFileSync(config.output, `=== ${process.argv[2]} 选择器记录 ===\n${new Date().toISOString()}\n\n`);
  await new Promise(r => setTimeout(r, 3000));

  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    executablePath: TABBIT_EXE,
    headless: false,
    viewport: { width: 1440, height: 900 },
  });

  const page = context.pages()[0] || await context.newPage();

  await page.exposeFunction('__recordClick', (json) => {
    const info = JSON.parse(json);
    const entry = [
      '', '--- 点击 #' + (++clickCount) + ' ---',
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
    fs.appendFileSync(config.output, entry);
  });

  await page.exposeFunction('__recordInput', (json) => {
    const info = JSON.parse(json);
    const entry = [
      '', '--- 输入 #' + (++inputCount) + ' ---',
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
    fs.appendFileSync(config.output, entry);
  });

  await page.addInitScript(injectRecorder);

  page.on('load', async () => {
    const url = page.url();
    const title = await page.title().catch(() => '(无法获取标题)');
    const entry = '\n## 步骤' + (++stepNum) + ': 页面导航\n  URL: ' + url + '\n  Title: ' + title + '\n  Time: ' + new Date().toISOString() + '\n';
    fs.appendFileSync(config.output, entry);
  });

  await page.goto(config.url, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);

  console.log('\n========================================');
  console.log('  录制已就绪！请在浏览器中操作。');
  console.log('  平台:', process.argv[2], '| 文件:', config.output);
  console.log('  完成后关闭浏览器或按 Ctrl+C。');
  console.log('========================================\n');
})();
```

## 运行命令

```bash
# 录制店管家
node E:/first_cc/record_dgj.js dgj

# 录制抖店
node E:/first_cc/record_douyin.js douyin
```

## 重要提示

- Tabbit 浏览器需已安装于默认路径
- 录制前关闭浏览器标签页避免累积
- 操作完成后关闭浏览器窗口即可自动退出录制
- 选择器文件会追加到已有文件（不会清空历史记录）
