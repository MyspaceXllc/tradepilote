import ctypes
import ipaddress
import json
import logging
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

import pystray
import qrcode
import requests
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from tkinter import messagebox, ttk


APP_NAME = "TradePilot"
PORT = 8765
MUTEX_NAME = "Global\\TradePilotConnector"
CONNECTOR_WIDTH = 520
ANALYSIS_WIDTH = 940


def app_data_dir():
    root = Path(os.getenv("LOCALAPPDATA", Path.home()))
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


DATA_DIR = app_data_dir()
LOG_PATH = DATA_DIR / "tradepilot.log"
DB_PATH = DATA_DIR / "tradepilot.db"
STATE_PATH = DATA_DIR / "connector_state.json"
SECRET_PATH = DATA_DIR / "server_secret.txt"

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(APP_NAME)


def runtime_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()

def tailscale_ip():
    candidates = [
        shutil.which("tailscale"),
        Path(os.getenv("ProgramFiles", "C:\\Program Files"))
        / "Tailscale"
        / "tailscale.exe",
        Path(os.getenv("LOCALAPPDATA", ""))
        / "Tailscale"
        / "tailscale.exe",
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            result = subprocess.run(
                [str(candidate), "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                continue
            for line in result.stdout.splitlines():
                value = line.strip()
                address = ipaddress.ip_address(value)
                if address.version == 4 and value.startswith("100."):
                    return value
        except (OSError, ValueError, subprocess.SubprocessError):
            logger.exception("Tailscale detection failed")
    return None


def edge_path():
    candidates = [
        shutil.which("msedge"),
        Path(os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.getenv("ProgramFiles", "C:\\Program Files"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def find_window_by_title(title_fragment):
    matches = []
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_fragment.lower() in buffer.value.lower():
            matches.append(hwnd)
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return matches[-1] if matches else None


def access_address():
    remote_ip = tailscale_ip()
    if remote_ip:
        return remote_ip, "tailscale"
    return local_ip(), "local"


def get_secret():
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text().strip()
    value = secrets.token_urlsafe(64)
    SECRET_PATH.write_text(value)
    return value


def configure_environment():
    ip, network_mode = access_address()
    web_dist = runtime_root() / "web_dist"
    os.environ.update(
        {
            "SECRET_KEY": get_secret(),
            "DATABASE_PATH": str(DB_PATH),
            "ALLOWED_ORIGINS": (
                f"http://127.0.0.1:{PORT},http://localhost:{PORT},"
                f"http://{ip}:{PORT}"
            ),
            "ACCESS_TOKEN_MINUTES": "43200",
            "DEMO_ONLY": "true",
            "WEB_DIST_DIR": str(web_dist),
            "SERVER_URL": f"http://127.0.0.1:{PORT}",
            "WS_URL": f"ws://127.0.0.1:{PORT}/ws/connector",
            "STATE_PATH": str(STATE_PATH),
            "DEVICE_NAME": os.getenv("COMPUTERNAME", "TradePilot Windows"),
            "ALLOW_LIVE_TRADING": "false",
            "PAIRING_TOKEN": "",
        }
    )
    return ip, network_mode


def create_icon(size=256):
    logo_path = runtime_root() / "web_dist" / "tradepilot-logo.png"
    if logo_path.exists():
        try:
            image = Image.open(logo_path).convert("RGBA")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (size, size), "#0a0b0e")
            x = (size - image.width) // 2
            y = (size - image.height) // 2
            canvas.alpha_composite(image, (x, y))
            return canvas.convert("RGB")
        except Exception:
            pass

    image = Image.new("RGB", (size, size), "#0a0b0e")
    draw = ImageDraw.Draw(image)
    margin = int(size * 0.14)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=int(size * 0.18),
        fill="#d6ad55",
    )
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.28))
    except OSError:
        font = ImageFont.load_default()
    draw.text(
        (size // 2, size // 2),
        "TP",
        fill="#151109",
        anchor="mm",
        font=font,
        stroke_width=1,
    )
    return image


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(
            None,
            "TradePilot Connector is already running.",
            "TradePilot",
            0x40,
        )
        sys.exit(0)
    return handle


class TradePilotApp:
    def __init__(self):
        self.ip, self.network_mode = configure_environment()
        self.base_url = f"http://{self.ip}:{PORT}"
        self.local_url = f"http://127.0.0.1:{PORT}"
        self.root = tk.Tk()
        self.root.title("TradePilot Connector")
        self.root.geometry(f"{CONNECTOR_WIDTH}x740")
        self.root.minsize(CONNECTOR_WIDTH, 700)
        self.root.configure(bg="#0a0b0e")
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.qr_photo = None
        self.qr_refresh_job = None
        self.analysis_processes = {}
        self.analysis_open = False
        self.analysis_menu = None
        self.analysis_window_title = "TradePilot Market Lab"
        self.tray = None
        self._build_styles()
        self._build_ui()
        self._start_services()
        self._start_tray()
        self.root.after(1200, self.refresh_status)
        self.root.after(1800, self.generate_pairing_qr)

    def _build_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TP.TButton",
            background="#d6ad55",
            foreground="#151109",
            borderwidth=0,
            padding=(14, 12),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("TP.TButton", background=[("active", "#e2bf69")])
        style.configure(
            "Secondary.TButton",
            background="#20232b",
            foreground="#ffffff",
            borderwidth=0,
            padding=(14, 11),
            font=("Segoe UI", 9, "bold"),
        )

    def _build_ui(self):
        frame = tk.Frame(
            self.root,
            width=CONNECTOR_WIDTH,
            bg="#0a0b0e",
            padx=28,
            pady=24,
        )
        frame.pack(side="left", fill="y")
        frame.pack_propagate(False)
        self.connector_frame = frame

        header = tk.Frame(frame, bg="#0a0b0e")
        header.pack(fill="x")
        logo_path = runtime_root() / "web_dist" / "tradepilot-logo.png"
        if logo_path.exists():
            try:
                logo_image = Image.open(logo_path).convert("RGBA")
                logo_image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_image)
                logo = tk.Label(
                    header,
                    image=self.logo_photo,
                    bg="#0a0b0e",
                    bd=0,
                    highlightthickness=0,
                )
            except Exception:
                logo = tk.Label(
                    header,
                    text="TP",
                    bg="#d6ad55",
                    fg="#151109",
                    font=("Segoe UI", 16, "bold"),
                    width=3,
                    height=1,
                    padx=6,
                    pady=8,
                )
        else:
            logo = tk.Label(
                header,
                text="TP",
                bg="#d6ad55",
                fg="#151109",
                font=("Segoe UI", 16, "bold"),
                width=3,
                height=1,
                padx=6,
                pady=8,
            )
        logo.pack(side="left")
        title_box = tk.Frame(header, bg="#0a0b0e")
        title_box.pack(side="left", padx=12)
        tk.Label(
            title_box,
            text="TRADEPILOT",
            bg="#0a0b0e",
            fg="#ffffff",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="MT5 CONNECTOR â€¢ DEMO LOCKED",
            bg="#0a0b0e",
            fg="#8b8f99",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        self.status_label = tk.Label(
            frame,
            text="Starting servicesâ€¦",
            bg="#111318",
            fg="#f3ca70",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=14,
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(22, 10))

        self.account_label = tk.Label(
            frame,
            text="MT5: waiting for terminal",
            bg="#111318",
            fg="#c8c9ce",
            font=("Segoe UI", 10),
            padx=16,
            pady=12,
            anchor="w",
            justify="left",
        )
        self.account_label.pack(fill="x")

        qr_card = tk.Frame(
            frame,
            bg="#111318",
            highlightbackground="#2a2d34",
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        qr_card.pack(fill="both", expand=True, pady=12)
        tk.Label(
            qr_card,
            text="CONNECT YOUR PHONE",
            bg="#111318",
            fg="#ffffff",
            font=("Segoe UI", 11, "bold"),
        ).pack()
        tk.Label(
            qr_card,
            text="Scan once. No username or password required.",
            bg="#111318",
            fg="#8b8f99",
            font=("Segoe UI", 9),
        ).pack(pady=(3, 10))
        self.qr_label = tk.Label(qr_card, bg="#111318")
        self.qr_label.pack(expand=True)
        self.qr_info = tk.Label(
            qr_card,
            text="Preparing one-time QRâ€¦",
            bg="#111318",
            fg="#8b8f99",
            font=("Segoe UI", 8),
        )
        self.qr_info.pack(pady=(8, 0))

        buttons = tk.Frame(frame, bg="#0a0b0e")
        buttons.pack(fill="x")
        ttk.Button(
            buttons,
            text="NEW QR",
            style="Secondary.TButton",
            command=self.generate_pairing_qr,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(
            buttons,
            text="OPEN WEB APP",
            style="TP.TButton",
            command=self.open_web_app,
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.network_info = tk.Label(
            frame,
            text=self._network_text(),
            bg="#0a0b0e",
            fg="#666a73",
            font=("Segoe UI", 8),
            justify="left",
        )
        self.network_info.pack(fill="x", pady=(12, 0))

        self.analysis_button = tk.Button(
            self.root,
            text="â€º",
            command=self.toggle_analysis_panel,
            bg="#d6ad55",
            fg="#151109",
            activebackground="#e4c46f",
            activeforeground="#151109",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 18, "bold"),
        )
        self.analysis_button.place(
            x=CONNECTOR_WIDTH,
            rely=0.5,
            anchor="e",
            width=30,
            height=82,
        )

    def _network_text(self):
        access = (
            "Remote access: Tailscale connected"
            if self.network_mode == "tailscale"
            else "Access: Local Wi-Fi only"
        )
        return f"{access}\nWeb app: {self.base_url}\nData: {DATA_DIR}"

    def _refresh_access_address(self):
        ip, network_mode = access_address()
        self.ip = ip
        self.network_mode = network_mode
        self.base_url = f"http://{self.ip}:{PORT}"
        self.network_info.configure(text=self._network_text())

    def _start_services(self):
        threading.Thread(target=self._run_server, daemon=True).start()
        threading.Thread(target=self._run_connector_forever, daemon=True).start()

    def _run_server(self):
        try:
            import uvicorn
            from server.app.main import app

            uvicorn.run(
                app,
                host="0.0.0.0",
                port=PORT,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
        except Exception:
            logger.exception("Server failed")

    def _run_connector_forever(self):
        while True:
            try:
                if requests.get(self.local_url + "/health", timeout=0.8).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.5)
        while True:
            try:
                from connector import connector as mt5_connector

                mt5_connector.main()
            except Exception:
                logger.exception("Connector failed; retrying")
                time.sleep(5)

    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open TradePilot", self.show_window, default=True),
            pystray.MenuItem("Open Web App", self.open_web_app),
            pystray.MenuItem("Toggle Market Lab", self.toggle_analysis_panel),
            pystray.MenuItem("New Pairing QR", self.generate_pairing_qr),
            pystray.MenuItem("Exit", self.exit_app),
        )
        self.tray = pystray.Icon(
            "TradePilot",
            create_icon(64),
            "TradePilot Connector",
            menu,
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

    def generate_pairing_qr(self, *_):
        if self.qr_refresh_job is not None:
            try:
                self.root.after_cancel(self.qr_refresh_job)
            except tk.TclError:
                pass
            self.qr_refresh_job = None
        threading.Thread(target=self._generate_qr_worker, daemon=True).start()

    def _new_setup_url(self):
        ip, network_mode = access_address()
        self.ip = ip
        self.network_mode = network_mode
        self.base_url = f"http://{self.ip}:{PORT}"
        self.root.after(
            0,
            lambda: self.network_info.configure(text=self._network_text()),
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if not STATE_PATH.exists():
                    time.sleep(0.5)
                    continue
                state = json.loads(STATE_PATH.read_text())
                response = requests.post(
                    self.local_url + "/setup/create",
                    json={
                        "device_id": state["device_id"],
                        "connector_token": state["connector_token"],
                    },
                    timeout=3,
                )
                if response.status_code == 404:
                    time.sleep(0.7)
                    continue
                response.raise_for_status()
                payload = response.json()
                token = payload["setup_token"]
                expires_in = int(payload.get("expires_in", 300))
                return (
                    f"{self.base_url}/?setup={quote(token)}",
                    expires_in,
                )
            except Exception:
                logger.exception("Could not create pairing QR")
                time.sleep(1)
        return None

    def _generate_qr_worker(self):
        setup = self._new_setup_url()
        if setup:
            url, expires_in = setup
            image = qrcode.make(url).convert("RGB").resize(
                (230, 230),
                Image.Resampling.NEAREST,
            )
            self.root.after(
                0,
                lambda: self._show_qr(image, url, expires_in),
            )
            return
        self.root.after(0, self._show_qr_error)

    def open_web_app(self, *_):
        threading.Thread(target=self._open_web_worker, daemon=True).start()

    def _open_web_worker(self):
        setup = self._new_setup_url()
        if setup:
            url, _ = setup
            webbrowser.open(url)
            return
        self.root.after(
            0,
            lambda: messagebox.showerror(
                "TradePilot",
                "Could not create a secure browser session. Try again.",
            ),
        )

    def _schedule_qr_refresh(self, delay_seconds):
        if self.qr_refresh_job is not None:
            try:
                self.root.after_cancel(self.qr_refresh_job)
            except tk.TclError:
                pass
        self.qr_refresh_job = self.root.after(
            max(1, int(delay_seconds * 1000)),
            self.generate_pairing_qr,
        )

    def _show_qr(self, image, url, expires_in):
        self.qr_photo = ImageTk.PhotoImage(image)
        self.qr_label.configure(image=self.qr_photo)
        self.qr_info.configure(
            text=(
                "Scan with your phone camera â€¢ auto-renews before expiry\n"
                f"{url.split('?')[0]}"
            ),
            fg="#8b8f99",
        )
        self._schedule_qr_refresh(max(30, expires_in - 15))

    def _show_qr_error(self):
        self.qr_info.config(
            text="Could not create QR. Retrying automaticallyâ€¦",
            fg="#ff858e",
        )
        self._schedule_qr_refresh(15)

    def toggle_analysis_panel(self, *_):
        self.root.after(0, self._toggle_analysis_menu)

    def _destroy_analysis_menu(self):
        menu = self.analysis_menu
        self.analysis_menu = None
        if menu:
            try:
                menu.destroy()
            except tk.TclError:
                pass

    def _toggle_analysis_menu(self):
        if self.analysis_menu:
            self._destroy_analysis_menu()
            return

        self.root.update_idletasks()
        menu = tk.Toplevel(self.root)
        self.analysis_menu = menu
        menu.overrideredirect(True)
        menu.configure(bg="#090c12")
        menu.attributes("-topmost", True)

        width = 250
        height = 302 if self.analysis_open else 256
        x = self.root.winfo_x() + CONNECTOR_WIDTH + 6
        y = self.root.winfo_y() + max(90, (self.root.winfo_height() - height) // 2)
        if x + width > self.root.winfo_screenwidth():
            x = max(0, self.root.winfo_x() + CONNECTOR_WIDTH - width - 36)
        menu.geometry(f"{width}x{height}+{x}+{y}")

        shell = tk.Frame(
            menu,
            bg="#0d1118",
            highlightbackground="#303744",
            highlightthickness=1,
        )
        shell.pack(fill="both", expand=True)
        tk.Label(
            shell,
            text="ANALYSIS MENU",
            bg="#0d1118",
            fg="#8d96a4",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 8))

        tk.Button(
            shell,
            text="STRATEGIES   â€º",
            command=lambda: self._open_analysis_page("analysis.html", False),
            bg="#171c25",
            fg="#f2f4f7",
            activebackground="#222936",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=14,
        ).pack(fill="x", padx=10, pady=(0, 6), ipady=9)

        tk.Button(
            shell,
            text="FLOW PULSE   â€º",
            command=lambda: self._open_analysis_page("premium.html", True),
            bg="#d6ad55",
            fg="#151109",
            activebackground="#e6c56e",
            activeforeground="#151109",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=14,
        ).pack(fill="x", padx=10, pady=(0, 6), ipady=9)

        tk.Button(
            shell,
            text="SIGNAL FUSION   â€º",
            command=lambda: self._open_analysis_page("fusion.html", True),
            bg="#142a28",
            fg="#57ddb2",
            activebackground="#1b3a36",
            activeforeground="#8af0ce",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=14,
        ).pack(fill="x", padx=10, pady=(0, 8), ipady=9)

        tk.Button(
            shell,
            text="STRATEGY CHARTS   â€º",
            command=lambda: self._open_analysis_page("strategy-charts.html", True),
            bg="#171c25",
            fg="#f2f4f7",
            activebackground="#222936",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=14,
        ).pack(fill="x", padx=10, pady=(0, 8), ipady=9)

        if self.analysis_open:
            tk.Button(
                shell,
                text="CLOSE ANALYSIS",
                command=self._close_analysis_panel,
                bg="#0d1118",
                fg="#ff8d99",
                activebackground="#231419",
                activeforeground="#ffb2ba",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
            ).pack(fill="x", padx=10, pady=(0, 7), ipady=4)

        menu.bind("<Escape>", lambda _event: self._destroy_analysis_menu())
        menu.focus_force()

    def _open_analysis_page(self, filename, fullscreen=False):
        self._destroy_analysis_menu()

        browser = edge_path()
        url = self.local_url + "/" + filename
        if not browser:
            webbrowser.open(url)
            return

        # Keep every analysis page open independently. If the same page is
        # already open, bring its window forward instead of opening a duplicate.
        existing = self.analysis_processes.get(filename)
        if existing and existing.poll() is None:
            self.root.after(0, lambda: self._focus_analysis_window(filename))
            return

        self.root.update_idletasks()
        x = max(0, self.root.winfo_x())
        y = max(0, self.root.winfo_y())
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        profile = DATA_DIR / ("analysis-edge-" + Path(filename).stem.replace("-", "_"))
        profile.mkdir(parents=True, exist_ok=True)

        titles = {
            "fusion.html": "TradePilot Signal Fusion",
            "premium.html": "TradePilot Flow Pulse",
            "analysis.html": "TradePilot Market Lab",
            "strategy-charts.html": "TradePilot Strategy Charts",
        }
        self.analysis_window_title = titles.get(filename, "TradePilot Analysis")

        if fullscreen:
            window_args = [
                "--start-maximized",
                f"--window-size={screen_width},{screen_height}",
                "--window-position=0,0",
            ]
        else:
            height = max(700, self.root.winfo_height())
            analysis_x = x + CONNECTOR_WIDTH + 8
            if analysis_x + ANALYSIS_WIDTH > screen_width:
                analysis_x = max(0, x - ANALYSIS_WIDTH - 8)
            window_args = [
                f"--window-size={ANALYSIS_WIDTH},{height}",
                f"--window-position={analysis_x},{y}",
            ]

        try:
            process = subprocess.Popen(
                [
                    browser,
                    f"--app={url}",
                    f"--user-data-dir={profile}",
                    *window_args,
                    "--no-first-run",
                    "--force-device-scale-factor=1",
                    "--disable-features=msEdgeSidebarV2",
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.analysis_processes[filename] = process
            self.analysis_open = True
            self.analysis_button.configure(text="â€¹")
            self.root.after(250, lambda f=filename: self._apply_analysis_icon(0, f))
        except OSError:
            logger.exception("Could not open analysis page")
            webbrowser.open(url)

    def _focus_analysis_window(self, filename):
        titles = {
            "fusion.html": "TradePilot Signal Fusion",
            "premium.html": "TradePilot Flow Pulse",
            "analysis.html": "TradePilot Market Lab",
            "strategy-charts.html": "TradePilot Strategy Charts",
        }
        hwnd = find_window_by_title(titles.get(filename, "TradePilot Analysis"))
        if hwnd:
            try:
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                logger.exception("Could not focus analysis window")

    def _apply_analysis_icon(self, attempt, filename):
        process = self.analysis_processes.get(filename)
        if not process or process.poll() is not None:
            return
        titles = {
            "fusion.html": "TradePilot Signal Fusion",
            "premium.html": "TradePilot Flow Pulse",
            "analysis.html": "TradePilot Market Lab",
            "strategy-charts.html": "TradePilot Strategy Charts",
        }
        hwnd = find_window_by_title(titles.get(filename, "TradePilot Analysis"))
        icon_path = runtime_root() / "web_dist" / "favicon.ico"
        if hwnd and icon_path.exists():
            user32 = ctypes.windll.user32
            image_icon = 1
            load_from_file = 0x0010
            wm_seticon = 0x0080
            icon_small = 0
            icon_big = 1
            big_icon = user32.LoadImageW(
                None,
                str(icon_path),
                image_icon,
                32,
                32,
                load_from_file,
            )
            small_icon = user32.LoadImageW(
                None,
                str(icon_path),
                image_icon,
                16,
                16,
                load_from_file,
            )
            if big_icon:
                user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon)
            if small_icon:
                user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
            return
        if attempt < 40:
            self.root.after(
                250,
                lambda: self._apply_analysis_icon(attempt + 1, filename),
            )

    def _close_analysis_panel(self):
        self._destroy_analysis_menu()
        processes = list(self.analysis_processes.items())
        self.analysis_processes = {}
        self.analysis_open = False
        self.analysis_button.configure(text="â€º")
        for _filename, process in processes:
            if process and process.poll() is None:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except (OSError, subprocess.SubprocessError):
                    logger.exception("Could not close analysis window")

    def refresh_status(self):
        server_ok = False
        try:
            server_ok = requests.get(
                self.local_url + "/health", timeout=0.8
            ).ok
        except requests.RequestException:
            pass

        status = "offline"
        mode = "â€”"
        account = None
        broker = None
        if STATE_PATH.exists() and DB_PATH.exists():
            try:
                state = json.loads(STATE_PATH.read_text())
                with sqlite3.connect(DB_PATH) as connection:
                    row = connection.execute(
                        "SELECT status,mode,mt5_account,broker FROM devices WHERE id=?",
                        (state["device_id"],),
                    ).fetchone()
                if row:
                    status, mode, account, broker = row
            except Exception:
                logger.exception("Status refresh failed")

        if server_ok and status == "online":
            self.status_label.config(
                text="â—  CONNECTED â€” READY",
                fg="#7ce1aa",
            )
        elif server_ok:
            self.status_label.config(
                text="â—  SERVER READY â€” WAITING FOR MT5",
                fg="#f3ca70",
            )
        else:
            self.status_label.config(
                text="â—  STARTING LOCAL SERVER",
                fg="#ff858e",
            )

        if account:
            masked = str(account)[-4:]
            self.account_label.config(
                text=(
                    f"MT5 account: â€¢â€¢â€¢â€¢{masked}\n"
                    f"Broker: {broker or 'â€”'}  â€¢  Mode: {mode}"
                )
            )
        else:
            self.account_label.config(text="MT5: open the terminal and log into Demo")

        # Drop analysis entries whose windows were closed manually.
        for filename, process in list(self.analysis_processes.items()):
            if process.poll() is not None:
                self.analysis_processes.pop(filename, None)
        self.analysis_open = bool(self.analysis_processes)
        if not self.analysis_open:
            self.analysis_button.configure(text="â€º")

        self.root.after(2000, self.refresh_status)

    def hide_window(self):
        self.root.withdraw()

    def show_window(self, *_):
        self.root.after(0, self._show_window_on_ui_thread)

    def _show_window_on_ui_thread(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self, *_):
        if self.analysis_open:
            self._close_analysis_panel()
        if self.tray:
            self.tray.stop()
        self.root.after(100, lambda: os._exit(0))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    acquire_single_instance()
    try:
        TradePilotApp().run()
    except Exception as exc:
        logger.exception("Fatal launcher error")
        messagebox.showerror(
            "TradePilot",
            f"TradePilot could not start.\n\n{exc}\n\nLog: {LOG_PATH}",
        )

