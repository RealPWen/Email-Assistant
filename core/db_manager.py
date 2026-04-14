import sqlite3
import os

class DBManager:
    def __init__(self, db_path=None):
        # 默认存储在项目根目录的 data 文件夹下
        if db_path is None:
            # 获取项目根目录 (即 core 目录的上一级)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "data", "emails.db")
        else:
            self.db_path = db_path
            
        # 确保 data 目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库和表结构，并处理版本升级"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 创建基础邮件表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE,
                    subject TEXT,
                    sender TEXT,
                    date_str TEXT,
                    body TEXT,
                    folder TEXT DEFAULT 'INBOX',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 2. 版本升级 (增加新列)
            columns = [
                ("is_read", "INTEGER DEFAULT 0"),
                ("normalized_date", "TEXT"),
                ("attachments_metadata", "TEXT"),  # 存储 JSON 字符串
                ("body_translation", "TEXT"),       # 存储正文翻译内容
                ("summary", "TEXT"),                # AI 摘要内容
                ("action_items", "TEXT"),           # AI 提取的行动项 (JSON)
                ("importance", "TEXT"),             # AI 判定的重要性
                ("category", "TEXT DEFAULT '其他'"),   # AI 判定的分类
                ("reason", "TEXT")                  # AI 判定的原因
            ]
            
            for col_name, col_type in columns:
                cursor.execute(f"PRAGMA table_info(emails)")
                current_columns = [row[1] for row in cursor.fetchall()]
                if col_name not in current_columns:
                    print(f"🔧 正在升级数据库: 添加列 {col_name}...")
                    cursor.execute(f"ALTER TABLE emails ADD COLUMN {col_name} {col_type}")

            # 3. 创建待办事项表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER,
                    title TEXT,
                    content TEXT,
                    priority TEXT DEFAULT 'Normal',
                    due_date TEXT,
                    status INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email_id) REFERENCES emails(id)
                )
            ''')
            
            # 4. 创建 prompt_templates 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prompt_templates (
                    skill_name TEXT PRIMARY KEY,
                    system_prompt TEXT,
                    default_system_prompt TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 插入默认 prompts
            try:
                from core.default_prompts import DEFAULT_PROMPTS
                for skill_name, default_prompt in DEFAULT_PROMPTS.items():
                    cursor.execute('SELECT 1 FROM prompt_templates WHERE skill_name = ?', (skill_name,))
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO prompt_templates (skill_name, system_prompt, default_system_prompt)
                            VALUES (?, ?, ?)
                        ''', (skill_name, default_prompt, default_prompt))
            except Exception as e:
                print(f"⚠️ 初始化默认 Prompt 失败: {e}")
            
            conn.commit()

    def get_connection(self):
        """获取数据库连接对象，默认开启 Row 模式并启用 WAL 模式"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # 开启 WAL 模式提高并发性能 (多读一写)
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def save_email(self, email_data):
        """保存单封邮件到数据库"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO emails (message_id, subject, sender, date_str, body, folder, is_read, normalized_date, attachments_metadata, body_translation, summary, action_items, importance, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    email_data.get('message_id'),
                    email_data.get('subject'),
                    email_data.get('sender'),
                    email_data.get('date_str'),
                    email_data.get('body'),
                    email_data.get('folder', 'INBOX'),
                    email_data.get('is_read', 0),
                    email_data.get('normalized_date'),
                    email_data.get('attachments_metadata'),
                    email_data.get('body_translation'),
                    email_data.get('summary'),
                    email_data.get('action_items'),
                    email_data.get('importance'),
                    email_data.get('category', '其他')
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def update_email_status(self, message_id, is_read):
        """更新邮件的已读/未读状态"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE emails SET is_read = ? WHERE message_id = ?
            ''', (is_read, message_id))
            conn.commit()

    def exists(self, message_id):
        """检查 Message-ID 是否已存在于数据库中"""
        if not message_id:
            return False
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM emails WHERE message_id = ? LIMIT 1', (message_id,))
            return cursor.fetchone() is not None

    def get_all_emails(self, limit=500):
        """获取数据库中的最近邮件"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, message_id, subject, sender, normalized_date, importance, is_read, summary, category 
                FROM emails 
                ORDER BY normalized_date DESC, id DESC 
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return rows

    def get_email_by_id(self, email_id):
        """根据 ID 获取邮件详情"""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM emails WHERE id = ?', (email_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_email_count(self):
        """获取总邮件数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM emails')
            return cursor.fetchone()[0]

    def get_untranslated_emails(self):
        """获取所有需要补全数据的邮件 (未翻译、未标准化、或未 AI 加工)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT message_id, body, date_str, normalized_date, summary, category FROM emails 
                WHERE (body_translation IS NULL OR body_translation = '') 
                OR (normalized_date IS NULL OR normalized_date = '')
                OR (summary IS NULL OR summary = '')
                OR (category IS NULL OR category = '其他')
            ''')
            rows = cursor.fetchall()
            return rows

    def update_email_metadata(self, message_id, normalized_date=None, translation=None, ai_data=None):
        """更新邮件的元数据（翻译、时间、AI 数据）"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if normalized_date:
                updates.append("normalized_date = ?")
                params.append(normalized_date)
            if translation:
                updates.append("body_translation = ?")
                params.append(translation)
            if ai_data:
                updates.append("summary = ?")
                params.append(ai_data.get('summary'))
                updates.append("action_items = ?")
                params.append(ai_data.get('action_items'))
                updates.append("importance = ?")
                params.append(ai_data.get('importance'))
                updates.append("category = ?")
                params.append(ai_data.get('category', '其他'))
                
            if not updates:
                return
                
            params.append(message_id)
            query = f"UPDATE emails SET {', '.join(updates)} WHERE message_id = ?"
            cursor.execute(query, params)
            conn.commit()

    # --- Todo Management Methods ---

    def add_todo(self, todo_data):
        """添加待办事项"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO todos (email_id, title, content, priority, due_date, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                todo_data.get('email_id'),
                todo_data.get('title'),
                todo_data.get('content'),
                todo_data.get('priority', 'Normal'),
                todo_data.get('due_date'),
                todo_data.get('status', 0)
            ))
            conn.commit()
            return cursor.lastrowid

    def get_all_todos(self):
        """获取所有待办事项"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM todos ORDER BY status ASC, due_date ASC, id DESC')
            return [dict(row) for row in cursor.fetchall()]

    def update_todo_status(self, todo_id, status):
        """更新待办事项状态 (0: 未完成, 1: 已完成)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE todos SET status = ? WHERE id = ?', (status, todo_id))
            conn.commit()

    def delete_todo(self, todo_id):
        """删除待办事项"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM todos WHERE id = ?', (todo_id,))
            conn.commit()

    def update_todo(self, todo_id, todo_data):
        """更新待办事项详情"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            for key in ['title', 'content', 'priority', 'due_date', 'status']:
                if key in todo_data:
                    updates.append(f"{key} = ?")
                    params.append(todo_data[key])
            
            if not updates:
                return
            
            params.append(todo_id)
            cursor.execute(f"UPDATE todos SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    # --- Prompt Management Methods ---

    def get_prompt(self, skill_name, default_fallback=""):
        """获取指定 skill 的当前 prompt"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT system_prompt FROM prompt_templates WHERE skill_name = ?', (skill_name,))
            row = cursor.fetchone()
            return row[0] if row else default_fallback

    def get_all_prompts(self):
        """获取所有 prompts 信息"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT skill_name, system_prompt, default_system_prompt, updated_at FROM prompt_templates')
            return [dict(row) for row in cursor.fetchall()]

    def update_prompt(self, skill_name, new_prompt):
        """更新指定 skill 的 prompt"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 检查是否存在
            cursor.execute('SELECT 1 FROM prompt_templates WHERE skill_name = ?', (skill_name,))
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE prompt_templates 
                    SET system_prompt = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE skill_name = ?
                ''', (new_prompt, skill_name))
            else:
                cursor.execute('''
                    INSERT INTO prompt_templates (skill_name, system_prompt, default_system_prompt)
                    VALUES (?, ?, ?)
                ''', (skill_name, new_prompt, new_prompt))
            conn.commit()

    def restore_default_prompt(self, skill_name):
        """将指定 skill 的 prompt 恢复为默认值"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE prompt_templates 
                SET system_prompt = default_system_prompt, updated_at = CURRENT_TIMESTAMP 
                WHERE skill_name = ? AND default_system_prompt IS NOT NULL
            ''', (skill_name,))
            conn.commit()
