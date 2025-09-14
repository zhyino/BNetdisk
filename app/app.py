import os
import queue
from flask import Flask, render_template, request, jsonify, Response
from .backup import BackupWorker

app = Flask(__name__)

task_queue = queue.Queue()
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "backup_log.txt")
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
    tasks = data.get("tasks", [])
    
    if not tasks or not isinstance(tasks, list):
        return jsonify({"error": "无效的任务格式"}), 400
    
    for task in tasks:
        source = task.get("source")
        dest = task.get("dest")
        
        if not source or not dest:
            return jsonify({"error": "路径不完整"}), 400
            
        if not os.path.exists(source):
            return jsonify({"error": f"源路径不存在: {source}"}), 400
            
        # 确保目标目录存在
        os.makedirs(dest, exist_ok=True)
            
        task_queue.put({"source": source, "dest": dest})
        log_callback(f"任务已添加: {source} -> {dest}")
    
    return jsonify({"status": "ok", "count": len(tasks)})

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
