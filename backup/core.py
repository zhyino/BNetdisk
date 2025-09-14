import os
import time
from typing import List, Set, Tuple

# 常见图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg', '.ico'}

def load_backup_log(log_file: str = 'backup_log.txt') -> Set[str]:
    """加载已备份文件日志"""
    backed_up = set()
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    backed_up.add(line.strip())
    except Exception as e:
        raise Exception(f"加载备份日志失败: {str(e)}")
    return backed_up

def save_backup_log(backed_up: Set[str], log_file: str = 'backup_log.txt') -> None:
    """保存已备份文件日志"""
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            for item in backed_up:
                f.write(item + '\n')
    except Exception as e:
        raise Exception(f"保存备份日志失败: {str(e)}")

def is_valid_pair(src_dir: str, dest_dir: str) -> Tuple[bool, str]:
    """验证源目录和目标目录是否有效"""
    if not os.path.isdir(src_dir):
        return False, f"源目录不存在: {src_dir}"
    
    if not os.path.isdir(dest_dir):
        return False, f"目标目录不存在: {dest_dir}"
    
    # 检查目标目录是否是源目录或其子目录
    src_real = os.path.realpath(src_dir)
    dest_real = os.path.realpath(dest_dir)
    if dest_real.startswith(src_real):
        return False, "错误：不能将备份保存到源目录或其子目录下"
    
    return True, "目录验证通过"

def should_skip_file(filename: str, filter_images: bool, filter_nfo: bool) -> bool:
    """判断是否应该跳过文件"""
    ext = os.path.splitext(filename.lower())[1]
    
    if filter_images and ext in IMAGE_EXTENSIONS:
        return True
    
    if filter_nfo and ext == '.nfo':
        return True
    
    return False

def backup_directory(src_dir: str, dest_dir: str, backed_up: Set[str], 
                     filter_images: bool = True, filter_nfo: bool = False,
                     progress_callback = None) -> Tuple[int, int, List[str]]:
    """
    备份目录
    
    Args:
        src_dir: 源目录
        dest_dir: 目标目录
        backed_up: 已备份文件集合
        filter_images: 是否过滤图片
        filter_nfo: 是否过滤nfo文件
        progress_callback: 进度回调函数，接收日志信息
    
    Returns:
        备份数量、跳过数量、日志列表
    """
    logs = []
    num_backed_up = 0
    num_skipped = 0
    
    try:
        for dirpath, dirnames, filenames in os.walk(src_dir):
            # 创建目标目录中对应的目录
            dest_path = dirpath.replace(src_dir, dest_dir)
            try:
                if not os.path.exists(dest_path):
                    os.makedirs(dest_path, exist_ok=True)
                    msg = f"创建目录: {dest_path}"
                    logs.append(msg)
                    if progress_callback:
                        progress_callback(msg)
            except Exception as e:
                msg = f"创建目录 {dest_path} 时出错: {str(e)}"
                logs.append(msg)
                if progress_callback:
                    progress_callback(msg)
                continue
            
            # 处理文件
            for filename in filenames:
                # 检查是否需要过滤
                if should_skip_file(filename, filter_images, filter_nfo):
                    msg = f"过滤文件: {filename}"
                    logs.append(msg)
                    if progress_callback:
                        progress_callback(msg)
                    num_skipped += 1
                    continue
                
                src_file = os.path.join(dirpath, filename)
                if src_file in backed_up:
                    msg = f"已备份，跳过: {src_file}"
                    logs.append(msg)
                    if progress_callback:
                        progress_callback(msg)
                    num_skipped += 1
                    continue
                
                dest_file = os.path.join(dest_path, filename)
                try:
                    # 创建1KB大小的文件
                    with open(dest_file, 'w', encoding='utf-8') as f:
                        f.write(' ' * 1024)
                    
                    backed_up.add(src_file)
                    num_backed_up += 1
                    msg = f"已备份 {num_backed_up} 个文件，跳过 {num_skipped} 个文件: {filename}"
                    logs.append(msg)
                    if progress_callback:
                        progress_callback(msg)
                except Exception as e:
                    msg = f"创建文件 {dest_file} 时出错: {str(e)}"
                    logs.append(msg)
                    if progress_callback:
                        progress_callback(msg)
    
    except Exception as e:
        msg = f"备份过程出错: {str(e)}"
        logs.append(msg)
        if progress_callback:
            progress_callback(msg)
    
    return num_backed_up, num_skipped, logs
