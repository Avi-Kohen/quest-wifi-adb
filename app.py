import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox


APP_TITLE = "Quest WiFi ADB Connector"


@dataclass
class Device:
    serial: str
    state: str
    model: str = ""


class AdbClient:
    def __init__(self) -> None:
        self.adb_path = self.find_adb()

    def find_adb(self) -> str | None:
        """
        Looks for adb in:
        1. ADB_PATH environment variable
        2. ./platform-tools/adb(.exe) next to this app
        3. System PATH
        """
        exe = "adb.exe" if os.name == "nt" else "adb"

        env_path = os.environ.get("ADB_PATH")
        if env_path and os.path.exists(env_path):
            return env_path

        app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        local_adb = os.path.join(app_dir, "platform-tools", exe)
        if os.path.exists(local_adb):
            return local_adb

        path_adb = shutil.which("adb")
        if path_adb:
            return path_adb

        return None

    def run(self, args: list[str], timeout: int = 10) -> tuple[int, str, str]:
        if not self.adb_path:
            return 127, "", "ADB not found. Put platform-tools next to the app or add adb to PATH."

        cmd = [self.adb_path] + args

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            # Prevents black CMD windows from blinking on Windows.
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                startupinfo=startupinfo,
                creationflags=creationflags,
                encoding="utf-8",
                errors="replace",
            )
            return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
        except subprocess.TimeoutExpired:
            return 124, "", f"Command timed out after {timeout} seconds."
        except Exception as exc:
            return 1, "", str(exc)

    def devices(self) -> list[Device]:
        code, out, err = self.run(["devices"], timeout=5)
        if code != 0:
            raise RuntimeError(err or out or "adb devices failed")

        devices: list[Device] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue

            parts = line.split()
            if len(parts) >= 2:
                serial, state = parts[0], parts[1]
                devices.append(Device(serial=serial, state=state))

        # Get model names only for authorized devices.
        for d in devices:
            if d.state == "device":
                d.model = self.getprop(d.serial, "ro.product.model") or "Android / Quest device"

        return devices

    def getprop(self, serial: str, prop: str) -> str:
        code, out, _ = self.run(["-s", serial, "shell", "getprop", prop], timeout=5)
        if code == 0:
            return out.strip()
        return ""

    def enable_wifi(self, serial: str) -> tuple[int, str, str]:
        return self.run(["-s", serial, "shell", "svc", "wifi", "enable"], timeout=10)

    def connect_network(self, serial: str, ssid: str, security: str, password: str) -> tuple[int, str, str]:
        args = ["-s", serial, "shell", "cmd", "wifi", "connect-network", ssid, security]
        if security in ("wpa2", "wpa3"):
            args.append(password)
        return self.run(args, timeout=25)

    def wifi_status(self, serial: str) -> tuple[int, str, str]:
        # Supported on many Android builds. If unavailable, the app will simply show the error.
        return self.run(["-s", serial, "shell", "cmd", "wifi", "status"], timeout=10)


class QuestWifiApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("760x560")
        self.minsize(720, 520)

        self.adb = AdbClient()
        self.devices_cache: list[Device] = []
        self.polling = False

        self.ssid_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.security_var = tk.StringVar(value="wpa2")
        self.selected_device_var = tk.StringVar()
        self.show_password_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._set_status("red", "לא מחובר", "חבר משקפת עם כבל USB. אם זו הפעם הראשונה — צריך לאשר Debugging בתוך המשקפת.")
        self.after(300, self.refresh_devices)
        self.after(2200, self._auto_refresh_loop)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text="חיבור מהיר של Meta Quest ל‑WiFi דרך ADB", font=("Segoe UI", 17, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            root,
            text="הכנס שם רשת וסיסמה, חבר משקפת עם USB, אשר Always Allow פעם אחת, ושלח את ההגדרות.",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 14))

        status_frame = ttk.LabelFrame(root, text="מצב משקפת", padding=12)
        status_frame.pack(fill="x", pady=(0, 12))

        self.status_canvas = tk.Canvas(status_frame, width=28, height=28, highlightthickness=0)
        self.status_canvas.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self.status_circle = self.status_canvas.create_oval(4, 4, 24, 24, fill="#cc3333", outline="")

        self.status_title = ttk.Label(status_frame, text="", font=("Segoe UI", 12, "bold"))
        self.status_title.grid(row=0, column=1, sticky="w")

        self.status_details = ttk.Label(status_frame, text="", wraplength=620)
        self.status_details.grid(row=1, column=1, sticky="w", pady=(3, 0))

        form = ttk.LabelFrame(root, text="פרטי WiFi", padding=12)
        form.pack(fill="x", pady=(0, 12))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="שם הרשת / SSID").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        ssid_entry = ttk.Entry(form, textvariable=self.ssid_var)
        ssid_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(form, text="סיסמה").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        self.password_entry = ttk.Entry(form, textvariable=self.password_var, show="•")
        self.password_entry.grid(row=1, column=1, sticky="ew", pady=6)

        show_check = ttk.Checkbutton(
            form,
            text="הצג סיסמה",
            variable=self.show_password_var,
            command=self._toggle_password,
        )
        show_check.grid(row=1, column=2, padx=(10, 0), sticky="w")

        ttk.Label(form, text="סוג אבטחה").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        security_combo = ttk.Combobox(
            form,
            textvariable=self.security_var,
            values=["wpa2", "wpa3", "open"],
            width=12,
            state="readonly",
        )
        security_combo.grid(row=2, column=1, sticky="w", pady=6)

        device_frame = ttk.LabelFrame(root, text="בחירת משקפת", padding=12)
        device_frame.pack(fill="x", pady=(0, 12))
        device_frame.columnconfigure(0, weight=1)

        self.device_combo = ttk.Combobox(device_frame, textvariable=self.selected_device_var, state="readonly")
        self.device_combo.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        ttk.Button(device_frame, text="רענן", command=self.refresh_devices).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(device_frame, text="בדוק WiFi", command=self.check_wifi_status).grid(row=0, column=2)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(0, 12))

        self.send_button = ttk.Button(actions, text="שלח WiFi למשקפת", command=self.send_wifi)
        self.send_button.pack(side="left")

        ttk.Button(actions, text="נקה לוג", command=self._clear_log).pack(side="left", padx=(10, 0))

        log_frame = ttk.LabelFrame(root, text="לוג", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=12, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self._log("האפליקציה מוכנה.")
        if self.adb.adb_path:
            self._log(f"ADB נמצא: {self.adb.adb_path}")
        else:
            self._log("ADB לא נמצא. שים תיקיית platform-tools ליד app.py או הוסף adb ל-PATH.")

    def _toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.show_password_var.get() else "•")

    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def _set_status(self, color: str, title: str, details: str) -> None:
        colors = {
            "red": "#cc3333",
            "yellow": "#e0aa00",
            "green": "#2fa84f",
            "gray": "#777777",
        }
        self.status_canvas.itemconfig(self.status_circle, fill=colors.get(color, "#777777"))
        self.status_title.configure(text=title)
        self.status_details.configure(text=details)

    def _auto_refresh_loop(self) -> None:
        self.refresh_devices(silent=True)
        self.after(2200, self._auto_refresh_loop)

    def refresh_devices(self, silent: bool = False) -> None:
        if self.polling:
            return
        self.polling = True

        def worker() -> None:
            try:
                devices = self.adb.devices()
                self.after(0, lambda: self._update_devices_ui(devices, silent=silent))
            except Exception as exc:
                self.after(0, lambda: self._handle_refresh_error(str(exc), silent=silent))
            finally:
                self.polling = False

        threading.Thread(target=worker, daemon=True).start()

    def _update_devices_ui(self, devices: list[Device], silent: bool) -> None:
        self.devices_cache = devices

        combo_values = []
        for d in devices:
            label = f"{d.serial} | {d.state}"
            if d.model:
                label += f" | {d.model}"
            combo_values.append(label)

        self.device_combo["values"] = combo_values

        current = self.selected_device_var.get()
        if combo_values and current not in combo_values:
            # Prefer an authorized device, otherwise first device.
            first_ready = next((v for v, d in zip(combo_values, devices) if d.state == "device"), combo_values[0])
            self.selected_device_var.set(first_ready)
        elif not combo_values:
            self.selected_device_var.set("")

        if not self.adb.adb_path:
            self._set_status("red", "ADB לא נמצא", "הורד Android platform-tools או שים תיקיית platform-tools ליד האפליקציה.")
            return

        if not devices:
            self._set_status("red", "לא מחובר", "לא נמצאה משקפת ב‑ADB. חבר כבל USB שתומך Data.")
        elif any(d.state == "unauthorized" for d in devices):
            self._set_status("yellow", "ממתין לאישור", "בתוך המשקפת צריך לאשר USB Debugging ולסמן Always allow from this computer.")
        elif any(d.state == "device" for d in devices):
            ready = [d for d in devices if d.state == "device"]
            main = ready[0]
            name = f"{main.model} ({main.serial})" if main.model else main.serial
            self._set_status("green", "מחובר ומוכן לשליחה", f"משקפת מזוהה: {name}")
        else:
            states = ", ".join(f"{d.serial}: {d.state}" for d in devices)
            self._set_status("red", "ADB לא מוכן", f"נמצאו מכשירים אבל לא במצב device: {states}")

        if not silent:
            self._log(f"נמצאו {len(devices)} מכשירים.")

    def _handle_refresh_error(self, error: str, silent: bool) -> None:
        self._set_status("red", "שגיאת ADB", error)
        if not silent:
            self._log(f"שגיאת רענון: {error}")

    def _get_selected_device(self) -> Device | None:
        selected = self.selected_device_var.get()
        if not selected:
            return None

        serial = selected.split("|")[0].strip()
        for d in self.devices_cache:
            if d.serial == serial:
                return d
        return None

    def send_wifi(self) -> None:
        ssid = self.ssid_var.get().strip()
        password = self.password_var.get()
        security = self.security_var.get().strip()

        if not ssid:
            messagebox.showwarning("חסר SSID", "צריך להזין שם רשת WiFi.")
            return

        if security in ("wpa2", "wpa3") and not password:
            messagebox.showwarning("חסרה סיסמה", "צריך להזין סיסמה לרשת מאובטחת.")
            return

        device = self._get_selected_device()
        if not device:
            messagebox.showwarning("אין משקפת", "לא נמצאה משקפת. חבר USB ורענן.")
            return

        if device.state == "unauthorized":
            messagebox.showwarning("צריך אישור", "שים את המשקפת ואשר Always allow from this computer.")
            return

        if device.state != "device":
            messagebox.showwarning("ADB לא מוכן", f"המשקפת במצב {device.state}, לא במצב device.")
            return

        self.send_button.configure(state="disabled")
        self._log(f"שולח WiFi אל {device.serial}...")
        self._set_status("gray", "שולח הגדרות", "מפעיל WiFi ואז שולח את פרטי הרשת למשקפת.")

        def worker() -> None:
            logs: list[str] = []

            code1, out1, err1 = self.adb.enable_wifi(device.serial)
            logs.append(f"$ adb -s {device.serial} shell svc wifi enable")
            logs.append(out1 or err1 or f"exit code: {code1}")

            time.sleep(1)

            code2, out2, err2 = self.adb.connect_network(device.serial, ssid, security, password)
            logs.append(f'$ adb -s {device.serial} shell cmd wifi connect-network "{ssid}" {security} {"***" if password else ""}'.strip())
            logs.append(out2 or err2 or f"exit code: {code2}")

            time.sleep(2)

            code3, out3, err3 = self.adb.wifi_status(device.serial)
            logs.append("$ adb shell cmd wifi status")
            logs.append(out3 or err3 or f"exit code: {code3}")

            success = code1 == 0 and code2 == 0
            self.after(0, lambda: self._finish_send(success, logs))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_send(self, success: bool, logs: list[str]) -> None:
        for line in logs:
            self._log(line)

        if success:
            self._set_status("green", "נשלח", "פקודת החיבור נשלחה. אפשר לנתק את המשקפת ולחבר את הבאה; שם הרשת והסיסמה נשארים במסך.")
        else:
            self._set_status("red", "השליחה נכשלה", "בדוק לוג, כבל USB, הרשאת Debugging, שם רשת וסיסמה.")

        self.send_button.configure(state="normal")
        self.refresh_devices(silent=True)

    def check_wifi_status(self) -> None:
        device = self._get_selected_device()
        if not device or device.state != "device":
            messagebox.showwarning("אין משקפת מוכנה", "בחר משקפת שמופיעה במצב device.")
            return

        self._log(f"בודק WiFi עבור {device.serial}...")

        def worker() -> None:
            code, out, err = self.adb.wifi_status(device.serial)
            self.after(0, lambda: self._log(out or err or f"exit code: {code}"))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = QuestWifiApp()
    app.mainloop()
