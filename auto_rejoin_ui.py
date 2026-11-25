#!/data/data/com.termux/files/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import json
import urllib.request
import urllib.error
import subprocess
from datetime import datetime
from collections import deque

from rich.console import Console, Group
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich import box

# ==============================================================================
# ตั้งค่าระบบรวม (Global Configuration)
# ==============================================================================
CHECK_INTERVAL = 20           # ระยะเวลาเช็คสถานะทุกรอบ (วินาที)
REJOIN_DELAY = 35             # ระยะเวลารอให้เกมโหลดหลังจากสั่งเปิด 1 จอ (วินาที)
USE_ROOT = True               # True = ใช้สิทธิ์ Root (su), False = ใช้ ADB (Wireless Debugging)

# ==============================================================================
# ตั้งค่าบัญชีและแอปโคลน (Multi-Account & Clone Apps Configuration)
# ==============================================================================
ACCOUNTS = [
    {
        "name": "ID_หลัก_1",
        "user_id": 2267991284,                  # User ID ของคุณ
        "place_id": 8304191830,                 # Place ID ของแมพ
        "link_code": "",                        # ใส่ VIP Server Link Code (ถ้ามี)
        "package": "com.roblox.client",         # ชื่อ Package ของแอป Roblox ตัวหลัก
        "android_user_id": 0,                   # 0 = ระบบหลัก
        "cookie": ""                            # .ROBLOSECURITY (ใส่เฉพาะกรณีปิดสถานะออนไลน์)
    }
]

# ==============================================================================
# ตัวแปรจัดการสถานะ UI
# ==============================================================================
console = Console()
logs = deque(maxlen=8)  # เก็บประวัติการทำงานล่าสุด 8 บรรทัด

account_states = {}
for acc in ACCOUNTS:
    account_states[acc["user_id"]] = {
        "status_text": "[dim]รอตรวจสอบ...[/dim]",
        "rejoin_count": 0,
        "last_rejoin": "-"
    }

def add_log(message: str):
    now = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[dim][{now}][/dim] {message}")

def check_batch_presence(accounts):
    url = "https://presence.roblox.com/v1/presence/users"
    results = {}

    has_cookies = any(acc.get("cookie") for acc in accounts)
    if not has_cookies:
        user_ids = [acc["user_id"] for acc in accounts]
        payload = json.dumps({"userIds": user_ids}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Android; Termux)"
        }
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    for item in data.get("userPresences", []):
                        results[item["userId"]] = item["userPresenceType"]
                    return results
        except Exception as e:
            add_log(f"[bold red]Error:[/bold red] เชื่อมต่อ API ล้มเหลว ({e})")
            return None

    for acc in accounts:
        uid = acc["user_id"]
        cookie = acc.get("cookie", "")
        payload = json.dumps({"userIds": [uid]}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Android; Termux)"
        }
        if cookie:
            headers["Cookie"] = f".ROBLOSECURITY={cookie}"
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    presences = data.get("userPresences", [])
                    if presences:
                        results[uid] = presences[0]["userPresenceType"]
        except Exception as e:
            add_log(f"[bold red]Error:[/bold red] เช็ค {acc['name']} ล้มเหลว")
            results[uid] = None

    return results

