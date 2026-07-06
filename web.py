import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, send_from_directory, request

from monitor import Monitor, MonitorDB, ping_host, tcp_delay, load_config

app = Flask(__name__, static_folder="static", static_url_path="")
monitor_instance = None
tz = timezone(timedelta(hours=8))

config = load_config()


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/icmp/status")
def api_icmp_status():
    minutes = request.args.get("minutes", type=int)
    data = monitor_instance.db.query_icmp_recent(limit_per_target=20000)
    result = {}
    cutoff = None
    if minutes:
        cutoff = (datetime.now(tz) - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    for target_name, entries in data.items():
        entries.sort(key=lambda x: x["timestamp"])
        if cutoff:
            entries = [e for e in entries if e["timestamp"] >= cutoff]
        result[target_name] = {
            "host": entries[0]["target_host"] if entries else "",
            "latest": entries[-1] if entries else None,
            "history": [
                {"ts": e["timestamp"], "avg_ms": e["avg_ms"],
                 "loss_pct": e["loss_pct"], "reachable": e["reachable"],
                 "sent": e["sent"], "received": e["received"]}
                for e in entries
            ],
        }
    return jsonify(result)


@app.route("/api/tcp/status")
def api_tcp_status():
    minutes = request.args.get("minutes", type=int)
    data = monitor_instance.db.query_tcp_recent(limit_per_target=20000)
    result = {}
    cutoff = None
    if minutes:
        cutoff = (datetime.now(tz) - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    for target_name, entries in data.items():
        entries.sort(key=lambda x: x["timestamp"])
        if cutoff:
            entries = [e for e in entries if e["timestamp"] >= cutoff]
        latest = entries[-1] if entries else None
        result[target_name] = {
            "host": latest["target_host"] if latest else "",
            "port": latest["target_port"] if latest else 0,
            "region": latest["region"] if latest else "",
            "isp": latest["isp"] if latest else "",
            "latest": latest,
            "history": [
                {"ts": e["timestamp"], "delay_ms": e["delay_ms"],
                 "reachable": e["reachable"]}
                for e in entries
            ],
        }
    return jsonify(result)


@app.route("/api/ping_now")
def api_ping_now():
    count = int(request.args.get("count", config["ping_count"]))
    timeout = int(request.args.get("timeout", config["ping_timeout"]))
    icmp_targets = config.get("icmp_targets", [])
    results = []
    for t in icmp_targets:
        r = ping_host(t["host"], count, timeout)
        r["target_name"] = t["name"]
        r["timestamp"] = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        results.append(r)
    return jsonify(results)


@app.route("/api/tcp_now")
def api_tcp_now():
    timeout = int(request.args.get("timeout", config.get("tcp_timeout", 5)))
    tcp_targets = config.get("tcp_targets", [])
    results = []
    for t in tcp_targets:
        r = tcp_delay(t["host"], t["port"], timeout)
        r["target_name"] = t["name"]
        r["target_region"] = t.get("region", "")
        r["target_isp"] = t.get("isp", "")
        r["timestamp"] = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        results.append(r)
    return jsonify(results)


@app.route("/api/tcp/summary")
def api_tcp_summary():
    data = monitor_instance.db.query_tcp_recent(limit_per_target=240)
    summary = {}
    for name, entries in data.items():
        if not entries:
            continue
        total = len(entries)
        reachable_count = sum(1 for e in entries if e["reachable"])
        delays = [e["delay_ms"] for e in entries if e["delay_ms"] is not None]
        summary[name] = {
            "host": entries[0]["target_host"],
            "port": entries[0]["target_port"],
            "region": entries[0]["region"],
            "isp": entries[0]["isp"],
            "reachable_pct": round(reachable_count / total * 100, 1) if total else 0,
            "avg_delay": round(sum(delays) / len(delays), 2) if delays else None,
            "min_delay": round(min(delays), 2) if delays else None,
            "max_delay": round(max(delays), 2) if delays else None,
        }
    return jsonify(summary)


@app.route("/api/reachable_summary")
def api_reachable_summary():
    data = monitor_instance.db.query_icmp_recent(limit_per_target=240)
    summary = {}
    for name, entries in data.items():
        if not entries:
            continue
        total = len(entries)
        reachable_count = sum(1 for e in entries if e["reachable"])
        avg_lat = sum(e["avg_ms"] for e in entries if e["avg_ms"]) / max(
            reachable_count, 1
        )
        summary[name] = {
            "host": entries[0]["target_host"],
            "reachable_pct": round(reachable_count / total * 100, 1),
            "avg_latency": round(avg_lat, 2),
        }
    return jsonify(summary)


@app.route("/api/targets")
def api_targets():
    return jsonify({
        "icmp": config.get("icmp_targets", []),
        "tcp": config.get("tcp_targets", []),
    })


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        new_config = request.get_json()
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        global config
        config = new_config
        return jsonify({"ok": True})
    return jsonify(config)


def run_web():
    web_cfg = config["web"]
    print(f"Web 面板启动: http://{web_cfg['host']}:{web_cfg['port']}")
    app.run(
        host=web_cfg["host"],
        port=web_cfg["port"],
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    monitor_instance = Monitor()
    monitor_instance.start()

    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor_instance.stop()
        print("\n服务已停止")
