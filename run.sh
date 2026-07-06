#!/bin/bash
# 网络出口监控 - 启动脚本
# 用法: ./run.sh [start|stop|status|log]

set -e
cd "$(dirname "$0")"

VENV_DIR=".venv"
PID_FILE="monitor.pid"
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/monitor-$(date +%Y%m%d).log"
DATA_DIR="data"

start() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "监控已在运行中 (PID: $(cat $PID_FILE))"
        return 1
    fi

    mkdir -p "$LOG_DIR" "$DATA_DIR"

    if [ ! -d "$VENV_DIR" ]; then
        echo "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi

    echo "安装依赖..."
    "$VENV_DIR/bin/pip" install -q -r requirements.txt

    echo "启动监控服务..."
    nohup env PYTHONUNBUFFERED=1 "$VENV_DIR/bin/python" web.py > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "启动成功 (PID: $(cat $PID_FILE))"
        echo "日志: $LOG_FILE"
        echo "面板: http://$(hostname -I | awk '{print $1}'):8080"
    else
        echo "启动失败，查看日志: $LOG_FILE"
        rm -f "$PID_FILE"
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "已停止 (PID: $PID)"
        fi
        rm -f "$PID_FILE"
    else
        echo "未找到运行中的进程"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        PID=$(cat "$PID_FILE")
        echo "运行中 (PID: $PID)"
        echo "日志: $LOG_FILE"
        echo "数据: $DATA_DIR/monitor.db ($(du -h "$DATA_DIR/monitor.db" 2>/dev/null | cut -f1))"
        echo "面板: http://$(hostname -I | awk '{print $1}'):8080"
    else
        echo "未运行"
    fi
}

log() {
    if [ -f "$LOG_FILE" ]; then
        tail -50 "$LOG_FILE"
    else
        echo "日志文件不存在: $LOG_FILE"
    fi
}

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 2; start ;;
    status)  status ;;
    log)     log ;;
    *)       echo "用法: $0 {start|stop|restart|status|log}" ;;
esac
