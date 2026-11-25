#!/data/data/com.termux/files/usr/bin/python3
# -*- coding: utf-8 -*-

import time
import re
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
CHECK_INTERVAL = 10           # ระยะเวลาสแกนสถานะทุกรอบ (วินาที)
REJOIN_DELAY = 35             # ระยะเวลารอให้เกมโหลดหลังจากสั่งเปิด 1 จอ (วินาที)
USE_ROOT = True               # True = ใช้สิทธิ์ Root (su), False = ใช้ ADB (Wireless Debugging)
CHECK_DISCONNECTED_UI = True  # True = เช็กข้อความ Disconnected บนหน้าจอด้วย

# ==============================================================================
# ตั้งค่าบัญชีและแอปโคลน (Multi-Account & Clone Apps Configuration)
# ==============================================================================
ACCOUNTS = [
    {
        "name": "ID_หลัก_1",
        "place_id": 8304191830,                 # Place ID ของแมพ
        "link_code": "",                        # ใส่ VIP Server Link Code (ถ้ามี)
        "package": "com.roblox.client",         # ชื่อ Package ของแอป Roblox ตัวหลัก
        "android_user_id": 0                    # 0 = ระบบหลัก (หรือใส่ 999 / 10 สำหรับ Dual App)
    },
    # ตัวอย่างการเพิ่มจอโคลนตัวที่ 2 (เอาเครื่องหมาย # ออกหากต้องการใช้งาน):
    # {
    #     "name": "ID_ไก่_2",
    #     "place_id": 8304191830,
    #     "link_code": "",
    #     "package": "com.roblox.client2",
    #     "android_user_id": 0
    # }
]

# ==============================================================================
# ตัวแปรจัดการสถานะ UI
# ==============================================================================
console = Console()
logs = deque(maxlen=8)  # เก็บประวัติการทำงานล่าสุด 8 บรรทัด

account_states = []
for acc in ACCOUNTS:
    account_states.append({
        "status_text": "[dim]รอตรวจสอบ...[/dim]",
        "rejoin_count": 0,
        "last_rejoin": "-",
        "pid": "-"
    })

def add_log(message: str):
    now = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[dim][{now}][/dim] {message}")

def get_shell_output(cmd: str, use_root: bool) -> str:
    full_cmd = f"su -c '{cmd}'" if use_root else f"adb shell {cmd}"
    try:
        res = subprocess.run(
            full_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10
        )
        return res.stdout or ""
    except Exception as e:
        add_log(f"[bold red]Shell Error:[/bold red] {e}")
        return ""

