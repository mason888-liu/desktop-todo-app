# 桌面待办小软件

一个用 Electron 实现的本地桌面待办应用，支持：

- 添加待办
- 勾选完成
- 删除待办
- 清除已完成
- 自动本地保存（关闭后再次打开仍保留）

## 运行方式

1. 安装依赖

```bash
npm install
```

2. 启动应用

```bash
npm start
```

## 目录说明

- `main.js`：Electron 主进程，窗口创建与数据读写
- `preload.js`：主进程与渲染进程通信桥接
- `index.html`：界面结构
- `styles.css`：界面样式
- `renderer.js`：待办逻辑与事件处理
