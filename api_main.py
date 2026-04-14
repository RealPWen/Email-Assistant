from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from core.db_manager import DBManager
from core.todo_skill import TodoSkill
from tools.fetch_emails import sync_emails
import json
import os
import asyncio
from fastapi.responses import HTMLResponse, StreamingResponse
from queue import Queue
from threading import Thread

app = FastAPI(title="DeepMail AI API")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DBManager()

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/emails")
async def get_emails(limit: int = 500):
    """获取邮件列表"""
    try:
        rows = db.get_all_emails(limit=limit)
        emails = []
        for row in rows:
            emails.append({
                "id": row['id'],
                "message_id": row['message_id'],
                "subject": row['subject'],
                "sender": row['sender'],
                "date": row['normalized_date'],
                "importance": row['importance'],
                "is_read": row['is_read'],
                "summary": row['summary'],
                "category": row['category']
            })
        return emails
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    try:
        count = db.get_email_count()
        # 这里可以扩展更多统计，如今日新增、未读数等
        return {
            "total_emails": count,
            "unread_emails": 0, # 待实现
            "important_emails": 0 # 待实现
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        thread.start()
        
        # 监听队列并将消息发送给前端
        while thread.is_alive() or not q.empty():
            try:
                # 使用 timeout 避免永久阻塞，允许检查线程状态
                msg = q.get(timeout=1.0)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except:
                continue
                
        # 确保发送最后的完成信号 (如果 sync_emails 异常退出)
        # yield "data: {\"status\": \"done\", \"message\": \"同步结束\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/todo", response_class=HTMLResponse)
async def read_todo():
    with open("static/todo.html", "r", encoding="utf-8") as f:
        return f.read()

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
    try:
        return db.get_all_todos()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/api/todos/{todo_id}/status")
async def update_todo_status(todo_id: int, request: Request):
    """更新待办事项"""
    try:
        data = await request.json()
        db.update_todo(todo_id, data)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: int):
    """删除待办事项"""
    try:
        db.delete_todo(todo_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
