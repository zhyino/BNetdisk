import os
import io
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from app.backup import BackupWorker

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 初始化工作目录
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/app/data')
os.makedirs(BACKUP_DIR, exist_ok=True)

# 初始化备份工作器
worker = BackupWorker(
    service_log=Path(BACKUP_DIR) / 'service_log.txt',
    backup_log=Path(BACKUP_DIR) / 'backup_log.txt'
)
worker.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/add', methods=['POST'])
def api_add():
    try:
        data = request.get_json()
        if not data or 'tasks' not in data:
            return jsonify({'status': 'error', 'message': 'No tasks provided'}), 400
            
        for task in data['tasks']:
            if not all(k in task for k in ['src', 'dst']):
                return jsonify({'status': 'error', 'message': 'Task missing src or dst'}), 400
                
            worker.add_task(task)
            
        return jsonify({'status': 'success', 'message': f'Added {len(data["tasks"])} tasks'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/queue')
def api_queue():
    return jsonify({
        'queue_size': worker.queue_size(),
        'active': worker.is_alive()
    })

@app.route('/api/logs')
def api_logs():
    try:
        lines = int(request.args.get('n', 200))
        logs = worker.get_last_logs(lines)
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stream')
def stream():
    def event_stream():
        while True:
            message = worker.get_message()
            if message:
                yield f'data: {json.dumps(message)}\n\n'
            else:
                yield ': keepalive\n\n'
                
    return Response(event_stream(), mimetype="text/event-stream")

def tail_file_lines(path: Path, lines: int = 200):
    """高效读取文件最后N行"""
    if not path.exists():
        return []
    
    try:
        with open(path, 'rb') as f:
            f.seek(0, io.SEEK_END)
            file_size = f.tell()
            
            if file_size < 1024 * 1024:  # 1MB以下直接读取
                f.seek(0)
                data = f.read().decode('utf-8', errors='ignore')
                return data.splitlines()[-lines:]
            
            buffer_size = 8192
            buffer = b''
            line_count = 0
            position = file_size
            
            while position > 0 and line_count < lines:
                step = min(buffer_size, position)
                position -= step
                f.seek(position)
                buffer = f.read(step) + buffer
                line_count += buffer.count(b'\n')
        
        data = buffer.decode('utf-8', errors='ignore')
        lines_list = data.splitlines()
        return lines_list[-lines:] if len(lines_list) > lines else lines_list
        
    except Exception as e:
        app.logger.error(f"Error reading log file: {e}")
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readlines()[-lines:]
        except Exception:
            return []

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('APP_PORT', 18008)), debug=False)
