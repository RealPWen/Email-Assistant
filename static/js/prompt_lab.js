let currentPrompts = {};
let activeSkill = null;

// 初始化加载所有 prompts
window.initPromptLab = async function() {
    const skillList = document.getElementById('skill-list');
    // Check if skills are already loaded (tabs exist)
    if (!skillList || skillList.querySelectorAll('.skill-tab').length === 0) {
        await fetchPrompts();
    }
};

async function fetchPrompts() {
    try {
        const res = await fetch('/api/prompts');
        const data = await res.json();
        
        // 渲染左侧列表
        const skillList = document.getElementById('skill-list');
        skillList.innerHTML = data.map(skill => `
            <li class="skill-tab" data-skill="${skill.skill_name}" style="padding: 12px 15px; border-radius: 8px; margin-bottom: 8px; cursor: pointer; display: flex; align-items: center; gap: 10px; transition: all 0.2s; border-left: 3px solid transparent;">
                <i class="fas ${getSkillIcon(skill.skill_name)}" style="width: 20px; text-align: center; color: var(--text-muted);"></i>
                <span style="font-size: 0.9rem; font-weight: 500; color: var(--text-main);">${formatSkillName(skill.skill_name)}</span>
            </li>
        `).join('');

        // 绑定点击事件
        skillList.querySelectorAll('.skill-tab').forEach(tab => {
            tab.addEventListener('click', () => selectSkill(tab.dataset.skill, data.find(s => s.skill_name === tab.dataset.skill)));
        });

        // 默认选择第一个
        if (data.length > 0 && !activeSkill) {
            const firstSkill = data[0];
            selectSkill(firstSkill.skill_name, firstSkill);
        }
    } catch (e) {
        console.error("加载失败:", e);
    }
}

function selectSkill(skillName, skillData) {
    if (!skillData) return;
    activeSkill = skillName;
    
    // UI 高亮切换
    document.querySelectorAll('.skill-tab').forEach(tab => {
        if (tab.dataset.skill === skillName) {
            tab.style.background = 'var(--bg-active)';
            tab.style.borderColor = 'var(--accent-sage)';
            tab.querySelector('i').style.color = 'var(--accent-sage)';
        } else {
            tab.style.background = 'transparent';
            tab.style.borderColor = 'transparent';
            tab.querySelector('i').style.color = 'var(--text-muted)';
        }
    });

    // 切换编辑器
    const placeholder = document.getElementById('editor-placeholder');
    const area = document.getElementById('editor-area');
    if (placeholder) placeholder.classList.add('hidden');
    if (area) area.classList.remove('hidden');
    
    const nameEl = document.getElementById('active-skill-name');
    const textEl = document.getElementById('prompt-textarea');
    if (nameEl) nameEl.innerText = formatSkillName(skillName);
    if (textEl) textEl.value = skillData.system_prompt || '';
}

async function savePrompt() {
    if (!activeSkill) return;
    const content = document.getElementById('prompt-textarea').value;
    const saveBtn = document.getElementById('save-prompt');
    const originalText = saveBtn.innerHTML;

    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 保存中...';

    try {
        const res = await fetch(`/api/prompts/${activeSkill}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ system_prompt: content })
        });
        if (res.ok) {
            CommonUI.showToast("已应用指令更新");
        }
    } catch (e) {
        alert('保存失败!');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    }
}

async function restoreDefault() {
    if (!activeSkill || !confirm("确定要恢复默认设定吗？这会覆盖所有的个性化修改。")) return;
    
    try {
        const res = await fetch(`/api/prompts/${activeSkill}/restore`, { method: 'POST' });
        if (res.ok) {
            await fetchPrompts(); // 刷新
            CommonUI.showToast("已重置为默认指令");
        }
    } catch (e) {
        alert('恢复失败!');
    }
}

async function optimizePrompt() {
    if (!activeSkill) return;
    const requestInput = document.getElementById('optimize-request');
    const requestText = requestInput.value.trim();
    if (!requestText) {
        alert('请输入优化需求');
        return;
    }

    const optimizeBtn = document.getElementById('optimize-prompt');
    const statusOverlay = document.getElementById('optimizer-status');
    const statusText = document.getElementById('optimizer-text');
    const editor = document.getElementById('prompt-textarea');

    optimizeBtn.disabled = true;
    statusOverlay.classList.remove('hidden');
    statusText.innerText = "AI 正在优化指令...";
    
    try {
        const res = await fetch(`/api/prompts/${activeSkill}/optimize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_request: requestText })
        });

        if (!res.ok) throw new Error("优化请求失败");

        editor.value = ""; // 清空并准备接收流
        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let done = false;

        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                // Remove markdown code fences if present in stream
                let cleanChunk = chunk.replace(/```json\n?|```\n?/g, "");
                editor.value += cleanChunk;
                editor.scrollTop = editor.scrollHeight;
            }
        }

        statusText.innerText = "优化完成！审核后请保存。";
        requestInput.value = "";
        setTimeout(() => statusOverlay.classList.add('hidden'), 3000);

    } catch (error) {
        console.error("Optimization failed:", error);
        statusText.innerText = "优化失败: " + error.message;
        setTimeout(() => statusOverlay.classList.add('hidden'), 5000);
    } finally {
        optimizeBtn.disabled = false;
    }
}

function formatSkillName(name) {
    const mapping = {
        'summary': '邮件摘要 (Email Summary)',
        'todo': '待办提取 (Todo Extraction)',
        'translation': '智能翻译 (AI Translation)',
        'meta': 'Prompt 优化器 (Meta Skill)'
    };
    return mapping[name] || name;
}

function getSkillIcon(name) {
    const mapping = {
        'summary': 'fa-file-alt',
        'todo': 'fa-check-double',
        'translation': 'fa-language',
        'meta': 'fa-magic'
    };
    return mapping[name] || 'fa-cog';
}

// 绑定主界面按钮
document.addEventListener('DOMContentLoaded', () => {
    const saveBtn = document.getElementById('save-prompt');
    const restoreBtn = document.getElementById('restore-prompt');
    const optimizeBtn = document.getElementById('optimize-prompt');
    const optimizeInput = document.getElementById('optimize-request');
    
    if (saveBtn) saveBtn.addEventListener('click', savePrompt);
    if (restoreBtn) restoreBtn.addEventListener('click', restoreDefault);
    if (optimizeBtn) optimizeBtn.addEventListener('click', optimizePrompt);
    if (optimizeInput) {
        optimizeInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') optimizePrompt();
        });
    }
});