def run_shell_cmd(cmd: str, use_root: bool):
    full_cmd = f"su -c '{cmd}'" if use_root else f"adb shell {cmd}"
    subprocess.run(full_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_running_roblox_instances(use_root: bool):
    """
    ตรวจหารายชื่อโปรเซสของ Roblox ที่กำลังทำงานอยู่บนเครื่อง
    คืนค่าเป็น dict: {(android_user_id, package_name): pid}
    """
    output = get_shell_output("ps -A -o USER,PID,NAME", use_root)
    running = {}

    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue

        proc_user, pid, proc_name = parts[0], parts[1], parts[2]
        if ":" in proc_name:
            continue

        if "roblox" in proc_name.lower():
            m = re.match(r"^u(\d+)_", proc_user)
            android_uid = int(m.group(1)) if m else 0
            running[(android_uid, proc_name)] = pid

    return running

def check_screen_disconnected(use_root: bool):
    """
    ตรวจสอบหน้าจอปัจจุบันว่ามีหน้าต่าง Disconnected / Error Code ค้างอยู่หรือไม่
    คืนค่าชื่อ package ที่กำลังค้างหน้า Disconnected (หรือ None หากปกติ)
    """
    if not CHECK_DISCONNECTED_UI:
        return None

    xml_data = get_shell_output("uiautomator dump /dev/tty", use_root)
    if not xml_data:
        return None

    lower_xml = xml_data.lower()
    disconnect_keywords = [
        "disconnected",
        "error code:",
        "lost connection",
        "same account launched",
        "kicked by server",
        "idle for 20 minutes"
    ]

    if any(kw in lower_xml for kw in disconnect_keywords):
        m = re.search(r'package="([^"]*roblox[^"]*)"', xml_data, re.IGNORECASE)
        if m:
            return m.group(1)
        return "UNKNOWN_ROBLOX_PKG"

    return None

def launch_clone_instance(account: dict, use_root: bool):
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
    table = Table(box=box.ROUNDED, expand=True, border_style="cyan")
    table.add_column("ชื่อบัญชี", style="bold white", justify="left")
    table.add_column("Package / User", style="dim", justify="left")
    table.add_column("PID", style="cyan", justify="center")
    table.add_column("สถานะบนเครื่อง", justify="center")
    table.add_column("Rejoin", style="yellow", justify="center")
    table.add_column("เปิดใหม่ล่าสุด", style="dim", justify="center")

    for idx, acc in enumerate(ACCOUNTS):
        state = account_states[idx]
        pkg_info = f"{acc['package']} (u{acc.get('android_user_id', 0)})"
        table.add_row(
            acc["name"],
            pkg_info,
            state["pid"],
            state["status_text"],
            str(state["rejoin_count"]),
            state["last_rejoin"]
        )

    log_content = "\n".join(logs) if logs else "[dim]ยังไม่มีประวัติการทำงาน...[/dim]"
    log_panel = Panel(log_content, title="[bold]บันทึกการทำงาน (Logs)[/bold]", border_style="bright_black", box=box.ROUNDED)

    mode_text = "ROOT (su)" if USE_ROOT else "ADB Wireless"
    ui_check_text = "เปิด" if CHECK_DISCONNECTED_UI else "ปิด"
    footer = Text.from_markup(
        f"โหมดสิทธิ์: [bold green]{mode_text}[/bold green]  |  "
        f"เช็กหน้าจอหลุด: [bold cyan]{ui_check_text}[/bold cyan]  |  "
        f"สถานะ: {status_banner}"
    )

    ui_group = Group(
        table,
        log_panel,
        Panel(footer, border_style="blue", box=box.ROUNDED)
    )

    return Panel(
        ui_group,
        title="[bold cyan]🎮 ROBLOX LOCAL PROCESS & SCREEN MONITOR[/bold cyan]",
        subtitle="[dim]กด Ctrl + C เพื่อหยุดการทำงาน[/dim]",
        border_style="bright_cyan",
        padding=(1, 1)
    )

def main():
    add_log("เริ่มต้นระบบตรวจจับโปรเซสและหน้าจอบนเครื่อง...")

    with Live(generate_ui("[yellow]กำลังเริ่มต้น...[/yellow]"), console=console, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                live.update(generate_ui("[bold cyan]กำลังสแกนโปรเซสและหน้าจอ...[/bold cyan]"))
                running_instances = get_running_roblox_instances(USE_ROOT)
                disconnected_pkg = check_screen_disconnected(USE_ROOT)

                for idx, acc in enumerate(ACCOUNTS):
                    name = acc["name"]
                    pkg = acc["package"]
                    android_uid = acc.get("android_user_id", 0)
                    key = (android_uid, pkg)

                    is_running = key in running_instances
                    is_screen_dc = (
                        disconnected_pkg is not None
                        and (
                            disconnected_pkg == pkg
                            or (disconnected_pkg == "UNKNOWN_ROBLOX_PKG" and len(ACCOUNTS) == 1)
                        )
                    )

                    if is_running and not is_screen_dc:
                        pid = running_instances[key]
                        account_states[idx]["pid"] = pid
                        account_states[idx]["status_text"] = "[bold green]🟢 กำลังรันอยู่ (Running)[/bold green]"
                    else:
                        reason = "หน้าจอขึ้น Disconnected" if is_screen_dc else "ปิดอยู่ / แอปเด้งหลุด"
                        account_states[idx]["pid"] = "-"
                        account_states[idx]["status_text"] = f"[bold red]🔴 {reason}[/bold red]"
                        account_states[idx]["rejoin_count"] += 1
                        account_states[idx]["last_rejoin"] = datetime.now().strftime("%H:%M:%S")

                        add_log(f"[bold yellow]{name}[/bold yellow] ({pkg}) {reason} -> กำลังเปิดแอปใหม่...")
                        live.update(generate_ui(f"[bold yellow]กำลังดึง {name} กลับเข้าแมพ...[/bold yellow]"))

                        launch_clone_instance(acc, USE_ROOT)

                        for sec in range(REJOIN_DELAY, 0, -1):
                            account_states[idx]["status_text"] = f"[bold yellow]⏳ กำลังโหลดเกม ({sec}s)...[/bold yellow]"
                            live.update(generate_ui(f"[yellow]รอ {name} โหลดเข้าเกม ({sec} วินาที)...[/yellow]"))
                            time.sleep(1)

                        account_states[idx]["status_text"] = "[cyan]สั่งเปิดแล้ว (รอสแกนรอบถัดไป)[/cyan]"
                        add_log(f"เปิดแอปให้ [bold green]{name}[/bold green] เรียบร้อยแล้ว")

                for sec in range(CHECK_INTERVAL, 0, -1):
                    live.update(generate_ui(f"[green]ปกติ[/green] - สแกนรอบถัดไปใน [bold white]{sec}[/bold white] วินาที"))
                    time.sleep(1)

        except KeyboardInterrupt:
            pass

    console.print("\n[bold yellow]หยุดการทำงานของระบบเรียบร้อยแล้ว[/bold yellow]")

if __name__ == "__main__":
    main()
