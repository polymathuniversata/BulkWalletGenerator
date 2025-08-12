import os
import subprocess
import sys
import time
from pathlib import Path

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

PROJECT_ROOT = Path(__file__).parent.resolve()
WATCH_DIRS = [PROJECT_ROOT / "src", PROJECT_ROOT]
PATTERNS = ["*.py", "*.env", "*.md"]
IGNORE_DIRS = {"venv", ".git", "__pycache__"}


class RestartOnChangeHandler(PatternMatchingEventHandler):
    def __init__(self, restart_cb):
        super().__init__(patterns=PATTERNS, ignore_directories=False, case_sensitive=False)
        self._restart_cb = restart_cb

    def on_any_event(self, event):
        # Ignore changes inside ignored directories
        p = Path(event.src_path)
        for part in p.parts:
            if part in IGNORE_DIRS:
                return
        self._restart_cb(reason=f"{event.event_type}: {p}")


def run_bot() -> subprocess.Popen:
    env = os.environ.copy()
    # Ensure stdout/err are unbuffered for immediate logs
    return subprocess.Popen([sys.executable, "-m", "src.bot"], cwd=str(PROJECT_ROOT), env=env)


def main():
    print("[watchdog] Starting dev runner with autoreload...")
    proc = run_bot()

    def restart(reason: str):
        nonlocal proc
        print(f"[watchdog] Change detected ({reason}). Restarting bot...")
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                # Give it a moment to terminate gracefully
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as e:
            print(f"[watchdog] Error terminating process: {e}")
        proc = run_bot()

    observer = Observer()
    handler = RestartOnChangeHandler(restart)
    for d in WATCH_DIRS:
        observer.schedule(handler, str(d), recursive=True)
        print(f"[watchdog] Watching: {d}")

    observer.start()
    try:
        while True:
            time.sleep(1)
            # If the process died (e.g., crash), restart automatically
            if proc and proc.poll() is not None:
                print("[watchdog] Bot process exited, restarting...")
                proc = run_bot()
    except KeyboardInterrupt:
        print("[watchdog] Shutting down...")
    finally:
        observer.stop()
        observer.join()
        try:
            if proc and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=3)
        except Exception:
            pass


if __name__ == "__main__":
    main()
