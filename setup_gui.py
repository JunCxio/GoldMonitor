"""金价监控 - 图形化安装程序"""
import os, sys, shutil, tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_NAME = "金价监控"
DEFAULT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "GoldMonitor")


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - 安装向导")
        self.geometry("520x420")
        self.resizable(False, False)
        self.configure(bg="#16162a")

        try:
            self.iconbitmap(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "icon.ico")
            )
        except Exception:
            pass

        self.install_dir = tk.StringVar(value=DEFAULT_DIR)
        self.create_desktop = tk.BooleanVar(value=True)
        self.create_startmenu = tk.BooleanVar(value=True)
        self.auto_start = tk.BooleanVar(value=True)
        self.src_dir = os.path.dirname(os.path.abspath(__file__))

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#16162a", foreground="#d8d8e0", fieldbackground="#12122a")
        style.configure("TLabel", background="#16162a", foreground="#d8d8e0", font=("Microsoft YaHei", 10))
        style.configure("TButton", font=("Microsoft YaHei", 10), padding=6)
        style.configure("TCheckbutton", background="#16162a", foreground="#d8d8e0", font=("Microsoft YaHei", 10))
        style.configure("TEntry", fieldbackground="#12122a", foreground="#d8d8e0", font=("Microsoft YaHei", 10))
        style.configure("TProgressbar", troughcolor="#12122a", background="#e8b830")

        # 标题
        title = tk.Label(
            self, text=APP_NAME, font=("Microsoft YaHei", 22, "bold"),
            bg="#16162a", fg="#e8b830"
        )
        title.pack(pady=(24, 4))
        subtitle = tk.Label(
            self, text="实时黄金价格监控与预警系统", font=("Microsoft YaHei", 10),
            bg="#16162a", fg="#7a7a90"
        )
        subtitle.pack()

        # 分隔线
        sep = tk.Frame(self, height=1, bg="#2a2a40")
        sep.pack(fill="x", padx=40, pady=16)

        # 安装位置
        loc_frame = tk.Frame(self, bg="#16162a")
        loc_frame.pack(fill="x", padx=40)
        tk.Label(loc_frame, text="安装位置", bg="#16162a", fg="#7a7a90", font=("Microsoft YaHei", 9)).pack(anchor="w")
        row = tk.Frame(loc_frame, bg="#16162a")
        row.pack(fill="x", pady=(4, 0))
        self.loc_entry = tk.Entry(row, textvariable=self.install_dir, font=("Consolas", 9),
                                  bg="#12122a", fg="#d8d8e0", insertbackground="#d8d8e0",
                                  relief="flat", bd=6)
        self.loc_entry.pack(side="left", fill="x", expand=True)
        btn = tk.Button(row, text="浏览", command=self._browse, font=("Microsoft YaHei", 9),
                        bg="#2a2a40", fg="#d8d8e0", relief="flat", padx=12, cursor="hand2")
        btn.pack(side="right", padx=(6, 0))

        # 选项
        opt_frame = tk.Frame(self, bg="#16162a")
        opt_frame.pack(fill="x", padx=40, pady=(16, 0))
        ttk.Checkbutton(opt_frame, text="创建桌面快捷方式", variable=self.create_desktop).pack(anchor="w", pady=2)
        ttk.Checkbutton(opt_frame, text="创建开始菜单快捷方式", variable=self.create_startmenu).pack(anchor="w", pady=2)
        ttk.Checkbutton(opt_frame, text="安装完成后启动程序", variable=self.auto_start).pack(anchor="w", pady=2)

        # 进度条
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=400)
        self.progress.pack(pady=(20, 0))

        # 按钮
        btn_frame = tk.Frame(self, bg="#16162a")
        btn_frame.pack(pady=20)
        self.install_btn = tk.Button(
            btn_frame, text="  开始安装  ", command=self._install,
            font=("Microsoft YaHei", 12, "bold"), bg="#e8b830", fg="#141416",
            relief="flat", padx=30, pady=8, cursor="hand2"
        )
        self.install_btn.pack()

    def _browse(self):
        path = filedialog.askdirectory(title="选择安装位置", initialdir=self.install_dir.get())
        if path:
            self.install_dir.set(path)

    def _install(self):
        target = self.install_dir.get()
        if not target:
            messagebox.showerror("错误", "请选择安装位置")
            return

        self.install_btn.config(state="disabled", text="安装中...")
        self.progress.start(10)
        self.update()

        try:
            os.makedirs(target, exist_ok=True)

            # 复制 EXE
            src_exe = os.path.join(self.src_dir, "dist", "GoldMonitor.exe")
            dst_exe = os.path.join(target, "GoldMonitor.exe")
            shutil.copy2(src_exe, dst_exe)

            # 复制图标
            src_ico = os.path.join(self.src_dir, "static", "icon.ico")
            dst_ico = os.path.join(target, "icon.ico")
            if os.path.exists(src_ico):
                shutil.copy2(src_ico, dst_ico)

            # 快捷方式
            desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
            startmenu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)

            if self.create_startmenu.get():
                os.makedirs(startmenu, exist_ok=True)
                self._make_shortcut(os.path.join(startmenu, f"{APP_NAME}.lnk"), dst_exe, dst_ico)
                self._make_uninstaller(startmenu, target, desktop)

            if self.create_desktop.get():
                self._make_shortcut(os.path.join(desktop, f"{APP_NAME}.lnk"), dst_exe, dst_ico)

            self.progress.stop()
            messagebox.showinfo("安装完成", f"{APP_NAME} 安装成功！\n\n位置: {target}")

            if self.auto_start.get():
                os.startfile(dst_exe)

            self.destroy()
        except Exception as e:
            self.progress.stop()
            messagebox.showerror("安装失败", str(e))
            self.install_btn.config(state="normal", text="  开始安装  ")

    def _make_shortcut(self, path, target, icon):
        try:
            import pythoncom
            from win32com.client import Dispatch
            shell = Dispatch("WScript.Shell")
            sc = shell.CreateShortcut(path)
            sc.TargetPath = target
            sc.WorkingDirectory = os.path.dirname(target)
            sc.IconLocation = icon
            sc.Description = APP_NAME
            sc.Save()
        except ImportError:
            with open(path + ".url", "w") as f:
                f.write(f"[InternetShortcut]\nURL=file:///{target}\nIconFile={icon}\n")

    def _make_uninstaller(self, startmenu, target_dir, desktop_dir):
        bat = os.path.join(startmenu, "卸载.bat")
        desktop_lnk = os.path.join(desktop_dir, f"{APP_NAME}.lnk")
        with open(bat, "w", encoding="gbk") as f:
            f.write("@echo off\r\n")
            f.write("taskkill /f /im GoldMonitor.exe >nul 2>&1\r\n")
            f.write("timeout /t 1 /nobreak >nul\r\n")
            f.write(f'if exist "{desktop_lnk}" del /q "{desktop_lnk}" >nul 2>&1\r\n')
            f.write(f'rmdir /s /q "{startmenu}" >nul 2>&1\r\n')
            f.write(f'rmdir /s /q "{target_dir}" >nul 2>&1\r\n')
            f.write("echo 金价监控已卸载\r\n")
            f.write("pause\r\n")


if __name__ == "__main__":
    app = Installer()
    app.mainloop()
