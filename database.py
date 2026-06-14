import sqlite3
from pathlib import Path


APP_DIR = Path.home() / ".local" / "share" / "openlauncher"
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DIR / "apps.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cur = self.conn.cursor()

    def init_db(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                command TEXT NOT NULL,
                uses INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def add_app(self, name, command):
        self.cur.execute("""
            INSERT INTO apps(name, command)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET command = excluded.command
        """, (name, command))
        self.conn.commit()

    def search_apps(self, query):
        self.cur.execute("""
            SELECT id, name, command
            FROM apps
            WHERE name LIKE ?
            ORDER BY uses DESC, name ASC
            LIMIT 8
        """, (f"%{query}%",))

        return self.cur.fetchall()
    
    def get_all_apps(self):
        self.cur.execute("""
            SELECT id, name, command
              FROM apps
          ORDER BY uses DESC, name ASC
        """)
        
        return self.cur.fetchall()
    
    def increase_usage(self, app_id):
        self.cur.execute("""
            UPDATE apps
            SET uses = uses + 1
            WHERE id = ?
        """, (app_id,))
        self.conn.commit()

    def delete_app(self, name):
        self.cur.execute("""
            DELETE FROM apps
            WHERE name = ?
        """, (name,))
        self.conn.commit()

        return self.cur.rowcount
