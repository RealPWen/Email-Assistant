import os
import sys

# 获取项目根目录，用于定位静态文件和数据库
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 确保项目根目录在 sys.path 中，以便导入 core 和 tools 模块
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from core.db_manager import DBManager
from core.todo_skill import TodoSkill
from tools.fetch_emails import sync_emails
import json
import asyncio
from queue import Queue
from threading import Thread

app = FastAPI(title="DeepMail AI API")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)},
    )

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DBManager()

# 挂载静态文件
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# (BASE_DIR 已在文件顶部定义)

def serve_html(filename):
    path = os.path.join(BASE_DIR, "static", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def read_index():
    return serve_html("index.html")

@app.get("/api/emails")
async def get_emails(limit: int = 500):
    """获取邮件列表"""
    rows = db.get_all_emails(limit=limit)
    return [{
        "id": row['id'],
        "message_id": row['message_id'],
        "subject": row['subject'],
        "sender": row['sender'],
        "date": row['normalized_date'],
        "importance": row['importance'],
        "is_read": row['is_read'],
        "summary": row['summary'],
        "category": row['category']
    } for row in rows]

@app.get("/api/email/{email_id}")
async def get_email_detail(email_id: int):
    """获取邮件详细内容 (原文 + 翻译 + 摘要)"""
    email = db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # 转换为字典并处理 JSON 字段
    email_dict = dict(email)
    try:
        if email_dict.get('action_items'):
            email_dict['action_items'] = json.loads(email_dict['action_items'])
    except:
        email_dict['action_items'] = []
        
    return email_dict

@app.post("/api/email/{email_id}/read")
async def mark_as_read(email_id: int, request: Request):
    """标记邮件为已读"""
    data = await request.json()
    is_read = data.get('is_read', 1)
    
    # 获取 message_id
    email = db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    db.update_email_status(email['message_id'], is_read)
    return {"status": "success", "message_id": email['message_id'], "is_read": is_read}

@app.get("/api/stats")
async def get_stats():
    """获取简单的仪表盘统计数据"""
    return {
        "total_emails": db.get_email_count(),
        "unread_emails": db.get_unread_count(),
        "important_emails": db.get_important_count()
    }

@app.get("/api/sync/progress")
def sync_progress():
    """流式返回同步进度 (SSE)"""
    def event_stream():
        q = Queue()
        
        def callback(msg):
            q.put(msg)
            
        # 在后台线程中运行同步
        thread = Thread(target=sync_emails, kwargs={
            "max_scan": 50, 
            "batch_size": 10,
            "progress_callback": callback
        })
        thread.daemon = True # 确保主进程退出时子线程也退出
        thread.start()
        
        # 监听队列并将消息发送给前端
        # 增加一个终止条件，如果线程结束且队列为空，则退出循环
        while True:
            try:
                # 使用 timeout 避免永久阻塞
                msg = q.get(timeout=1.0)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                
                # 如果收到 done 消息，说明任务正常结束
                if isinstance(msg, dict) and msg.get("status") == "done":
                    break
            except Exception:
                # 检查线程是否还在运行，如果线程已挂且队列为空，则安全退出
                if not thread.is_alive() and q.empty():
                    # 补包一个 done 消息，防止前端一直等待
                    final_msg = {"status": "done", "message": "同步任务结束"}
                    yield f"data: {json.dumps(final_msg, ensure_ascii=False)}\n\n"
                    break
                continue
                
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/todo", response_class=HTMLResponse)
async def read_todo():
    return serve_html("todo.html")

def process_smart_todo(email_id: int, todo_id: int):
    """后台处理：从邮件中智能提取待办并更新占位符"""
    try:
        email = db.get_email_by_id(email_id)
        if not email:
            return
            
        todo_skill = TodoSkill()
        content_to_analyze = email.get('body') or email.get('summary')
        
        extracted_info = todo_skill.extract_todo_info(content_to_analyze)
        
        # 组装待办数据并更新占位符
        from datetime import datetime
        todo_data = {
            "title": extracted_info.get("title", email.get("subject")),
            "content": extracted_info.get("details", ""),
            "priority": extracted_info.get("priority", "Normal"),
            "due_date": extracted_info.get("due_date", datetime.now().strftime("%Y-%m-%d")),
            "status": 0
        }
        db.update_todo(todo_id, todo_data)
        print(f"✅ 邮件 {email_id} 的智能待办已更新 (后台任务)")
    except Exception as e:
        print(f"❌ 智能提取后台任务失败: {e}")
        # 失败状态，将任务置为人工处理
        db.update_todo(todo_id, {"title": f"⚠ AI 提取失败: {email.get('subject')}", "status": 0})

@app.post("/api/email/{email_id}/add-smart-todo")
async def add_smart_todo(email_id: int, background_tasks: BackgroundTasks):
    """一键转为待办：理解后门异步处理"""
    email = db.get_email_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
        
    # 立即插入带有AI处理中标记（status=2）的占位待办事项
    from datetime import datetime
    placeholder_data = {
        "email_id": email_id,
        "title": f"AI 正在提取待办: {email.get('subject', '未知标题')}",
        "content": "请稍候，DeepSeek 正在扫描邮件内容并提取截止日期...",
        "priority": "Normal",
        "due_date": datetime.now().strftime("%Y-%m-%d"),
        "status": 2
    }
    todo_id = db.add_todo(placeholder_data)
        
    background_tasks.add_task(process_smart_todo, email_id, todo_id)
    return {"status": "processing", "message": "已进入后台提取并保存", "todo_id": todo_id}

@app.get("/api/todos")
async def get_todos():
    """获取所有待办事项"""
    return db.get_all_todos()

@app.post("/api/todos")
async def create_todo(request: Request):
    """添加本地待办事项"""
    try:
        data = await request.json()
        todo_id = db.add_todo(data)
        return {"status": "success", "id": todo_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/todos/{todo_id}")
async def update_todo(todo_id: int, request: Request):
    """更新待办事项信息"""
    try:
        data = await request.json()
        db.update_todo(todo_id, data)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: int):
    """删除待办事项"""
    db.delete_todo(todo_id)
    return {"status": "success"}

# Note: /api/todos/{todo_id}/status has been merged into PUT /api/todos/{todo_id}

@app.post("/api/sync")
def sync_now():
    """手动触发邮件同步"""
    try:
        # 手动同步时，为了响应速度，仅扫描最近 50 封邮件
        # 注意：这里的 sync_emails 是同步执行的。对于 50 封邮件，耗时通常在 5-10s 左右。
        sync_emails(max_scan=50, batch_size=10)
        
        # 同步完后获取最新统计
        count = db.get_email_count()
        return {
            "status": "success",
            "message": "同步完成",
            "total_emails": count
        }
    except Exception as e:
        print(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Prompt Lab Endpoints ---

@app.get("/prompt-lab", response_class=HTMLResponse)
async def read_prompt_lab():
    return serve_html("prompt_lab.html")

@app.get("/api/prompts")
async def get_all_prompts():
    """获取所有提示词"""
    try:
        return db.get_all_prompts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/prompts/{skill_name}")
async def update_prompt(skill_name: str, request: Request):
    """保存更新的提示词"""
    try:
        data = await request.json()
        new_prompt = data.get("system_prompt")
        if not new_prompt:
            raise HTTPException(status_code=400, detail="Missing system_prompt")
        db.update_prompt(skill_name, new_prompt)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prompts/{skill_name}/restore")
async def restore_prompt(skill_name: str):
    """恢复默认提示词"""
    try:
        db.restore_default_prompt(skill_name)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prompts/{skill_name}/optimize")
async def optimize_prompt(skill_name: str, request: Request):
    """使用 Meta-Skill 流式改写 prompt"""
    try:
        data = await request.json()
        user_request = data.get("user_request")
        if not user_request:
            raise HTTPException(status_code=400, detail="Missing user_request")
            
        current_prompt = db.get_prompt(skill_name)
        if not current_prompt:
            raise HTTPException(status_code=404, detail="Skill prompt not found")
            
        from core.prompt_meta_skill import PromptMetaSkill
        meta_skill = PromptMetaSkill()
        
        return StreamingResponse(
            meta_skill.optimize_prompt_stream(current_prompt, user_request), 
            media_type="text/plain"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
