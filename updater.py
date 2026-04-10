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

# Fallback token embedded in the exe (read-only, releases scope only).
# This means the updater always works even if settings.json loses the token.
_FALLBACK_TOKEN = "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"


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
    if not github_token:
        github_token = _FALLBACK_TOKEN
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
                    # Use API url (not browser_download_url) for private-repo downloads.
                    # GET api.github.com/...assets/{id} with Accept:octet-stream → 302 → S3.
                    result['download_url'] = asset['url']
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
    """Download the new exe and schedule replacement via a batch script.
    Returns (True, "") on success or (False, error_message) on failure.
    """
    if not github_token:
        github_token = _FALLBACK_TOKEN
    exe_path = _get_exe_path()
    if not exe_path:
        return False, "Not running as a packaged exe"
    try:
        import urllib.request
        import urllib.parse

        _token = github_token

        class _AuthRedirectHandler(urllib.request.HTTPRedirectHandler):
            """Strip Authorization when redirecting to a different domain."""
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                orig_host = urllib.parse.urlparse(req.full_url).netloc
                new_host = urllib.parse.urlparse(newurl).netloc
                new_req = urllib.request.Request(
                    newurl,
                    headers={
                        'User-Agent': 'AgentHelper',
                        'Accept': 'application/octet-stream',
                    },
                )
                if new_host == orig_host:
                    new_req.add_header('Authorization', f'token {_token}')
                return new_req

        opener = urllib.request.build_opener(_AuthRedirectHandler())
        req = urllib.request.Request(
            download_url,
            headers={
                'Accept': 'application/octet-stream',
                'User-Agent': 'AgentHelper',
                'Authorization': f'token {_token}',
            },
        )
        tmp = Path(tempfile.gettempdir()) / "AgentHelper_update.exe"
        with opener.open(req, timeout=120) as resp:
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
        # Batch script polls until the old PID exits (PyInstaller temp fully cleaned),
        # then replaces the exe and restarts it with --updated so the app shows
        # a success notification.
        import os
        pid = os.getpid()
        new_ver = get_current_version()
        exe_dir = str(exe_path.parent)
        bat = Path(tempfile.gettempdir()) / "agenthelper_update.bat"
        bat.write_text(
            f'@echo off\n'
            f':WAIT\n'
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\n'
            f'if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto WAIT)\n'
            f'timeout /t 2 /nobreak >nul\n'
            f'copy /y "{tmp}" "{exe_path}"\n'
            f'del "{tmp}"\n'
            f'start "" /D "{exe_dir}" "{exe_path}" --updated {new_ver}\n'
            f'del "%~f0"\n'
        )
        subprocess.Popen(['cmd', '/c', str(bat)], creationflags=0x08000000)
        return True, ""
    except Exception as e:
        return False, str(e)
