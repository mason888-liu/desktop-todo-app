import json
import os
import tkinter as tk
from tkinter import messagebox


APP_TITLE = "桌面待办"
DATA_FILE = os.path.join(os.path.dirname(__file__), "todos.json")

# Color palette inspired by the provided logo.
BG_COLOR = "#F4F7F3"
PANEL_COLOR = "#FFFFFF"
PRIMARY_GREEN = "#02A54F"
DARK_GREEN = "#008A42"
ACCENT_ORANGE = "#F39B16"
TEXT_COLOR = "#123322"
MUTED_TEXT = "#5A7062"
DONE_TEXT = "#8A9A91"


class TodoApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("520x620")
        self.root.minsize(420, 460)
        self.root.configure(bg=BG_COLOR)

        self.todos = []

        self.build_ui()
        self.load_todos()
        self.refresh_list()

    def build_ui(self):
        wrapper = tk.Frame(self.root, padx=16, pady=16, bg=BG_COLOR)
        wrapper.pack(fill=tk.BOTH, expand=True)

        title = tk.Label(
            wrapper,
            text="我的待办",
            font=("Microsoft YaHei UI", 20, "bold"),
            fg=PRIMARY_GREEN,
            bg=BG_COLOR,
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            wrapper,
            text="添加、完成、删除，自动本地保存",
            fg=MUTED_TEXT,
            bg=BG_COLOR,
            font=("Microsoft YaHei UI", 10),
        )
        subtitle.pack(anchor="w", pady=(2, 12))

        input_row = tk.Frame(wrapper, bg=BG_COLOR)
        input_row.pack(fill=tk.X, pady=(0, 10))

        self.entry = tk.Entry(
            input_row,
            font=("Microsoft YaHei UI", 11),
            fg=TEXT_COLOR,
            bg=PANEL_COLOR,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=PRIMARY_GREEN,
            highlightcolor=PRIMARY_GREEN,
            insertbackground=TEXT_COLOR,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda _e: self.add_todo())

        add_btn = tk.Button(
            input_row,
            text="添加",
            width=10,
            command=self.add_todo,
            bg=PRIMARY_GREEN,
            fg="white",
            activebackground=DARK_GREEN,
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        add_btn.pack(side=tk.LEFT, padx=(8, 0))

        stats_row = tk.Frame(wrapper, bg=BG_COLOR)
        stats_row.pack(fill=tk.X, pady=(0, 10))

        self.stats_label = tk.Label(stats_row, text="0 / 0 项待办", fg=MUTED_TEXT, bg=BG_COLOR)
        self.stats_label.pack(side=tk.LEFT)

        clear_btn = tk.Button(
            stats_row,
            text="清除已完成",
            command=self.clear_completed,
            bg=ACCENT_ORANGE,
            fg="white",
            activebackground="#E5890C",
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        clear_btn.pack(side=tk.RIGHT)

        list_frame = tk.Frame(wrapper, bg=BG_COLOR)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(
            list_frame,
            font=("Microsoft YaHei UI", 11),
            activestyle="none",
            selectmode=tk.SINGLE,
            bg=PANEL_COLOR,
            fg=TEXT_COLOR,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#D6E8DC",
            selectbackground="#CDEEDB",
            selectforeground=TEXT_COLOR,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.toggle_selected())

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        actions = tk.Frame(wrapper, bg=BG_COLOR)
        actions.pack(fill=tk.X, pady=(10, 0))

        done_btn = tk.Button(
            actions,
            text="切换完成状态",
            command=self.toggle_selected,
            bg=PRIMARY_GREEN,
            fg="white",
            activebackground=DARK_GREEN,
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        done_btn.pack(side=tk.LEFT)

        del_btn = tk.Button(
            actions,
            text="删除选中",
            command=self.delete_selected,
            bg=ACCENT_ORANGE,
            fg="white",
            activebackground="#E5890C",
            activeforeground="white",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        del_btn.pack(side=tk.LEFT, padx=(8, 0))

    def load_todos(self):
        if not os.path.exists(DATA_FILE):
            self.todos = []
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.todos = data
                else:
                    self.todos = []
        except Exception:
            self.todos = []

    def save_todos(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.todos, f, ensure_ascii=False, indent=2)

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        if not self.todos:
            self.listbox.insert(tk.END, "还没有任务，先添加一个吧。")
            self.listbox.itemconfig(0, fg=MUTED_TEXT)
            self.stats_label.config(text="0 / 0 项待办")
            return

        remain = 0
        for item in self.todos:
            completed = bool(item.get("completed"))
            text = str(item.get("text", "")).strip()
            prefix = "✓" if completed else "○"
            display = f"{prefix} {text}"
            self.listbox.insert(tk.END, display)
            if completed:
                idx = self.listbox.size() - 1
                self.listbox.itemconfig(idx, fg=DONE_TEXT)
            else:
                remain += 1

        self.stats_label.config(text=f"{remain} / {len(self.todos)} 项待办")

    def add_todo(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.todos.insert(0, {"text": text, "completed": False})
        self.entry.delete(0, tk.END)
        self.save_todos()
        self.refresh_list()

    def get_selected_index(self):
        if not self.todos:
            return None
        selected = self.listbox.curselection()
        if not selected:
            return None
        idx = selected[0]
        if idx < 0 or idx >= len(self.todos):
            return None
        return idx

    def toggle_selected(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        self.todos[idx]["completed"] = not bool(self.todos[idx].get("completed"))
        self.save_todos()
        self.refresh_list()

    def delete_selected(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        del self.todos[idx]
        self.save_todos()
        self.refresh_list()

    def clear_completed(self):
        if not self.todos:
            return
        new_todos = [item for item in self.todos if not bool(item.get("completed"))]
        if len(new_todos) == len(self.todos):
            messagebox.showinfo(APP_TITLE, "没有已完成任务可清除。")
            return
        self.todos = new_todos
        self.save_todos()
        self.refresh_list()


def main():
    root = tk.Tk()
    TodoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
