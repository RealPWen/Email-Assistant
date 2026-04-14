import sqlite3
import os


class DBManager:
    def __init__(self, db_path=None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "data", "emails.db")
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _execute(self, query, params=(), fetch=None, commit=False):
        """通用执行入口，减少重复的 connection/cursor 模板代码。"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if fetch == 'one':
                return cursor.fetchone()
            if fetch == 'all':
                return cursor.fetchall()
            if commit:
                conn.commit()
            return cursor

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE, subject TEXT, sender TEXT,
                    date_str TEXT, body TEXT, folder TEXT DEFAULT 'INBOX',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 版本升级：批量检测并添加缺失列（只查询一次 PRAGMA）
            cursor.execute("PRAGMA table_info(emails)")
            existing = {row[1] for row in cursor.fetchall()}
            for col_name, col_type in [
                ("is_read", "INTEGER DEFAULT 0"), ("normalized_date", "TEXT"),
                ("attachments_metadata", "TEXT"), ("body_translation", "TEXT"),
                ("summary", "TEXT"), ("action_items", "TEXT"),
                ("importance", "TEXT"), ("category", "TEXT DEFAULT '其他'"),
                ("reason", "TEXT"),
            ]:
                if col_name not in existing:
                    print(f"🔧 正在升级数据库: 添加列 {col_name}...")
                    cursor.execute(f"ALTER TABLE emails ADD COLUMN {col_name} {col_type}")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER, title TEXT, content TEXT,
                    priority TEXT DEFAULT 'Normal', due_date TEXT,
                    status INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email_id) REFERENCES emails(id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prompt_templates (
                    skill_name TEXT PRIMARY KEY, system_prompt TEXT,
                    default_system_prompt TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            try:
                from core.default_prompts import DEFAULT_PROMPTS
                for skill_name, default_prompt in DEFAULT_PROMPTS.items():
                    if not cursor.execute('SELECT 1 FROM prompt_templates WHERE skill_name = ?', (skill_name,)).fetchone():
                        cursor.execute(
                            'INSERT INTO prompt_templates (skill_name, system_prompt, default_system_prompt) VALUES (?, ?, ?)',
                            (skill_name, default_prompt, default_prompt)
                        )
            except Exception as e:
                print(f"⚠️ 初始化默认 Prompt 失败: {e}")

            conn.commit()

    # --- Email Methods ---

    _EMAIL_FIELDS = [
        'message_id', 'subject', 'sender', 'date_str', 'body', 'folder',
        'is_read', 'normalized_date', 'attachments_metadata', 'body_translation',
        'summary', 'action_items', 'importance', 'category',
    ]
    _EMAIL_DEFAULTS = {'folder': 'INBOX', 'is_read': 0, 'category': '其他'}

    def save_email(self, email_data):
        vals = [email_data.get(f, self._EMAIL_DEFAULTS.get(f)) for f in self._EMAIL_FIELDS]
        placeholders = ','.join(['?'] * len(self._EMAIL_FIELDS))
        cols = ','.join(self._EMAIL_FIELDS)
        with self.get_connection() as conn:
            try:
                conn.execute(f"INSERT INTO emails ({cols}) VALUES ({placeholders})", vals)
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def update_email_status(self, message_id, is_read):
        self._execute('UPDATE emails SET is_read = ? WHERE message_id = ?', (is_read, message_id), commit=True)

    def exists(self, message_id):
        if not message_id:
            return False
        return self._execute('SELECT 1 FROM emails WHERE message_id = ? LIMIT 1', (message_id,), fetch='one') is not None

    def get_all_emails(self, limit=500):
        return self._execute(
            'SELECT id, message_id, subject, sender, normalized_date, importance, is_read, summary, category '
            'FROM emails ORDER BY normalized_date DESC, id DESC LIMIT ?',
            (limit,), fetch='all'
        )

    def get_email_by_id(self, email_id):
        row = self._execute('SELECT * FROM emails WHERE id = ?', (email_id,), fetch='one')
        return dict(row) if row else None

    def get_email_count(self):
        return self._execute('SELECT COUNT(*) FROM emails', fetch='one')[0]

    def get_unread_count(self):
        return self._execute('SELECT COUNT(*) FROM emails WHERE is_read = 0', fetch='one')[0]

    def get_important_count(self):
        return self._execute('SELECT COUNT(*) FROM emails WHERE importance = "高"', fetch='one')[0]

    def get_untranslated_emails(self):
        return self._execute('''
            SELECT message_id, body, date_str, normalized_date, summary, category FROM emails
            WHERE (body_translation IS NULL OR body_translation = '')
               OR (normalized_date IS NULL OR normalized_date = '')
               OR (summary IS NULL OR summary = '')
               OR (category IS NULL OR category = '其他')
        ''', fetch='all')

    def update_email_metadata(self, message_id, normalized_date=None, translation=None, ai_data=None):
        updates, params = [], []
        if normalized_date:
            updates.append("normalized_date = ?"); params.append(normalized_date)
        if translation:
            updates.append("body_translation = ?"); params.append(translation)
        if ai_data:
            for key in ('summary', 'action_items', 'importance'):
                updates.append(f"{key} = ?"); params.append(ai_data.get(key))
            updates.append("category = ?"); params.append(ai_data.get('category', '其他'))
        if not updates:
            return
        params.append(message_id)
        self._execute(f"UPDATE emails SET {', '.join(updates)} WHERE message_id = ?", params, commit=True)

    # --- Todo Methods ---

    def add_todo(self, data):
        cursor = self._execute(
            'INSERT INTO todos (email_id, title, content, priority, due_date, status) VALUES (?, ?, ?, ?, ?, ?)',
            (data.get('email_id'), data.get('title'), data.get('content'),
             data.get('priority', 'Normal'), data.get('due_date'), data.get('status', 0)),
            commit=True
        )
        return cursor.lastrowid

    def get_all_todos(self):
        rows = self._execute('SELECT * FROM todos ORDER BY status ASC, due_date ASC, id DESC', fetch='all')
        return [dict(r) for r in rows]

    def update_todo_status(self, todo_id, status):
        self._execute('UPDATE todos SET status = ? WHERE id = ?', (status, todo_id), commit=True)

    def delete_todo(self, todo_id):
        self._execute('DELETE FROM todos WHERE id = ?', (todo_id,), commit=True)

    def update_todo(self, todo_id, todo_data):
        allowed = ['title', 'content', 'priority', 'due_date', 'status']
        updates = [f"{k} = ?" for k in allowed if k in todo_data]
        params = [todo_data[k] for k in allowed if k in todo_data]
        if not updates:
            return
        params.append(todo_id)
        self._execute(f"UPDATE todos SET {', '.join(updates)} WHERE id = ?", params, commit=True)

    # --- Prompt Methods ---

    def get_prompt(self, skill_name, default_fallback=""):
        row = self._execute('SELECT system_prompt FROM prompt_templates WHERE skill_name = ?', (skill_name,), fetch='one')
        return row[0] if row else default_fallback

    def get_all_prompts(self):
        rows = self._execute('SELECT skill_name, system_prompt, default_system_prompt, updated_at FROM prompt_templates', fetch='all')
        return [dict(r) for r in rows]

    def update_prompt(self, skill_name, new_prompt):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if cursor.execute('SELECT 1 FROM prompt_templates WHERE skill_name = ?', (skill_name,)).fetchone():
                cursor.execute(
                    'UPDATE prompt_templates SET system_prompt = ?, updated_at = CURRENT_TIMESTAMP WHERE skill_name = ?',
                    (new_prompt, skill_name)
                )
            else:
                cursor.execute(
                    'INSERT INTO prompt_templates (skill_name, system_prompt, default_system_prompt) VALUES (?, ?, ?)',
                    (skill_name, new_prompt, new_prompt)
                )
            conn.commit()

    def restore_default_prompt(self, skill_name):
        self._execute(
            'UPDATE prompt_templates SET system_prompt = default_system_prompt, updated_at = CURRENT_TIMESTAMP '
            'WHERE skill_name = ? AND default_system_prompt IS NOT NULL',
            (skill_name,), commit=True
        )
