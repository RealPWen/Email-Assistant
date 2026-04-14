let currentPrompts = {};

// 初始化加载所有 prompts
async function fetchPrompts() {
    try {
        const res = await fetch('/api/prompts');
        const data = await res.json();
        
        // 转换为键值对形式
        data.forEach(item => {
            currentPrompts[item.skill_name] = item.system_prompt;
        });
        
        loadPrompt();
    } catch (e) {
        console.error("加载失败:", e);
        document.getElementById('prompt-editor').value = "加载提示词失败。";
    }
}

function loadPrompt() {
    const skill = document.getElementById('skill-select').value;
    const editor = document.getElementById('prompt-editor');
    editor.value = currentPrompts[skill] || "No prompt found.";
}

async function savePrompt() {
    const skill = document.getElementById('skill-select').value;
    const content = document.getElementById('prompt-editor').value;
    
    try {
        const res = await fetch(`/api/prompts/${skill}`, {
            method: 'PUT',
            headers:{ 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_prompt: content })
        });
        if(res.ok) {
            currentPrompts[skill] = content;
            showToast();
        }
    } catch (e) {
        alert('保存失败!');
    }
}

async function restoreDefault() {
    if(!confirm("确定要恢复默认设定吗？这会覆盖所有的个性化修改。")) return;
    
    const skill = document.getElementById('skill-select').value;
    try {
        const res = await fetch(`/api/prompts/${skill}/restore`, { method: 'POST' });
        if(res.ok) {
            await fetchPrompts(); // 刷新数据
            showToast("已恢复默认");
        }
    } catch (e) {
        alert('恢复失败!');
    }
}

function showToast(msg = "已保存修改 (立刻生效)") {
    const toast = document.getElementById('toast');
    toast.innerHTML = `<i class="fas fa-check-circle"></i> ${msg}`;
    toast.style.display = 'inline-block';
    setTimeout(() => { toast.style.display = 'none'; }, 3000);
}

// --- Chat Interaction ---
function appendMessage(sender, text) {
    const container = document.getElementById('chat-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;
    msgDiv.innerText = text;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

async function handleOptimize(e) {
    e.preventDefault();
    const input = document.getElementById('user-input');
    const text = input.value.trim();
    if(!text) return;

    const skill = document.getElementById('skill-select').value;
    
    appendMessage('user', text);
    input.value = '';
    
    const btn = document.getElementById('send-btn');
    const indicator = document.getElementById('typing-indicator');
    btn.disabled = true;
    indicator.style.display = 'block';

    try {
        const res = await fetch(`/api/prompts/${skill}/optimize`, {
            method: 'POST',
            headers:{ 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_request: text })
        });
        
        if (!res.ok) {
            appendMessage('system', '网络请求失败。');
            return;
        }
        
        const editor = document.getElementById('prompt-editor');
        editor.value = ""; // 清空编辑器，准备流式写入
        
        const container = document.getElementById('chat-messages');
        const sysMsgDiv = document.createElement('div');
        sysMsgDiv.className = `message system`;
        sysMsgDiv.innerText = "正在为您重写左侧的系统指令...";
        container.appendChild(sysMsgDiv);
        container.scrollTop = container.scrollHeight;
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let done = false;
        let fullText = "";
        
        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;
                
                let displayText = fullText;
                if (displayText.startsWith("```json\n")) displayText = displayText.substring(8);
                else if (displayText.startsWith("```\n")) displayText = displayText.substring(4);
                else if (displayText.startsWith("```")) displayText = displayText.substring(3);
                if (displayText.endsWith("```")) displayText = displayText.slice(0, -3);
                
                editor.value = displayText;
            }
        }
        
        editor.style.transition = 'background 0.3s';
        editor.style.background = '#e8f8f5';
        setTimeout(() => editor.style.background = '#fdfdfd', 800);
        sysMsgDiv.innerText = "重写完成！您可以审核并在右上方点击“保存更新”使其生效。";
        
    } catch (error) {
        appendMessage('system', '网络请求错误，请重试。: ' + error);
    } finally {
        btn.disabled = false;
        indicator.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', fetchPrompts);
