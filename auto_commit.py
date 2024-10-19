import os
import subprocess
from datetime import datetime
import json
import requests

def get_git_diff():
    try:
        # 尝试使用 UTF-8 解码
        return subprocess.check_output(['git', 'diff'], stderr=subprocess.STDOUT).decode('utf-8')
    except UnicodeDecodeError:
        # 如果 UTF-8 解码失败，尝试使用 'latin-1' 编码
        return subprocess.check_output(['git', 'diff'], stderr=subprocess.STDOUT).decode('latin-1')

def generate_commit_message_with_ollama(diff):
    api_url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "qwen2.5:14b",
        "prompt": f"根据以下Git差异生成一个简洁的commit消息，遵循Conventional Commits规范：\n\n{diff}\n\nCommit消息："
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()  # 如果请求失败，这将引发异常
        return response.json()['response'].strip()
    except requests.RequestException as e:
        print(f"调用Ollama API时出错: {e}")
        return "feat: 自动生成的提交"
def generate_commit_message_with_ollama(diff):
    api_url = "http://localhost:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "qwen2.5:14b",
        "prompt": f"根据以下Git差异生成一个简洁的commit消息，遵循Conventional Commits规范：\n\n{diff}\n\nCommit消息："
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, stream=True)
        response.raise_for_status()
        
        full_response = ""
        for line in response.iter_lines():
            if line:
                try:
                    json_line = json.loads(line)
                    if 'response' in json_line:
                        full_response += json_line['response']
                except json.JSONDecodeError:
                    print(f"无法解析JSON行: {line}")
        
        return full_response.strip()
    except requests.RequestException as e:
        print(f"调用Ollama API时出错: {e}")
        return "feat: 自动生成的提交"
def git_auto_commit():
    # 切换到Git仓库目录
    os.chdir('./')
    
    # 检查是否有变更
    try:
        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"执行git status时出错: {e}")
        return
    
    if status.stdout:
        # 获取差异
        diff = get_git_diff()
        
        # 使用Ollama生成commit消息
        commit_message = generate_commit_message_with_ollama(diff)
        
        # 添加时间戳到commit消息
        commit_message += f"\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            # 有变更,执行add
            subprocess.run(['git', 'add', '.'], check=True)
            
            # 执行commit
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            
            print("已完成自动提交，commit消息：\n", commit_message)
        except subprocess.CalledProcessError as e:
            print(f"执行git命令时出错: {e}")
    else:
        print("没有检测到变更,无需提交")

if __name__ == '__main__':
    git_auto_commit()
