import os
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk

from browser import DATA, ROOT, SITE, NeedsLogin, browser, login
from library import attach, list_requests, lookup, try_open_copy, update
from workflow import run, sign_status

STATES = {
    'draft': '待授权', 'queued': '待提交', 'submitting': '核对发布结果',
    'uncertain': '核对发布结果', 'submitted': '跟踪中', 'downloaded': '已保存',
    'review': '文件待核对', 'action': '待手动处理',
}


def sign_in_and_sync():
    login()
    run()


def show_site(url):
    with browser(headless=False) as context:
        page = context.pages[0]
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        closed = threading.Event()
        context.on('close', lambda _: closed.set())
        while not closed.is_set() and context.pages:
            try:
                context.pages[0].wait_for_timeout(500)
            except Exception:
                if not context.pages or closed.is_set():
                    break
                raise


class Window(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('科研通助手')
        self.geometry('900x560')
        self.minsize(720, 490)
        self.doi = tk.StringVar()
        self.status = tk.StringVar()
        self.busy = False
        self.rows = {}
        self.configure(padx=20, pady=17)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, sticky='ew', pady=(0, 12))
        ttk.Label(top, text='科研通助手', font=('Microsoft YaHei UI', 17, 'bold')).pack(side='left')
        ttk.Button(top, text='登录科研通', command=lambda: self.work(sign_in_and_sync)).pack(side='right')
        ttk.Button(top, text='签到并同步', command=lambda: self.work(run)).pack(side='right', padx=6)
        ttk.Label(self, textvariable=self.status, wraplength=800).grid(row=1, sticky='w', pady=(0, 14))

        search = ttk.Frame(self)
        search.grid(row=2, sticky='ew', pady=(0, 10))
        ttk.Label(search, text='DOI 或 DOI 链接').pack(side='left', padx=(0, 8))
        entry = ttk.Entry(search, textvariable=self.doi)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda _: self.add())
        ttk.Button(search, text='添加文献', command=self.add).pack(side='right', padx=(8, 0))

        table = ttk.Frame(self)
        table.grid(row=3, sticky='nsew')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=('title', 'state'), show='headings', selectmode='browse')
        self.tree.heading('title', text='文献')
        self.tree.heading('state', text='状态')
        self.tree.column('title', width=650)
        self.tree.column('state', width=140, stretch=False)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.show_note())

        self.detail = tk.StringVar()
        ttk.Label(self, textvariable=self.detail, wraplength=800).grid(row=4, sticky='w', pady=(8, 8))
        actions = ttk.Frame(self)
        actions.grid(row=5, sticky='ew')
        ttk.Button(actions, text='授权发布', command=self.authorize).pack(side='left')
        ttk.Button(actions, text='打开官网求助页', command=self.open_request).pack(side='left', padx=6)
        ttk.Button(actions, text='绑定已发布链接', command=self.bind_post).pack(side='left')
        ttk.Button(actions, text='打开文献目录', command=self.open_folder).pack(side='right')
        ttk.Button(actions, text='刷新', command=self.refresh).pack(side='right', padx=6)
        self.refresh()

    def selected(self):
        ids = self.tree.selection()
        return self.rows.get(ids[0]) if ids else None

    def show_note(self):
        row = self.selected()
        self.detail.set(f"{row['doi']}  ·  {row['note']}" if row else '')

    def refresh(self):
        selected = self.tree.selection()
        self.rows = {row['doi']: row for row in list_requests()}
        self.tree.delete(*self.tree.get_children())
        for doi, row in self.rows.items():
            self.tree.insert('', 'end', iid=doi, values=(row['title'], STATES[row['state']]))
        if selected and selected[0] in self.rows:
            self.tree.selection_set(selected[0])
        self.status.set(sign_status())
        self.show_note()

    def work(self, operation, done=None):
        if self.busy:
            self.status.set('正在处理，请稍等或关闭专用浏览器窗口。')
            return
        self.busy = True
        self.status.set('正在处理…')

        def perform():
            result, error = None, None
            try:
                result = operation()
            except (ValueError, RuntimeError) as exc:
                error = str(exc)
            except Exception as exc:
                error = f'操作未完成（{type(exc).__name__}），请检查网络或重试。'
            self.after(0, lambda: complete(result, error))

        def complete(result, error):
            self.busy = False
            self.refresh()
            if error:
                self.status.set(error)
            elif done:
                done(result)

        threading.Thread(target=perform, daemon=True).start()

    def add(self):
        value = self.doi.get()

        def find():
            row = lookup(value)
            if row['state'] == 'draft':
                try_open_copy(row)
            return row['doi']

        def select(doi):
            self.doi.set('')
            self.tree.selection_set(doi)
            self.tree.see(doi)

        self.work(find, select)

    def authorize(self):
        row = self.selected()
        if self.busy or not row or row['state'] not in ('draft', 'action'):
            return
        points = simpledialog.askinteger('授权发布求助',
            f"{row['title']}\n{row['doi']}\n\n如未获得公开全文，授权发布一次正文求助。请输入悬赏积分。",
            parent=self, initialvalue=row['points'] or 10, minvalue=1)
        if points is not None and update(row['doi'], 'queued', '已授权，等待提交。', before=row['state'], points=points):
            self.work(lambda: run(checkin=False))

    def open_request(self):
        row = self.selected()
        url = row['post_url'] if row and row['post_url'] else SITE + '/assist/create'
        if row and not row['post_url']:
            self.clipboard_clear()
            self.clipboard_append(row['doi'])
        self.work(lambda: show_site(url))

    def bind_post(self):
        row = self.selected()
        if not row or self.busy:
            return
        if row['state'] not in ('draft', 'action', 'uncertain', 'submitting'):
            return
        url = simpledialog.askstring('绑定已发布链接', '粘贴这篇文献在科研通的求助详情页地址', parent=self)
        if url:
            try:
                attach(row['doi'], url, row['state'])
            except ValueError as exc:
                messagebox.showerror('无法绑定', str(exc), parent=self)
            self.refresh()

    @staticmethod
    def open_folder():
        directory = DATA / '文献'
        directory.mkdir(exist_ok=True)
        os.startfile(directory)


def background():
    DATA.mkdir(exist_ok=True)
    status = DATA / '最近一次同步.txt'
    message = '同步结束。' + sign_status()
    try:
        run()
        message = '同步结束。' + sign_status()
    except NeedsLogin as exc:
        if not status.exists() or str(exc) not in status.read_text(encoding='utf-8'):
            try:
                subprocess.Popen(['msg.exe', os.environ['USERNAME'], '/TIME:25', '科研通需要重新登录，请打开科研通助手。'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            except OSError:
                pass
        message = str(exc)
    except RuntimeError as exc:
        message = str(exc)
    except Exception as exc:
        message = f'同步未完成（{type(exc).__name__}）。'
    status.write_text(f'{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n', encoding='utf-8')


if __name__ == '__main__':
    if '--background' in sys.argv:
        background()
    else:
        Window().mainloop()
