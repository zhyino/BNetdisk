import os
import queue
from flask import Flask, render_template, request, jsonify, Response
from .backup import BackupWorker

app = Flask(__name__)

task_queue = queue.Queue()
LOG_FILE = "/app/backup_log.txt"
log_subscribers = []

def log_callback(message: str):
    line = f"[LOG] {message}\n"
    print(line, end="")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    for q in log_subscribers:
        try:
            q.put_nowait(line)
        except queue.Full:
            pass

worker = BackupWorker(task_queue, log_callback)
worker.start()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/add", methods=["POST"])
def api_add():
    data = request.json
    path = data.get("path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "目录不存在"}), 400
    task_queue.put({"path": path})
    log_callback(f"任务已添加: {path}")
    return jsonify({"status": "ok"})

@app.route("/api/queue")
def api_queue():
    items = list(task_queue.queue)
    return jsonify({"queue": items})

@app.route("/stream")
def stream():
    def event_stream(q):
        while True:
            try:
                msg = q.get()
                yield f"data: {msg}\n\n"
            except Exception:
                break

    q = queue.Queue(maxsize=100)
    log_subscribers.append(q)
    return Response(event_stream(q), mimetype="text/event-stream")
