from pathlib import Path
import subprocess, sys, os
import daemon_process
import logging

LOG_FILE = Path(__file__).resolve().parent / "logs" / "daemon.log"
DAEMON_SCRIPT = Path(daemon_process.__file__).resolve()
log = logging.getLogger("gabriel.launcher")

class LinuxLauncher():

    @staticmethod
    def launch_daemon() -> int:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Pipe so the grandchild can send its PID back to us before we return.
        r_fd, w_fd = os.pipe()

        pid = os.fork()  # ── FORK 1 ──────────────────────────────────────────
        if pid > 0:
            # ── Parent: wait for intermediate child, then read grandchild PID ──
            os.close(w_fd)
            os.waitpid(pid, 0)                      # reap intermediate child
            raw = os.read(r_fd, 32).decode().strip()
            os.close(r_fd)
            daemon_pid = int(raw)
            log.info(f"Daemon launched. PID={daemon_pid}")
            return daemon_pid

        # ── Intermediate child ───────────────────────────────────────────────
        os.close(r_fd)
        os.setsid()                                 # new session, detach from terminal

        pid2 = os.fork()  # ── FORK 2 ─────────────────────────────────────────
        if pid2 > 0:
            # Intermediate child writes grandchild PID then exits immediately.
            os.write(w_fd, str(pid2).encode())
            os.close(w_fd)
            os._exit(0)                             # do NOT run atexit handlers

        # ── Grandchild: the actual daemon process ────────────────────────────
        os.close(w_fd)

        # Redirect stdin/stdout/stderr
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, sys.stdin.fileno())
        os.close(devnull)

        log_fd = os.open(
            str(LOG_FILE),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o644,
        )
        os.dup2(log_fd, sys.stdout.fileno())
        os.dup2(log_fd, sys.stderr.fileno())
        os.close(log_fd)

        # Change working directory so we don't hold a mount point open
        os.chdir("/")

        # Clear umask so the daemon controls its own file permissions
        os.umask(0)

        # Replace this process image with the daemon script
        os.execv(
            sys.executable,
            [sys.executable, str(DAEMON_SCRIPT)],
        )
        # execv never returns — if it does, something went wrong
        sys._exit(1)

class WindowsLauncher():

    @staticmethod
    def launch_daemon():
        """Spawn daemon.py as a fully detached Windows process."""
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        python = sys.executable
        
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        
        proc = subprocess.Popen(
            [python, str(DAEMON_SCRIPT)],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        return proc.pid


def launch_daemon():
    if sys.platform.startswith("win"):
        return WindowsLauncher.launch_daemon()
    return LinuxLauncher.launch_daemon()
