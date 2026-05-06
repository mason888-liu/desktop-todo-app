const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");

const dataFilePath = path.join(app.getPath("userData"), "todos.json");

function readTodos() {
  try {
    if (!fs.existsSync(dataFilePath)) {
      return [];
    }
    const file = fs.readFileSync(dataFilePath, "utf-8");
    return JSON.parse(file);
  } catch (error) {
    console.error("Failed to read todos:", error);
    return [];
  }
}

function saveTodos(todos) {
  try {
    fs.writeFileSync(dataFilePath, JSON.stringify(todos, null, 2), "utf-8");
    return { ok: true };
  } catch (error) {
    console.error("Failed to save todos:", error);
    return { ok: false, message: "保存失败，请重试。" };
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 700,
    height: 800,
    minWidth: 480,
    minHeight: 560,
    title: "桌面待办",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  win.loadFile("index.html");
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

ipcMain.handle("todos:load", () => {
  return readTodos();
});

ipcMain.handle("todos:save", (_event, todos) => {
  return saveTodos(todos);
});
