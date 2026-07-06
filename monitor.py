import subprocess
import json
import sqlite3
import os
import time
import re
import socket
import threading
from datetime import datetime, timezone, timedelta

tz = timezone(timedelta(hours=8))


def load_config(path="config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class MonitorDB:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "monitor.db")
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._connect()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS icmp_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                target_host TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                sent INTEGER, received INTEGER,
                loss_pct REAL, min_ms REAL, avg_ms REAL,
                max_ms REAL, mdev_ms REAL, reachable INTEGER
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_icmp_ts ON icmp_results(timestamp)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tcp_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                target_host TEXT NOT NULL,
                target_port INTEGER NOT NULL,
                target_region TEXT,
                target_isp TEXT,
                timestamp TEXT NOT NULL,
                delay_ms REAL,
                reachable INTEGER,
                error TEXT
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tcp_ts ON tcp_results(timestamp)"
        )
        conn.commit()
        conn.close()

    def insert_icmp(self, r):
        conn = self._connect()
        conn.execute(
            """INSERT INTO icmp_results (target_name, target_host, timestamp,
               sent, received, loss_pct, min_ms, avg_ms, max_ms, mdev_ms, reachable)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["target_name"], r["target_host"], r["timestamp"],
                r["sent"], r["received"], r["loss_pct"],
                r["min_ms"], r["avg_ms"], r["max_ms"], r["mdev_ms"],
                r["reachable"],
            ),
        )
        conn.commit()
        conn.close()

    def insert_tcp(self, r):
        conn = self._connect()
        conn.execute(
            """INSERT INTO tcp_results (target_name, target_host, target_port,
               target_region, target_isp, timestamp, delay_ms, reachable, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["target_name"], r["target_host"], r["target_port"],
                r.get("region", ""), r.get("isp", ""), r["timestamp"],
                r["delay_ms"], r["reachable"], r.get("error", ""),
            ),
        )
        conn.commit()
        conn.close()

    def query_icmp_recent(self, limit_per_target=120):
        conn = self._connect()
        rows = conn.execute(
            """SELECT target_name, target_host, timestamp, sent, received,
               loss_pct, min_ms, avg_ms, max_ms, mdev_ms, reachable
               FROM icmp_results ORDER BY id DESC LIMIT 10000"""
        ).fetchall()
        conn.close()

        from collections import defaultdict
        groups = defaultdict(list)
        for row in rows:
            groups[row[0]].append({
                "target_name": row[0], "target_host": row[1],
                "timestamp": row[2], "sent": row[3], "received": row[4],
                "loss_pct": row[5], "min_ms": row[6], "avg_ms": row[7],
                "max_ms": row[8], "mdev_ms": row[9], "reachable": row[10],
            })
        return {k: v[:limit_per_target] for k, v in groups.items()}

    def query_tcp_recent(self, limit_per_target=120):
        conn = self._connect()
        rows = conn.execute(
            """SELECT target_name, target_host, target_port, target_region,
               target_isp, timestamp, delay_ms, reachable, error
               FROM tcp_results ORDER BY id DESC LIMIT 20000"""
        ).fetchall()
        conn.close()

        from collections import defaultdict
        groups = defaultdict(list)
        for row in rows:
            groups[row[0]].append({
                "target_name": row[0], "target_host": row[1],
                "target_port": row[2], "region": row[3], "isp": row[4],
                "timestamp": row[5], "delay_ms": row[6], "reachable": row[7],
                "error": row[8],
            })
        return {k: v[:limit_per_target] for k, v in groups.items()}


