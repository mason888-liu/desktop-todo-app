const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("todoAPI", {
  loadTodos: () => ipcRenderer.invoke("todos:load"),
  saveTodos: (todos) => ipcRenderer.invoke("todos:save", todos)
});
