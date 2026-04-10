"""
Auto-updater for Agent Helper.
Checks GitHub Releases for a newer version, downloads zip, and replaces the exe.
"""

import json
import sys
import subprocess
import tempfile
import zipfile
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
                name = asset['name'].lower()
                # Prefer .zip, fall back to .exe
                if name.endswith('.zip'):
                    result['download_url'] = asset['url']
                    result['download_name'] = asset['name']
                    result['download_size'] = asset['size']
                    break
                if name.endswith('.exe') and 'download_url' not in result:
                    result['download_url'] = asset['url']
                    result['download_name'] = asset['name']
                    result['download_size'] = asset['size']
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


def download_and_apply(download_url, github_token="", progress_cb=None,
                       expected_size=0, download_name=""):
    """Download the update (zip or exe), add Defender exclusion, and schedule swap.
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
        import os

        _token = github_token
        is_zip = download_name.lower().endswith('.zip')

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

        # Download to temp
        suffix = '.zip' if is_zip else '.exe'
        tmp = Path(tempfile.gettempdir()) / f"AgentHelper_update{suffix}"
        with opener.open(req, timeout=180) as resp:
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

        # Verify download size
        if expected_size and tmp.stat().st_size != expected_size:
            return False, f"Size mismatch: got {tmp.stat().st_size}, expected {expected_size}"

        # If zip, extract the exe from it
        new_exe = tmp
        if is_zip:
            with zipfile.ZipFile(tmp, 'r') as zf:
                exe_names = [n for n in zf.namelist() if n.lower().endswith('.exe')]
                if not exe_names:
                    return False, "No .exe found in update zip"
                new_exe = Path(tempfile.gettempdir()) / "AgentHelper_update.exe"
                with zf.open(exe_names[0]) as src, open(new_exe, 'wb') as dst:
                    dst.write(src.read())

        # Add Defender exclusion for the exe folder (suppress errors if not admin)
        exe_dir = str(exe_path.parent)
        try:
            subprocess.run(
                ['powershell.exe', '-WindowStyle', 'Hidden', '-Command',
                 f'Add-MpPreference -ExclusionPath \'{exe_dir}\' -ErrorAction SilentlyContinue'],
                creationflags=0x08000000, timeout=10
            )
        except Exception:
            pass  # Not admin — that's fine

        # PowerShell launcher: Wait-Process → copy → relaunch
        pid = os.getpid()
        new_ver = get_current_version()
        ps1 = Path(tempfile.gettempdir()) / "agenthelper_update.ps1"
        ps1.write_text(
            f'Wait-Process -Id {pid} -ErrorAction SilentlyContinue\n'
            f'Start-Sleep -Seconds 5\n'
            f'Copy-Item -Force \'{new_exe}\' \'{exe_path}\'\n'
            f'Remove-Item -Force \'{new_exe}\' -ErrorAction SilentlyContinue\n'
            f'Remove-Item -Force \'{tmp}\' -ErrorAction SilentlyContinue\n'
            f'Start-Process \'{exe_path}\' -ArgumentList \'--updated {new_ver}\' -WorkingDirectory \'{exe_dir}\'\n'
            f'Remove-Item -Force $MyInvocation.MyCommand.Path -ErrorAction SilentlyContinue\n',
            encoding='utf-8'
        )
        subprocess.Popen(
            ['powershell.exe', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', str(ps1)],
            creationflags=0x08000000
        )
        return True, ""
    except Exception as e:
        return False, str(e)
