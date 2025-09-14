import sqlite3
from datetime import datetime

class SQLiteLogger:
    def __init__(self, db_path='logs.db'):
        """DBに接続し、テーブルがなければ作成する"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        """logsテーブルを作成する"""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                username TEXT,
                room_name TEXT,
                details TEXT,
                client_ip TEXT
            )
        ''')
        self.conn.commit()

    def log(self, event_type, username=None, room_name=None, details=None, client_ip=None):
        """ログをDBに挿入する"""
        cursor = self.conn.cursor()
        # SQLインジェクションを防ぐため、プレースホルダ(?)を使用
        cursor.execute('''
            INSERT INTO logs (event_type, username, room_name, details, client_ip)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_type, username, room_name, details, str(client_ip)))
        self.conn.commit()

    def close(self):
        """DB接続を閉じる"""
        self.conn.close()