def run_shell_cmd(cmd, use_root):
    full_cmd = f"su -c '{cmd}'" if use_root else f"adb shell {cmd}"
    subprocess.run(full_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def launch_clone_instance(account, use_root):
    pkg = account["package"]
    place_id = account["place_id"]
    link_code = account.get("link_code", "")
    android_uid = account.get("android_user_id", 0)

    deep_link = f"roblox://placeId={place_id}"
    if link_code:
        deep_link += f"&linkCode={link_code}"

    user_flag = f"--user {android_uid}" if android_uid is not None else "--user 0"

    stop_cmd = f"am force-stop {user_flag} {pkg}"
    start_cmd = f'am start {user_flag} -a android.intent.action.VIEW -d "{deep_link}" {pkg}'

    run_shell_cmd(stop_cmd, use_root)
    time.sleep(2)
    run_shell_cmd(start_cmd, use_root)

def generate_ui(status_banner: str) -> Panel:
    # 1. สร้างตารางแสดงสถานะบัญชี
    table = Table(box=box.ROUNDED, expand=True, border_style="cyan")
    table.add_column("ชื่อบัญชี", style="bold white", justify="left")
    table.add_column("Package / User", style="dim", justify="left")
    table.add_column("สถานะปัจจุบัน", justify="center")
    table.add_column("Rejoin", style="yellow", justify="center")
    table.add_column("ดึงกลับล่าสุด", style="dim", justify="center")

    for acc in ACCOUNTS:
        uid = acc["user_id"]
        state = account_states[uid]
        pkg_info = f"{acc['package']} (u{acc.get('android_user_id', 0)})"
        table.add_row(
            acc["name"],
            pkg_info,
            state["status_text"],
            str(state["rejoin_count"]),
            state["last_rejoin"]
        )

    # 2. กล่องแสดง Log
    log_content = "\n".join(logs) if logs else "[dim]ยังไม่มีประวัติการทำงาน...[/dim]"
    log_panel = Panel(log_content, title="[bold]บันทึกการทำงาน (Logs)[/bold]", border_style="bright_black", box=box.ROUNDED)

    # 3. แถบสถานะด้านล่าง
    mode_text = "ROOT (su)" if USE_ROOT else "ADB Wireless"
    footer = Text.from_markup(f"โหมดสิทธิ์: [bold green]{mode_text}[/bold green]  |  สถานะระบบ: {status_banner}")

    ui_group = Group(
        table,
        log_panel,
        Panel(footer, border_style="blue", box=box.ROUNDED)
    )

    return Panel(
        ui_group,
        title="[bold cyan]🎮 ROBLOX AUTO REJOIN MANAGER (MULTI-INSTANCE)[/bold cyan]",
        subtitle="[dim]กด Ctrl + C เพื่อหยุดการทำงาน[/dim]",
        border_style="bright_cyan",
        padding=(1, 1)
    )

def main():
    add_log("เริ่มต้นระบบตรวจสอบอัตโนมัติ...")

    with Live(generate_ui("[yellow]กำลังเริ่มต้น...[/yellow]"), console=console, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                live.update(generate_ui("[bold cyan]กำลังตรวจสอบสถานะ API...[/bold cyan]"))
                presences = check_batch_presence(ACCOUNTS)

                if presences is None:
                    for sec in range(CHECK_INTERVAL, 0, -1):
                        live.update(generate_ui(f"[bold red]API ขัดข้อง[/bold red] รอเช็คใหม่ใน {sec} วินาที..."))
                        time.sleep(1)
                    continue

                for acc in ACCOUNTS:
                    uid = acc["user_id"]
                    name = acc["name"]
                    status = presences.get(uid)

                    if status is None:
                        account_states[uid]["status_text"] = "[bold red]API Error[/bold red]"
                    elif status == 2:
                        account_states[uid]["status_text"] = "[bold green]🟢 อยู่ในเกม (In-Game)[/bold green]"
                    else:
                        status_label = "หน้าล็อบบี้ (Online)" if status == 1 else "ออฟไลน์ (Offline)"
                        account_states[uid]["status_text"] = f"[bold red]🔴 หลุด ({status_label})[/bold red]"
                        account_states[uid]["rejoin_count"] += 1
                        account_states[uid]["last_rejoin"] = datetime.now().strftime("%H:%M:%S")

                        add_log(f"[bold yellow]{name}[/bold yellow] หลุดออกจากเกม -> กำลังสั่งเปิดแอปใหม่...")
                        live.update(generate_ui(f"[bold yellow]กำลังดึง {name} กลับเข้าเซิร์ฟเวอร์...[/bold yellow]"))

                        launch_clone_instance(acc, USE_ROOT)

                        for sec in range(REJOIN_DELAY, 0, -1):
                            account_states[uid]["status_text"] = f"[bold yellow]⏳ กำลังโหลดเกม ({sec}s)...[/bold yellow]"
                            live.update(generate_ui(f"[yellow]รอ {name} โหลดเข้าเกม ({sec} วินาที)...[/yellow]"))
                            time.sleep(1)

                        account_states[uid]["status_text"] = "[cyan]ส่งคำสั่งแล้ว (รอเช็ครอบถัดไป)[/cyan]"
                        add_log(f"เปิดแอปให้ [bold green]{name}[/bold green] เรียบร้อยแล้ว")

                # นับถอยหลังรอเช็ครอบถัดไป
                for sec in range(CHECK_INTERVAL, 0, -1):
                    live.update(generate_ui(f"[green]ปกติ[/green] - เช็ครอบถัดไปใน [bold white]{sec}[/bold white] วินาที"))
                    time.sleep(1)

        except KeyboardInterrupt:
            pass

    console.print("\n[bold yellow]หยุดการทำงานของระบบ Auto Rejoin เรียบร้อยแล้ว[/bold yellow]")

if __name__ == "__main__":
    main()
