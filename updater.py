"""
Auto-updater for Agent Helper.
Checks GitHub Releases for a newer version, downloads zip, and replaces the app folder.

With --onedir builds there is NO runtime DLL extraction — all files are already
on disk, so Windows Defender never flags anything.
"""

import json
import sys
import subprocess
import tempfile
import zipfile
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

REPO_OWNER = "Mbuvi2003"
REPO_NAME = "Agent-helper"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

# Fallback token embedded in the exe (read-only, releases scope only).
_FALLBACK_TOKEN = "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"


def _get_app_dir():
    """Return the directory containing the running exe (the --onedir output folder)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
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
    """Returns dict with update info."""
    if not github_token:
        github_token = _FALLBACK_TOKEN
    result = {
        'available': False,
        'latest_version': '',
        'download_url': '',
        'download_name': '',
        'download_size': 0,
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
                if asset['name'].lower().endswith('.zip'):
                    result['download_url'] = asset['url']
                    result['download_name'] = asset['name']
                    result['download_size'] = asset['size']
                    break
    except HTTPError as e:
        if e.code == 401:
            result['error'] = 'auth'
        elif e.code == 404:
            result['error'] = 'notfound'
        else:
            result['error'] = f'http_{e.code}'
    except URLError:
        result['error'] = 'offline'
    except Exception as e:
        result['error'] = str(e)
    return result


def download_and_apply(download_url, github_token="", progress_cb=None,
                       expected_size=0, download_name=""):
    """Download the update zip and schedule a full folder replacement.

    The zip contains the entire --onedir output (AgentHelper/ folder with exe + DLLs).
    A PowerShell script waits for this process to exit, swaps folders, and relaunches.

    Returns (True, "") on success or (False, error_message) on failure.
    """
    if not github_token:
        github_token = _FALLBACK_TOKEN
    app_dir = _get_app_dir()
    if not app_dir:
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

        # Download zip to temp
        tmp_zip = Path(tempfile.gettempdir()) / "AgentHelper_update.zip"
        with opener.open(req, timeout=180) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            done = 0
            with open(tmp_zip, 'wb') as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb and total:
                        progress_cb(done, total)

        # Verify download size
        if expected_size and tmp_zip.stat().st_size != expected_size:
            return False, f"Size mismatch: got {tmp_zip.stat().st_size}, expected {expected_size}"

        # Extract zip to a temp staging folder
        staging = Path(tempfile.gettempdir()) / "AgentHelper_staging"
        if staging.exists():
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            zf.extractall(staging)

        # Find the extracted folder containing AgentHelper.exe
        extracted_exe = None
        for root, dirs, files in os.walk(staging):
            for f in files:
                if f.lower() == 'agenthelper.exe':
                    extracted_exe = Path(root) / f
                    break
            if extracted_exe:
                break

        if not extracted_exe:
            return False, "No AgentHelper.exe found in update zip"

        new_app_dir = extracted_exe.parent

        # Build PowerShell update script:
        # 1. Wait for current process to fully exit
        # 2. Remove old app files (keep data/ and images/ for user settings)
        # 3. Copy new files in
        # 4. Relaunch with --updated flag
        pid = os.getpid()
        exe_name = Path(sys.executable).name
        exe_path = app_dir / exe_name
        ps1 = Path(tempfile.gettempdir()) / "agenthelper_update.ps1"
        ps1.write_text(
            f'Wait-Process -Id {pid} -ErrorAction SilentlyContinue\n'
            f'Start-Sleep -Seconds 3\n'
            f'\n'
            f'$appDir = \'{app_dir}\'\n'
            f'$newDir = \'{new_app_dir}\'\n'
            f'$exe    = \'{exe_path}\'\n'
            f'\n'
            f'# Remove old files EXCEPT data/ and images/ (user settings)\n'
            f'Get-ChildItem $appDir -Exclude data,images | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue\n'
            f'\n'
            f'# Copy all new files into app dir\n'
            f'Get-ChildItem $newDir | Copy-Item -Destination $appDir -Recurse -Force\n'
            f'\n'
            f'# Clean up staging\n'
            f'Remove-Item -Recurse -Force \'{staging}\' -ErrorAction SilentlyContinue\n'
            f'Remove-Item -Force \'{tmp_zip}\' -ErrorAction SilentlyContinue\n'
            f'\n'
            f'# Relaunch\n'
            f'Start-Process $exe -ArgumentList \'--updated\' -WorkingDirectory $appDir\n'
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
