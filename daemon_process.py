# daemon_process.py
import os, sys, logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from daemon.pid_lock import write_lock, clear_lock, get_running_daemon, DAEMON_PORT, _PROJECT_ROOT, LOCK_FILE
from daemon.daemon import create_app
import uvicorn

LOG_FILE = _PROJECT_ROOT / "logs" / "daemon.log"

def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler(sys.stdout)],
    )

def main():
    setup_logging()
    log = logging.getLogger("gabriel.daemon")

    if get_running_daemon():
        log.warning("Daemon already running. Exiting.")
        sys.exit(0)

    write_lock(os.getpid(), DAEMON_PORT)
    log.info(f"Lock written to: {LOCK_FILE}")
    log.info(f"Daemon process started. PID={os.getpid()}, port={DAEMON_PORT}")

    try:
        app = create_app()

        @asynccontextmanager
        async def lifespan(app):
            app.state.daemon.start()
            log.info("Daemon thread started automatically on process startup.")
            yield

            #Add shutdown logic if needed

        app.router.lifespan_context = lifespan

        uvicorn.run(app, host="127.0.0.1", port=DAEMON_PORT, log_level="info")
    finally:
        clear_lock()
        log.info("Daemon process stopped. Lock cleared.")

if __name__ == "__main__":
    main()