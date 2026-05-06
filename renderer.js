const todoInput = document.getElementById("todo-input");
const addBtn = document.getElementById("add-btn");
const todoList = document.getElementById("todo-list");
const stats = document.getElementById("stats");
const clearCompletedBtn = document.getElementById("clear-completed-btn");

let todos = [];

function makeTodo(text) {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    text,
    completed: false,
    createdAt: Date.now()
  };
}

function escapeHTML(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function persistTodos() {
  const result = await window.todoAPI.saveTodos(todos);
  if (!result.ok) {
    alert(result.message || "保存失败");
  }
}

function updateStats() {
  const total = todos.length;
  const remaining = todos.filter((item) => !item.completed).length;
  stats.textContent = `${remaining} / ${total} 项待办`;
}

function render() {
  if (todos.length === 0) {
    todoList.innerHTML = `<li class="empty">还没有任务，先添加一个吧。</li>`;
    updateStats();
    return;
  }

  const html = todos
    .map((todo) => {
      const safeText = escapeHTML(todo.text);
      return `
        <li class="todo-item ${todo.completed ? "done" : ""}" data-id="${todo.id}">
          <label class="left">
            <input type="checkbox" ${todo.completed ? "checked" : ""} />
            <span>${safeText}</span>
          </label>
          <button class="danger delete-btn">删除</button>
        </li>
      `;
    })
    .join("");

  todoList.innerHTML = html;
  updateStats();
}

async function addTodo() {
  const text = todoInput.value.trim();
  if (!text) return;
  todos.unshift(makeTodo(text));
  todoInput.value = "";
  render();
  await persistTodos();
}

async function toggleTodo(id) {
  todos = todos.map((todo) =>
    todo.id === id ? { ...todo, completed: !todo.completed } : todo
  );
  render();
  await persistTodos();
}

async function deleteTodo(id) {
  todos = todos.filter((todo) => todo.id !== id);
  render();
  await persistTodos();
}

async function clearCompleted() {
  const hasCompleted = todos.some((todo) => todo.completed);
  if (!hasCompleted) return;
  todos = todos.filter((todo) => !todo.completed);
  render();
  await persistTodos();
}

async function boot() {
  const loaded = await window.todoAPI.loadTodos();
  if (Array.isArray(loaded)) {
    todos = loaded;
  }
  render();
}

addBtn.addEventListener("click", addTodo);
todoInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    addTodo();
  }
});

todoList.addEventListener("click", (event) => {
  const item = event.target.closest(".todo-item");
  if (!item) return;
  const id = item.dataset.id;
  if (!id) return;

  if (event.target.matches(".delete-btn")) {
    deleteTodo(id);
  }
});

todoList.addEventListener("change", (event) => {
  const item = event.target.closest(".todo-item");
  if (!item) return;
  const id = item.dataset.id;
  if (!id) return;

  if (event.target.matches('input[type="checkbox"]')) {
    toggleTodo(id);
  }
});

clearCompletedBtn.addEventListener("click", clearCompleted);

boot();
