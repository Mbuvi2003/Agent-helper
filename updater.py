"""
Auto-updater for Agent Helper.
Checks GitHub Releases for a newer version, downloads, and replaces the exe.
"""

import json
import sys
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

REPO_OWNER = "Mbuvi2003"
REPO_NAME = "Agent-helper"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"


def _get_exe_path():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable)
    return None


def _get_settings_path():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "data" / "settings.json"
    return Path.cwd() / "data" / "settings.json"


def get_current_version():
    try:
        with open(_get_settings_path(), 'r', encoding='utf-8') as f:
            return json.load(f).get('version', '0.0.0')
    except Exception:
        return '0.0.0'


def _ver(v):
    try:
        return tuple(int(x) for x in v.strip().lstrip('v').split('.'))
    except Exception:
        return (0, 0, 0)


def check_for_update(github_token=""):
    """Returns dict: {available, latest_version, download_url, notes, error}."""
    result = {
        'available': False,
        'latest_version': '',
        'download_url': '',
        'notes': '',
        'error': '',
    }
    try:
        req = Request(
            API_URL,
            headers={
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'AgentHelper',
            },
        )
        if github_token:
            req.add_header('Authorization', f'token {github_token}')
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = data.get('tag_name', '').lstrip('v')
        if _ver(tag) > _ver(get_current_version()):
            result['available'] = True
            result['latest_version'] = tag
            result['notes'] = data.get('body', '')
            for asset in data.get('assets', []):
                if asset['name'].lower().endswith('.exe'):
                    result['download_url'] = asset['browser_download_url']
                    break
    except HTTPError as e:
        if e.code == 401:
            result['error'] = 'auth'  # bad/expired token
        elif e.code == 404:
            result['error'] = 'notfound'  # wrong repo or no releases yet
        else:
            result['error'] = f'http_{e.code}'
    except URLError:
        result['error'] = 'offline'
    except Exception as e:
        result['error'] = str(e)
    return result


def download_and_apply(download_url, github_token="", progress_cb=None):
    """Download the new exe and schedule replacement via a batch script."""
    exe_path = _get_exe_path()
    if not exe_path:
        return False
    try:
        req = Request(
            download_url,
            headers={
                'Accept': 'application/octet-stream',
                'User-Agent': 'AgentHelper',
            },
        )
        if github_token:
            req.add_header('Authorization', f'token {github_token}')
        tmp = Path(tempfile.gettempdir()) / "AgentHelper_update.exe"
        with urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            done = 0
            with open(tmp, 'wb') as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb and total:
                        progress_cb(done, total)
        # Batch script waits for this process to exit, then replaces exe and restarts
        bat = Path(tempfile.gettempdir()) / "agenthelper_update.bat"
        bat.write_text(
            f'@echo off\n'
            f'timeout /t 2 /nobreak >nul\n'
            f'copy /y "{tmp}" "{exe_path}"\n'
            f'del "{tmp}"\n'
            f'start "" "{exe_path}"\n'
            f'del "%~f0"\n'
        )
        subprocess.Popen(['cmd', '/c', str(bat)], creationflags=0x08000000)
        return True
    except Exception:
        return False
