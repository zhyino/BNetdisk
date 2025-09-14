import os
import uuid
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
from backup.core import (
    load_backup_log, save_backup_log, is_valid_pair,
    backup_directory
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', str(uuid.uuid4()))
socketio = SocketIO(app, cors_allowed_origins="*")

# 存储用户的目录对
user_jobs = {}

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/add_directory_pair', methods=['POST'])
def add_directory_pair():
    """添加目录对"""
    data = request.json
    src_dir = data.get('src_dir', '').strip()
    dest_dir = data.get('dest_dir', '').strip()
    
    if not src_dir or not dest_dir:
        return jsonify({"status": "error", "message": "源目录和目标目录不能为空"})
    
    # 验证目录有效性
    valid, msg = is_valid_pair(src_dir, dest_dir)
    if not valid:
        return jsonify({"status": "error", "message": msg})
    
    # 生成唯一ID
    job_id = str(uuid.uuid4())
    if 'jobs' not in session:
        session['jobs'] = []
    
    session['jobs'].append({
        'id': job_id,
        'src_dir': src_dir,
        'dest_dir': dest_dir
    })
    session.modified = True
    
    return jsonify({
        "status": "success",
        "message": "目录对添加成功",
        "job": {
            'id': job_id,
            'src_dir': src_dir,
            'dest_dir': dest_dir
        }
    })

@app.route('/get_jobs', methods=['GET'])
def get_jobs():
    """获取所有目录对"""
    return jsonify({
        "status": "success",
        "jobs": session.get('jobs', [])
    })

@app.route('/remove_job', methods=['POST'])
def remove_job():
    """移除目录对"""
    data = request.json
    job_id = data.get('job_id')
    
    if 'jobs' in session:
        session['jobs'] = [job for job in session['jobs'] if job['id'] != job_id]
        session.modified = True
    
    return jsonify({"status": "success", "message": "目录对已移除"})

@socketio.on('start_backup')
def handle_start_backup(data):
    """开始备份过程"""
    filter_images = data.get('filter_images', True)
    filter_nfo = data.get('filter_nfo', False)
    jobs = session.get('jobs', [])
    
    if not jobs:
        emit('backup_log', {'message': '没有添加任何目录对，请先添加'})
        emit('backup_complete', {'status': 'error', 'message': '没有目录对可备份'})
        return
    
    try:
        # 加载备份日志
        backed_up = load_backup_log()
        total_backed = 0
        total_skipped = 0
        
        emit('backup_log', {'message': f'开始备份，共 {len(jobs)} 个目录对'})
        
        # 依次处理每个目录对
        for i, job in enumerate(jobs, 1):
            emit('backup_log', {'message': f'处理第 {i}/{len(jobs)} 个目录对: {job["src_dir"]} -> {job["dest_dir"]}'})
            
            # 备份回调函数
            def callback(msg):
                emit('backup_log', {'message': msg})
            
            # 执行备份
            backed, skipped, _ = backup_directory(
                job['src_dir'], 
                job['dest_dir'], 
                backed_up,
                filter_images,
                filter_nfo,
                callback
            )
            
            total_backed += backed
            total_skipped += skipped
        
        # 保存备份日志
        save_backup_log(backed_up)
        
        emit('backup_log', {'message': f'备份完成！总共备份 {total_backed} 个文件，跳过 {total_skipped} 个文件'})
        emit('backup_complete', {
            'status': 'success', 
            'message': f'备份完成！总共备份 {total_backed} 个文件，跳过 {total_skipped} 个文件'
        })
        
    except Exception as e:
        error_msg = f'备份过程出错: {str(e)}'
        emit('backup_log', {'message': error_msg})
        emit('backup_complete', {'status': 'error', 'message': error_msg})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
