from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from core.db_manager import DBManager
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
