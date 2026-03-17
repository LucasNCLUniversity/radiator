#!/usr/bin/env python3
"""
radiator.exe
------------
Heats your computer up. Green on black. No questions asked.

Requirements:
    py -m pip install psutil GPUtil numpy

Usage:
    python radiator.py
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import multiprocessing
import time
import math
import sys

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ── Constants ─────────────────────────────────────────────────────────────────

TARGET_TEMP     = 90
UPDATE_INTERVAL = 1500   # ms — UI refresh
SENSOR_INTERVAL = 2.0    # seconds — background sensor poll

BOOT_LINES = [
    "RADIATOR v1.0.0",
    "=" * 36,
    "",
    "Initialising thermal subsystems...",
    "Detecting CPU cores...",
    "Detecting GPU...",
    "Loading stress routines...",
    "Calibrating temperature sensors...",
    "",
    "All systems nominal.",
    "=" * 36,
    "",
]

GREEN        = "#00FF41"
GREEN_DIM    = "#007A1F"
GREEN_DARK   = "#003D0F"
BLACK        = "#0A0A0A"
GREEN_BRIGHT = "#AFFFBC"
RED_WARN     = "#FF4444"
AMBER        = "#FFB700"


# ── Shared sensor state ───────────────────────────────────────────────────────
# Written by background thread, read by UI thread via lock.

_sensor_lock = threading.Lock()
_sensor_data = {
    "cpu_temp": None,
    "gpu_temp": None,
    "cpu_load": 0.0,
    "gpu_load": None,
}


def _sensor_loop():
    """Background thread: polls sensors every SENSOR_INTERVAL seconds."""
    # Prime cpu_percent — first call always returns 0.0
    if HAS_PSUTIL:
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    while True:
        cpu_temp = None
        gpu_temp = None
        cpu_load = 0.0
        gpu_load = None

        if HAS_PSUTIL:
            try:
                # interval=1.0 blocks for 1 second but that's fine on this thread
                cpu_load = psutil.cpu_percent(interval=1.0)
            except Exception:
                pass

            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ["coretemp", "cpu_thermal", "k10temp", "acpitz", "cpu-thermal"]:
                        if key in temps:
                            vals = [e.current for e in temps[key] if e.current and e.current > 0]
                            if vals:
                                cpu_temp = round(max(vals), 1)
                                break
                    if cpu_temp is None:
                        for entries in temps.values():
                            vals = [e.current for e in entries if e.current and e.current > 0]
                            if vals:
                                cpu_temp = round(max(vals), 1)
                                break
            except Exception:
                pass

        if HAS_GPUTIL:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_temp = round(gpus[0].temperature, 1)
                    gpu_load = round(gpus[0].load * 100, 1)
            except Exception:
                pass

        with _sensor_lock:
            _sensor_data["cpu_temp"] = cpu_temp
            _sensor_data["gpu_temp"] = gpu_temp
            _sensor_data["cpu_load"] = cpu_load
            _sensor_data["gpu_load"] = gpu_load

        time.sleep(SENSOR_INTERVAL)


def get_sensor_data():
    with _sensor_lock:
        return dict(_sensor_data)


# ── Stress Workers ────────────────────────────────────────────────────────────
# Uses multiprocessing.Process so each worker gets its own GIL,
# allowing true multi-core CPU saturation.

_stress_processes = []


def _cpu_stress_process():
    """Runs in a separate process — no GIL, pins one full core."""
    import math
    x = 1.0
    while True:
        for _ in range(100000):
            x = math.sqrt(abs(x * 1.0000001 + 0.1)) * math.sin(x) + math.cos(x * 0.999)


def _gpu_stress_process():
    """Runs in a separate process — heavy numpy matrix ops."""
    try:
        import numpy as np
        size = 512
        while True:
            a = np.random.rand(size, size).astype(np.float32)
            b = np.random.rand(size, size).astype(np.float32)
            np.dot(a, b)
            np.linalg.svd(a, full_matrices=False)
    except ImportError:
        # Fall back to CPU math if numpy not available
        import math
        x = 1.0
        while True:
            for _ in range(100000):
                x = math.sqrt(abs(x * 1.0000001 + 0.1)) * math.sin(x) + math.cos(x * 0.999)


def start_stress():
    global _stress_processes
    n = psutil.cpu_count(logical=True) if HAS_PSUTIL else 4
    for _ in range(n):
        p = multiprocessing.Process(target=_cpu_stress_process, daemon=True)
        p.start()
        _stress_processes.append(p)
    for _ in range(2):
        p = multiprocessing.Process(target=_gpu_stress_process, daemon=True)
        p.start()
        _stress_processes.append(p)


def stop_stress():
    global _stress_processes
    for p in _stress_processes:
        try:
            p.terminate()
            p.join(timeout=2)
        except Exception:
            pass
    _stress_processes = []


# ── Main Application ──────────────────────────────────────────────────────────

class RadiatorApp:

    def __init__(self, root):
        self.root = root
        self.root.title("radiator.exe")
        self.root.configure(bg=BLACK)
        self.root.resizable(False, False)

        self.running = False
        self._update_job = None
        self._blink_on = True

        self._build_ui()
        self._start_boot_sequence()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        available = tkfont.families()
        mono_candidates = ["Courier New", "Consolas", "Lucida Console", "Courier"]
        mono = next((f for f in mono_candidates if f in available), "TkFixedFont")

        self.font_large  = tkfont.Font(family=mono, size=16, weight="bold")
        self.font_medium = tkfont.Font(family=mono, size=11, weight="bold")
        self.font_small  = tkfont.Font(family=mono, size=9)
        self.font_tiny   = tkfont.Font(family=mono, size=8)

        outer = tk.Frame(self.root, bg=GREEN_DARK, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(outer, bg=BLACK, padx=16, pady=12)
        inner.pack(fill=tk.BOTH, expand=True)

        # Title row
        title_row = tk.Frame(inner, bg=BLACK)
        title_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(title_row, text="RADIATOR.EXE",
                 font=self.font_large, fg=GREEN, bg=BLACK).pack(side=tk.LEFT)

        self.blink_label = tk.Label(title_row, text="█",
                                    font=self.font_large, fg=GREEN, bg=BLACK)
        self.blink_label.pack(side=tk.RIGHT)

        tk.Label(inner, text="=" * 36, font=self.font_small,
                 fg=GREEN_DIM, bg=BLACK).pack(fill=tk.X, pady=(0, 6))

        # Boot console
        self.console_frame = tk.Frame(inner, bg=BLACK)
        self.console_frame.pack(fill=tk.X)

        self.console_text = tk.Text(
            self.console_frame,
            width=38, height=13,
            font=self.font_small,
            fg=GREEN_DIM, bg=BLACK,
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor="none",
        )
        self.console_text.pack(fill=tk.X)

        # Dashboard (hidden until boot complete)
        self.dash = tk.Frame(inner, bg=BLACK)

        self.cpu_temp_var = tk.StringVar(value="---")
        self.gpu_temp_var = tk.StringVar(value="---")
        self.cpu_load_var = tk.StringVar(value="0%")
        self.gpu_load_var = tk.StringVar(value="---")

        self._make_temp_row("CPU TEMP", self.cpu_temp_var, "cpu_temp_lbl")
        self._make_load_row("CPU LOAD", self.cpu_load_var, "cpu_load_bar")

        tk.Label(self.dash, text="", bg=BLACK).pack()

        self._make_temp_row("GPU TEMP", self.gpu_temp_var, "gpu_temp_lbl")
        self._make_load_row("GPU LOAD", self.gpu_load_var, "gpu_load_bar")

        tk.Label(self.dash, text="", bg=BLACK).pack()

        # Progress bar toward target
        tk.Label(self.dash, text=f"TARGET: {TARGET_TEMP}C",
                 font=self.font_small, fg=GREEN_DIM, bg=BLACK, anchor="w").pack(fill=tk.X)

        self.prog_canvas = tk.Canvas(
            self.dash, width=360, height=20,
            bg=BLACK, highlightthickness=1,
            highlightbackground=GREEN_DARK
        )
        self.prog_canvas.pack(fill=tk.X, pady=(2, 2))

        self.prog_label = tk.Label(
            self.dash, text="HEATING... 0%",
            font=self.font_small, fg=GREEN, bg=BLACK, anchor="w"
        )
        self.prog_label.pack(fill=tk.X, pady=(0, 8))

        tk.Label(self.dash, text="=" * 36, font=self.font_small,
                 fg=GREEN_DIM, bg=BLACK).pack(fill=tk.X, pady=(0, 8))

        # Stop button
        self.stop_btn = tk.Button(
            self.dash,
            text="[ STOP HEATING ]",
            font=self.font_medium,
            fg=BLACK, bg=GREEN,
            activeforeground=BLACK, activebackground=GREEN_BRIGHT,
            relief=tk.FLAT, cursor="hand2",
            padx=12, pady=6,
            command=self._on_stop
        )
        self.stop_btn.pack(fill=tk.X)

        self.status_lbl = tk.Label(
            self.dash, text="",
            font=self.font_tiny, fg=GREEN_DIM, bg=BLACK
        )
        self.status_lbl.pack(fill=tk.X, pady=(4, 0))

        self.root.geometry("420x500")

    def _make_temp_row(self, label, var, lbl_attr):
        row = tk.Frame(self.dash, bg=BLACK)
        row.pack(fill=tk.X, pady=1)
        tk.Label(row, text=f"{label}:", font=self.font_small,
                 fg=GREEN_DIM, bg=BLACK, width=12, anchor="w").pack(side=tk.LEFT)
        lbl = tk.Label(row, textvariable=var,
                       font=self.font_medium, fg=GREEN, bg=BLACK, width=8, anchor="e")
        lbl.pack(side=tk.LEFT)
        tk.Label(row, text="C", font=self.font_small,
                 fg=GREEN_DIM, bg=BLACK).pack(side=tk.LEFT, padx=(2, 0))
        setattr(self, lbl_attr, lbl)

    def _make_load_row(self, label, var, bar_attr):
        row = tk.Frame(self.dash, bg=BLACK)
        row.pack(fill=tk.X, pady=1)
        tk.Label(row, text=f"{label}:", font=self.font_small,
                 fg=GREEN_DIM, bg=BLACK, width=12, anchor="w").pack(side=tk.LEFT)
        bar = tk.Canvas(row, width=200, height=12,
                        bg=BLACK, highlightthickness=0)
        bar.pack(side=tk.LEFT, padx=(4, 6))
        tk.Label(row, textvariable=var, font=self.font_small,
                 fg=GREEN, bg=BLACK, width=5, anchor="w").pack(side=tk.LEFT)
        setattr(self, bar_attr, bar)

    # ── Boot Sequence ─────────────────────────────────────────────────────────

    def _start_boot_sequence(self):
        lines = list(BOOT_LINES)
        cpu_count = psutil.cpu_count(logical=True) if HAS_PSUTIL else 4
        for i, line in enumerate(lines):
            if "Detecting CPU" in line:
                lines[i] = f"Detecting CPU cores... [{cpu_count} found]"
            elif "Detecting GPU" in line:
                lines[i] = "Detecting GPU...      [checking...]"
        self._boot_lines = lines
        self._boot_idx = 0
        self._type_next_line()

    def _type_next_line(self):
        if self._boot_idx >= len(self._boot_lines):
            self.root.after(500, self._finish_boot)
            return
        line = self._boot_lines[self._boot_idx]
        self._boot_idx += 1
        self._console_append(line + "\n")
        delay = 20 if ("=" in line or not line.strip()) else 130
        self.root.after(delay, self._type_next_line)

    def _console_append(self, text):
        self.console_text.configure(state=tk.NORMAL)
        self.console_text.insert(tk.END, text)
        self.console_text.see(tk.END)
        self.console_text.configure(state=tk.DISABLED)

    def _finish_boot(self):
        self.console_frame.pack_forget()
        self.dash.pack(fill=tk.BOTH, expand=True)
        self.running = True
        start_stress()
        self._update_ui()
        self._blink()

    # ── UI Update (runs on main thread via after()) ───────────────────────────

    def _update_ui(self):
        if not self.running:
            return

        data = get_sensor_data()
        cpu_temp = data["cpu_temp"]
        gpu_temp = data["gpu_temp"]
        cpu_load = data["cpu_load"]
        gpu_load = data["gpu_load"]

        # CPU temp
        if cpu_temp is not None:
            self.cpu_temp_var.set(f"{cpu_temp:.1f}")
            self.cpu_temp_lbl.configure(fg=self._temp_color(cpu_temp))
        else:
            self.cpu_temp_var.set("N/A")
            self.cpu_temp_lbl.configure(fg=GREEN_DIM)

        # GPU temp
        if gpu_temp is not None:
            self.gpu_temp_var.set(f"{gpu_temp:.1f}")
            self.gpu_temp_lbl.configure(fg=self._temp_color(gpu_temp))
        else:
            self.gpu_temp_var.set("N/A")
            self.gpu_temp_lbl.configure(fg=GREEN_DIM)

        # Load bars
        self.cpu_load_var.set(f"{cpu_load:.0f}%")
        self._draw_bar(self.cpu_load_bar, cpu_load / 100.0)

        if gpu_load is not None:
            self.gpu_load_var.set(f"{gpu_load:.0f}%")
            self._draw_bar(self.gpu_load_bar, gpu_load / 100.0)
        else:
            self.gpu_load_var.set("N/A")
            self._draw_bar(self.gpu_load_bar, 0)

        # Progress toward target
        current = cpu_temp or gpu_temp
        if current is not None:
            baseline = 35.0
            frac = max(0.0, min(1.0, (current - baseline) / (TARGET_TEMP - baseline)))
            self._draw_progress(frac)
            pct = int(frac * 100)
            if current >= TARGET_TEMP:
                self.prog_label.configure(
                    text=f"TARGET REACHED  {current:.1f}C", fg=RED_WARN)
            else:
                self.prog_label.configure(
                    text=f"HEATING... {pct}%  ({current:.1f}C -> {TARGET_TEMP}C)",
                    fg=GREEN)
        else:
            self._draw_progress(0.5, GREEN_DIM)
            self.prog_label.configure(
                text="HEATING... (no sensor data)", fg=GREEN_DIM)

        n = psutil.cpu_count(logical=True) if HAS_PSUTIL else 4
        self.status_lbl.configure(
            text=f"stress procs: {n} cpu + 2 gpu  |  ACTIVE")

        self._update_job = self.root.after(UPDATE_INTERVAL, self._update_ui)

    def _draw_bar(self, canvas, frac, color=GREEN):
        canvas.delete("all")
        w = canvas.winfo_width() or 200
        h = canvas.winfo_height() or 12
        canvas.create_rectangle(0, 0, w, h, fill=GREEN_DARK, outline="")
        fw = int(w * frac)
        if fw > 0:
            canvas.create_rectangle(0, 0, fw, h, fill=color, outline="")
        for x in range(0, w, 8):
            canvas.create_line(x, 0, x, h, fill=BLACK)

    def _draw_progress(self, frac, color=None):
        canvas = self.prog_canvas
        canvas.delete("all")
        w = canvas.winfo_width() or 360
        h = canvas.winfo_height() or 20
        canvas.create_rectangle(0, 0, w, h, fill=GREEN_DARK, outline="")
        c = color or (RED_WARN if frac >= 1.0 else AMBER if frac >= 0.8 else GREEN)
        fw = int(w * frac)
        if fw > 0:
            canvas.create_rectangle(0, 0, fw, h, fill=c, outline="")
        for x in range(0, w, 10):
            canvas.create_line(x, 0, x, h, fill=BLACK)

    def _temp_color(self, t):
        if t >= TARGET_TEMP:
            return RED_WARN
        elif t >= TARGET_TEMP * 0.85:
            return AMBER
        return GREEN

    def _blink(self):
        self._blink_on = not self._blink_on
        self.blink_label.configure(fg=GREEN if self._blink_on else BLACK)
        self.root.after(530, self._blink)

    # ── Stop ──────────────────────────────────────────────────────────────────

    def _on_stop(self):
        self.running = False
        stop_stress()
        if self._update_job:
            self.root.after_cancel(self._update_job)
        self.stop_btn.configure(
            text="[ STOPPED ]", fg=GREEN_DIM, bg=BLACK, state=tk.DISABLED)
        self.prog_label.configure(text="HEATING STOPPED.", fg=GREEN_DIM)
        self.status_lbl.configure(text="stress procs: terminated")
        self.blink_label.configure(fg=BLACK)


# ── Entry Point ───────────────────────────────────────────────────────────────

def check_deps():
    missing = [p for p, h in [
        ("psutil", HAS_PSUTIL),
        ("GPUtil", HAS_GPUTIL),
        ("numpy", HAS_NUMPY)
    ] if not h]
    if missing:
        print(f"[radiator] Missing packages: {', '.join(missing)}")
        print(f"[radiator] Run: py -m pip install {' '.join(missing)}")
        print(f"[radiator] Continuing with reduced functionality.\n")


if __name__ == "__main__":
    multiprocessing.freeze_support()  # required for Windows
    check_deps()

    # Start background sensor thread before launching UI
    threading.Thread(target=_sensor_loop, daemon=True).start()

    root = tk.Tk()
    app = RadiatorApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (stop_stress(), root.destroy()))
    root.mainloop()
