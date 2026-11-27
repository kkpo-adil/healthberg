"""An isolated local server and real browser; no external service or personal data."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture
def browser_session(tmp_path_factory):
    folder=tmp_path_factory.mktemp('browser-import')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    env={**os.environ,'HEALTHBERG_DB':str(folder/'demo.sqlite3'),'HEALTHBERG_ENABLE_REAL_PATIENTS':'false'}
    with (folder/'server.log').open('w+') as log:
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],
                              cwd=Path(__file__).resolve().parents[2],env=env,stdout=log,stderr=log)
        try:
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if proc.poll() is not None:break
                try:
                    with urllib.request.urlopen(origin+'/api/health',timeout=1):break
                except (OSError,TimeoutError):time.sleep(.1)
            else:raise AssertionError('Server startup timed out')
            if proc.poll() is not None:
                log.seek(0);raise AssertionError(log.read())
            with sync_playwright() as pw:
                browser_type=getattr(pw,os.getenv('AJOUR_TEST_BROWSER','chromium'))
                browser=browser_type.launch(executable_path=os.getenv('AJOUR_TEST_CHROMIUM') or None)
                try:yield browser,origin
                finally:browser.close()
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