def ping_host(host, count=10, timeout=5):
    cmd = ["ping", "-c", str(count), "-W", str(timeout), host]
    result = {
        "target_host": host, "sent": count, "received": 0,
        "loss_pct": 100.0, "min_ms": None, "avg_ms": None,
        "max_ms": None, "mdev_ms": None, "reachable": 0,
    }
    try:
        output = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout * count + 5
        )
        stdout = output.stdout
    except subprocess.TimeoutExpired:
        return result

    if output.returncode != 0 and "100% packet loss" in stdout:
        return result

    m = re.search(r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received", stdout)
    if m:
        result["sent"] = int(m.group(1))
        result["received"] = int(m.group(2))

    m = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", stdout)
    if m:
        result["loss_pct"] = float(m.group(1))

    m = re.search(
        r"rtt\s+min/avg/max/mdev\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms",
        stdout,
    )
    if m:
        result["min_ms"] = float(m.group(1))
        result["avg_ms"] = float(m.group(2))
        result["max_ms"] = float(m.group(3))
        result["mdev_ms"] = float(m.group(4))

    if result["received"] > 0:
        result["reachable"] = 1

    return result


def tcp_delay(host, port, timeout=5):
    result = {
        "target_host": host, "target_port": port,
        "delay_ms": None, "reachable": 0, "error": "",
    }
    try:
        addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        if not addrs:
            result["error"] = "DNS resolution failed"
            return result

        ip = addrs[0][4][0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        t0 = time.perf_counter()
        sock.connect((ip, port))
        t1 = time.perf_counter()

        sock.close()
        result["delay_ms"] = round((t1 - t0) * 1000, 2)
        result["reachable"] = 1
    except socket.timeout:
        result["error"] = "Connection timeout"
    except socket.gaierror as e:
        result["error"] = f"DNS error: {e}"
    except ConnectionRefusedError:
        result["error"] = "Connection refused"
    except OSError as e:
        result["error"] = str(e)

    return result


def run_icmp_round(db, targets, ping_count, ping_timeout):
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] ICMP ping 检测...")
    for t in targets:
        result = ping_host(t["host"], ping_count, ping_timeout)
        result["target_name"] = t["name"]
        result["timestamp"] = now
        db.insert_icmp(result)
        status = "可达" if result["reachable"] else "不可达"
        avg = f"{result['avg_ms']}ms" if result["avg_ms"] else "N/A"
        loss = f"{result['loss_pct']}%"
        print(f"  [ICMP] {t['name']:16s} ({t['host']:16s}) "
              f"{status} | 延迟: {avg:>8s} | 丢包: {loss:>6s}")


def run_tcp_round(db, targets, tcp_timeout):
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now}] TCP 握手延迟检测...")
    for t in targets:
        result = tcp_delay(t["host"], t["port"], tcp_timeout)
        result["target_name"] = t["name"]
        result["region"] = t.get("region", "")
        result["isp"] = t.get("isp", "")
        result["timestamp"] = now
        db.insert_tcp(result)
        status = "可达" if result["reachable"] else "不可达"
        delay = f"{result['delay_ms']}ms" if result["delay_ms"] else "N/A"
        region = f"{result.get('region', '')}"
        isp = f"{result.get('isp', '')}"
        print(f"  [TCP]  {t['name']:16s} ({t['host']}:{t['port']:<5d}) "
              f"{region:4s} {isp:4s} {status} | TCP延迟: {delay:>8s}")


class Monitor:
    def __init__(self, config_path="config.json"):
        self.config = load_config(config_path)
        self.db = MonitorDB(self.config["data_dir"])
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        icmp_targets = self.config.get("icmp_targets", [])
        tcp_targets = self.config.get("tcp_targets", [])
        count = self.config["ping_count"]
        icmp_timeout = self.config["ping_timeout"]
        tcp_timeout = self.config.get("tcp_timeout", 5)
        interval = self.config["interval_seconds"]

        print("=" * 60)
        print("网络出口监控已启动")
        print(f"ICMP 目标: {len(icmp_targets)} | TCP 目标: {len(tcp_targets)}")
        print(f"检测间隔: {interval}s | Ping 次数: {count}")
        print("=" * 60)

        while not self._stop.is_set():
            if icmp_targets:
                run_icmp_round(self.db, icmp_targets, count, icmp_timeout)
            if tcp_targets:
                run_tcp_round(self.db, tcp_targets, tcp_timeout)
            self._stop.wait(interval)


if __name__ == "__main__":
    m = Monitor()
    try:
        m.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        m.stop()
        print("\n监控已停止")
