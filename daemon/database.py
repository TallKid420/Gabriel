import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "database" / "checkpoints.sqlite"


class Database:
    def connect_sync(self) -> sqlite3.Connection:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(DB_PATH, check_same_thread=False)

class TestDatabase:
    def __init__(self):
        pass

    def connect(self):
        ... # Implement connection logic for testing, e.g., using an in-memory SQLite database