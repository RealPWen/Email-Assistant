document.addEventListener('DOMContentLoaded', () => {
    let todos = [];
    let currentViewDate = new Date();
    let activeFilterDate = null;
    let searchQuery = '';

    const dom = {
        taskList: document.getElementById('task-list'),
        calendarDays: document.getElementById('calendar-days'),
        monthYear: document.getElementById('calendar-month-year'),
        prevBtn: document.getElementById('prev-month'),
        nextBtn: document.getElementById('next-month'),
        toast: document.getElementById('toast'),
        searchInput: document.getElementById('task-search')
    };

    const modalDom = {
        overlay: document.getElementById('todo-modal'),
        id: document.getElementById('modal-todo-id'),
        title: document.getElementById('modal-todo-title'),
        date: document.getElementById('modal-todo-date'),
        priority: document.getElementById('modal-todo-priority'),
        details: document.getElementById('modal-todo-details'),
        saveBtn: document.getElementById('modal-confirm'),
        cancelBtn: document.getElementById('modal-cancel'),
        closeBtn: document.getElementById('modal-close')
    };

    let pollInterval = null;

    // --- Initialization ---
    async function init() {
        await fetchTodos();
        renderCalendar();
        renderTasks();
        setupListeners();
    }

    async function fetchTodos() {
        try {
            const res = await fetch('/api/todos');
            todos = await res.json();
            checkPolling();
        } catch (err) {
            console.error('Failed to fetch todos:', err);
            dom.taskList.innerHTML = '<div class="error">无法加载待办事项</div>';
        }
    }

    function checkPolling() {
        const hasProcessing = todos.some(t => t.status === 2);
        if (hasProcessing && !pollInterval) {
            pollInterval = setInterval(async () => {
                await fetchTodos();
                renderTasks();
                renderCalendar();
            }, 3000); // 智能轮询：只在有任务处理时刷新
        } else if (!hasProcessing && pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }
    }

    function setupListeners() {
        dom.prevBtn.addEventListener('click', () => {
            currentViewDate.setMonth(currentViewDate.getMonth() - 1);
            renderCalendar();
        });

        dom.nextBtn.addEventListener('click', () => {
            currentViewDate.setMonth(currentViewDate.getMonth() + 1);
            renderCalendar();
        });

        dom.searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value.toLowerCase();
            renderTasks();
        });
    }

    // --- Task Rendering ---
    function renderTasks() {
        let filtered = [...todos];
        
        // 1. Filter by Date
        if (activeFilterDate) {
            filtered = filtered.filter(t => t.due_date === activeFilterDate);
        }

        // 2. Filter by Search Query
        if (searchQuery) {
            filtered = filtered.filter(t => 
                t.title.toLowerCase().includes(searchQuery) || 
                (t.content && t.content.toLowerCase().includes(searchQuery))
            );
        }

        if (filtered.length === 0) {
            renderEmptyState();
            return;
        }

        dom.taskList.innerHTML = filtered.map((task, index) => {
            const isProcessing = task.status === 2;
            const extraClass = isProcessing ? 'ai-processing' : (task.status === 1 ? 'completed' : '');
            const titleHtml = isProcessing ? `<i class="fas fa-spinner"></i> ${task.title}` : task.title;
            
            let actionBtns = '';
            let bodyClick = '';
            if (!isProcessing) {
                actionBtns = `
                    <button class="action-circle btn-done" onclick="event.stopPropagation(); window.toggleTodo(${task.id}, ${task.status})" title="${task.status ? '设为未完成' : '设为已完成'}">
                        <i class="fas ${task.status ? 'fa-undo' : 'fa-check'}"></i>
                    </button>
                    <button class="action-circle btn-delete-task" onclick="event.stopPropagation(); window.deleteTodo(${task.id})" title="删除任务">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                `;
                bodyClick = `onclick="window.editTodo(${task.id})"`;
            }

            return `
            <div class="task-item ${extraClass}" style="animation: itemEntrance 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) ${index * 0.05}s backwards">
                <div class="priority-line priority-${task.priority.toLowerCase()}"></div>
                <div class="task-body" ${bodyClick} style="${!isProcessing ? 'cursor: pointer;' : ''}">
                    <div class="task-title">${titleHtml}</div>
                    <div class="task-desc">${task.content || (isProcessing ? '稍微喝杯咖啡，AI 马上就好...' : '未提供具体描述')}</div>
                    <div class="task-footer">
                        <div class="tag-pill"><i class="far fa-calendar-alt"></i> ${task.due_date}</div>
                        <div class="tag-pill"><i class="far fa-clock"></i> ${formatTime(task.created_at)}</div>
                    </div>
                </div>
                <div class="task-item-actions">
                    ${actionBtns}
                </div>
            </div>`;
        }).join('');
    }

    function renderEmptyState() {
        let icon = 'fa-tasks';
        let h3 = activeFilterDate ? '该日期暂无任务' : '暂无待办事项';
        let p = activeFilterDate ? '您可以切换日期或点击“全部”查看更多' : '去邮件列表把重要事情记录下来吧';
        
        if (searchQuery) {
            icon = 'fa-search';
            h3 = '未找到匹配结果';
            p = '请尝试调整您的关键词';
        }

        dom.taskList.innerHTML = `
            <div class="empty-state">
                <i class="fas ${icon}"></i>
                <h3>${h3}</h3>
                <p>${p}</p>
                ${activeFilterDate ? '<button onclick="window.setFilterDate(null)" style="margin-top: 15px; padding: 8px 16px; border-radius: 12px; border: 1px solid var(--primary); background: transparent; color: var(--primary); cursor: pointer; font-weight: 600;">显示全部任务</button>' : ''}
            </div>
        `;
    }

    // --- Calendar Rendering ---
    function renderCalendar() {
        const year = currentViewDate.getFullYear();
        const month = currentViewDate.getMonth();
        
        dom.monthYear.textContent = `${year}年 ${month + 1}月`;

        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const prevDaysInMonth = new Date(year, month, 0).getDate();
        
        const taskDays = new Set(todos.filter(t => !t.status).map(t => t.due_date));

        let daysHtml = '';
        const today = new Date().toISOString().split('T')[0];

        // Prev Month Fill
        for (let i = firstDay; i > 0; i--) {
            daysHtml += `<div class="day-cell other-month">${prevDaysInMonth - i + 1}</div>`;
        }

        // Current Month
        for (let i = 1; i <= daysInMonth; i++) {
            const dStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
            const isToday = dStr === today;
            const hasTask = taskDays.has(dStr);
            const isActive = dStr === activeFilterDate;

            daysHtml += `
                <div class="day-cell ${isToday ? 'today-cell' : ''} ${hasTask ? 'has-todos' : ''} ${isActive ? 'active-cell' : ''}" 
                     onclick="window.setFilterDate('${dStr}')">
                    ${i}
                </div>`;
        }
        
        dom.calendarDays.innerHTML = daysHtml;
    }

    // --- Globals for Handlers ---
    window.setFilterDate = (dateStr) => {
        if (activeFilterDate === dateStr) {
            activeFilterDate = null;
        } else {
            activeFilterDate = dateStr;
        }
        renderCalendar();
        renderTasks();
        if (activeFilterDate) showToast(`已筛选: ${dateStr}`);
    };

    window.toggleTodo = async (id, currentStatus) => {
        try {
            const res = await fetch(`/api/todos/${id}/status`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ status: currentStatus ? 0 : 1 })
            });
            if (res.ok) {
                const todo = todos.find(t => t.id === id);
                if (todo) todo.status = currentStatus ? 0 : 1;
                renderTasks();
                renderCalendar();
                showToast(currentStatus ? '已选为恢复待办' : '✅ 任务已完成！');
            }
        } catch (err) {
            console.error('Update failed:', err);
        }
    };

    window.deleteTodo = async (id) => {
        if (!confirm('确定要删除这项待办吗？')) return;
        try {
            const res = await fetch(`/api/todos/${id}`, { method: 'DELETE' });
            if (res.ok) {
                todos = todos.filter(t => t.id !== id);
                renderTasks();
                renderCalendar();
                showToast('已删除任务');
            }
        } catch (err) {
            console.error('Delete failed:', err);
        }
    };

    window.editTodo = (id) => {
        const todo = todos.find(t => t.id === id);
        if (!todo) return;
        
        modalDom.id.value = todo.id;
        modalDom.title.value = todo.title;
        modalDom.date.value = todo.due_date;
        modalDom.priority.value = todo.priority;
        modalDom.details.value = todo.content || '';
        
        modalDom.overlay.classList.remove('hidden');
    };

    function closeEditModal() {
        modalDom.overlay.classList.add('hidden');
    }

    async function handleSaveModal() {
        const id = modalDom.id.value;
        const updatedData = {
            title: modalDom.title.value,
            due_date: modalDom.date.value,
            priority: modalDom.priority.value,
            content: modalDom.details.value
        };

        modalDom.saveBtn.disabled = true;
        modalDom.saveBtn.textContent = '保存中...';

        try {
            const res = await fetch(`/api/todos/${id}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(updatedData)
            });
            
            if (res.ok) {
                closeEditModal();
                await fetchTodos(); // Refresh data
                renderTasks();
                renderCalendar();
                showToast('任务已更新');
            }
        } catch (err) {
            console.error('Failed to update todo:', err);
            alert('保存失败，请重试');
        } finally {
            modalDom.saveBtn.disabled = false;
            modalDom.saveBtn.textContent = '确认保存';
        }
    }

    // Modal listeners
    modalDom.cancelBtn.addEventListener('click', closeEditModal);
    modalDom.closeBtn.addEventListener('click', closeEditModal);
    modalDom.saveBtn.addEventListener('click', handleSaveModal);

    // --- Utils ---
    function formatTime(timestamp) {
        if (!timestamp) return '';
        // SQLite 的 CURRENT_TIMESTAMP 是 UTC 时间，但格式为 "YYYY-MM-DD HH:MM:SS"
        // JavaScript Date 解析这种格式默认会当作本地时间，因此需要补上 'Z' 使其被正确识别为 UTC
        let utcStr = timestamp;
        if (timestamp.includes(' ') && !timestamp.includes('Z')) {
            utcStr = timestamp.replace(' ', 'T') + 'Z';
        }
        const date = new Date(utcStr);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function showToast(msg) {
        dom.toast.textContent = msg;
        dom.toast.style.display = 'block';
        setTimeout(() => { dom.toast.style.display = 'none'; }, 2000);
    }

    init();
});
