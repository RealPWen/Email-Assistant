document.addEventListener('DOMContentLoaded', () => {
    const emailListElement = document.getElementById('email-list');
    const detailView = document.getElementById('detail-view');
    const welcomeView = document.getElementById('welcome-view');
    
    const panelOriginal = document.getElementById('pane-original');
    const panelTranslation = document.getElementById('pane-translation');
    
    let currentEmails = [];
    let emailCache = new Map(); // Caching email details
    let isSyncingScroll = false;
    let currentFilter = 'all'; // 'all' or 'high'

    // --- DOM Cache for Detail View ---
    const dom = {
        subject: document.getElementById('detail-subject'),
        sender: document.getElementById('detail-sender-name'),
        date: document.getElementById('detail-date'),
        importance: document.getElementById('detail-importance'),
        category: document.getElementById('detail-category'),
        summary: document.getElementById('detail-summary'),
        avatar: document.getElementById('detail-avatar'),
        original: document.getElementById('content-original'),
        translation: document.getElementById('content-translation'),
        actionsList: document.getElementById('detail-action-items'),
        bodyContainer: document.getElementById('body-container')
    };

    // --- Data Fetching ---
    async function fetchEmails() {
        try {
            const response = await fetch('/api/emails?limit=500')
            .then(res => res.json())
            .then(data => {
                currentEmails = data;
                applyFilters();
                updateStats(data);
            });
        } catch (error) {
            console.error('Failed to fetch emails:', error);
            emailListElement.innerHTML = '<div class="error">无法连接到服务器</div>';
        }
    }

    function applyFilters() {
        const importanceSelect = document.getElementById('filter-importance');
        if (!importanceSelect) return;
        
        const selectedImportance = importanceSelect.value;
        let filtered = [...currentEmails];
        
        // 1. Filter by Folder / Category (Sidebar priority)
        if (currentFilter === 'high') {
            filtered = filtered.filter(e => e.importance === '高');
            importanceSelect.value = 'high'; // Sync dropdown
        } else if (currentFilter === 'all') {
            // When Inbox is clicked via sidebar, we show everything and reset dropdown
            importanceSelect.value = 'all';
        } else if (currentFilter.startsWith('category:')) {
            const targetCategory = currentFilter.replace('category:', '');
            filtered = filtered.filter(e => (e.category || '其他') === targetCategory);
            importanceSelect.value = 'all'; // Categories usually encompass high/low
        } else {
            // In Inbox/All mode (if triggered manually by dropdown), respect dropdown
            if (selectedImportance === 'high') {
                filtered = filtered.filter(e => e.importance === '高');
            } else if (selectedImportance === 'low') {
                filtered = filtered.filter(e => e.importance !== '高');
            }
        }
        
        renderEmailList(filtered);
    }

    function renderEmailList(emails) {
        if (emails.length === 0) {
            emailListElement.innerHTML = '<div class="empty">暂无相关邮件</div>';
            return;
        }

        emailListElement.innerHTML = emails.map(email => `
            <div class="email-item ${email.is_read ? '' : 'unread'}" data-id="${email.id}">
                <div class="importance-marker ${email.importance === '高' ? 'high' : ''}"></div>
                <div class="item-content">
                    <div class="item-top">
                        <span class="item-sender">${(email.sender || '').split('<')[0].trim()}</span>
                        <span class="item-date">${formatDate(email.date)}</span>
                    </div>
                    <div class="item-subject">
                        <span class="badge ${getCategoryClass(email.category)}">${email.category || '其他'}</span>
                        ${email.subject || '(无主题)'}
                    </div>
                    <div class="item-summary">${email.summary || '无摘要...'}</div>
                </div>
            </div>
        `).join('');

        // Add Click Events
        document.querySelectorAll('.email-item').forEach(item => {
            item.addEventListener('click', () => loadEmailDetail(item.dataset.id));
        });
    }

    async function loadEmailDetail(id) {
        // Highlight active
        document.querySelectorAll('.email-item').forEach(el => el.classList.remove('active'));
        const target = document.querySelector(`.email-item[data-id="${id}"]`);
        if (target) {
            target.classList.add('active');
            target.classList.remove('unread');
        }

        // 1. Check Cache
        if (emailCache.has(id)) {
            displayEmail(emailCache.get(id));
            return;
        }

        // 2. Show Loading State
        showLoadingState();

        try {
            const response = await fetch(`/api/email/${id}`);
            const email = await response.json();
            
            // Save to Cache
            emailCache.set(id, email);
            
            displayEmail(email);
            
            // Mark as read in background
            fetch(`/api/email/${id}/read`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({is_read: 1})
            });
        } catch (error) {
            console.error('Error loading email details:', error);
            dom.summary.textContent = '加载失败，请重试';
        }
    }

    function showLoadingState() {
        welcomeView.classList.add('hidden');
        detailView.classList.remove('hidden');
        dom.subject.textContent = '正在加载...';
        dom.summary.textContent = 'AI 助手正在获取详情...';
        dom.original.innerHTML = '<div class="loading-shimmer"></div>';
        dom.translation.innerHTML = '<div class="loading-shimmer"></div>';
    }

    function displayEmail(email) {
        welcomeView.classList.add('hidden');
        detailView.classList.remove('hidden');

        dom.subject.textContent = email.subject || '(无主题)';
        dom.sender.textContent = email.sender || '未知发送者';
        dom.date.textContent = email.date_str || '';
        dom.importance.textContent = email.importance || '低';
        dom.importance.className = `tag importance-tag ${email.importance === '高' ? '' : 'hidden'}`;
        
        if (dom.category) {
            dom.category.textContent = email.category || '其他';
            dom.category.className = `tag category-tag ${getCategoryClass(email.category)}`;
        }
        
        dom.summary.textContent = email.summary || '未生成摘要';
        dom.avatar.textContent = (email.sender || '?').charAt(0).toUpperCase();

        dom.original.innerHTML = formatEmailBody(email.body);
        dom.translation.innerHTML = formatEmailBody(email.body_translation || '暂无翻译内容');

        const items = email.action_items || [];
        if (typeof items === 'string') {
            try { 
                dom.actionsList.innerHTML = JSON.parse(items).map(item => `<li>${item}</li>`).join(''); 
            } catch(e) { 
                dom.actionsList.innerHTML = '<li>无行动项</li>'; 
            }
        } else if (Array.isArray(items)) {
            dom.actionsList.innerHTML = items.length ? items.map(item => `<li>${item}</li>`).join('') : '<li>无行动项</li>';
        } else {
            dom.actionsList.innerHTML = '<li>无行动项</li>';
        }

        // Ensure scrolls reset
        panelOriginal.scrollTop = 0;
        panelTranslation.scrollTop = 0;
    }

    // --- Helpers ---
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }
        return date.toLocaleDateString([], {month: 'short', day: 'numeric'});
    }

    function getCategoryClass(category) {
        const mapping = {
            '课程内容': 'badge-course',
            '学术研究': 'badge-research',
            '讲座与学术': 'badge-seminar',
            '财务': 'badge-financial',
            '职业发展': 'badge-career',
            '校内事务': 'badge-campus',
            '系统通知': 'badge-notification',
            '社交与活动': 'badge-social',
            '校企与外部': 'badge-external',
            '推广': 'badge-promotion',
            '其他': 'badge-other'
        };
        return mapping[category] || 'badge-other';
    }

    function getCategoryDotClass(category) {
        const mapping = {
            '课程内容': 'dot-course',
            '学术研究': 'dot-research',
            '讲座与学术': 'dot-seminar',
            '财务': 'dot-financial',
            '职业发展': 'dot-career',
            '校内事务': 'dot-campus',
            '系统通知': 'dot-notification',
            '社交与活动': 'dot-social',
            '校企与外部': 'dot-external',
            '推广': 'dot-promotion',
            '其他': 'dot-other'
        };
        return mapping[category] || 'dot-other';
    }

    // --- Dynamic Sidebar Categories ---
    function setupCategoryList() {
        const categoryList = document.getElementById('category-list');
        const categories = [
            '课程内容', '学术研究', '讲座与学术', '财务', '职业发展', 
            '校内事务', '系统通知', '社交与活动', '校企与外部', '推广', '其他'
        ];
        
        categoryList.innerHTML = categories.map(cat => `
            <li class="category-item" data-category="${cat}">
                <span class="category-pill ${getCategoryDotClass(cat)}"></span>
                ${cat}
            </li>
        `).join('');

        // Sub-item Click
        categoryList.querySelectorAll('.category-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation(); // Avoid parent toggle
                
                // Clear all active states
                document.querySelectorAll('.folder-list li, .category-item, .folder-item, .folder-header').forEach(el => el.classList.remove('active'));
                
                // Set specific active states
                item.classList.add('active');
                document.getElementById('archive-header').classList.add('active'); // Keep parent highlighted
                
                currentFilter = `category:${item.dataset.category}`;
                applyFilters();
            });
        });
    }

    function setupSidebar() {
        const archiveItem = document.getElementById('folder-archive');
        const archiveHeader = document.getElementById('archive-header');
        const folderItems = document.querySelectorAll('.folder-list > li:not(.expandable)');

        // Archive Toggle
        archiveHeader.addEventListener('click', (e) => {
            const isExpanding = !archiveItem.classList.contains('expanded');
            
            // Highlight parent
            document.querySelectorAll('.folder-list li, .category-item, .folder-item, .folder-header').forEach(el => el.classList.remove('active'));
            archiveHeader.classList.add('active');
            
            if (isExpanding) {
                archiveItem.classList.add('expanded');
                archiveHeader.classList.add('expanded');
            } else {
                archiveItem.classList.remove('expanded');
                archiveHeader.classList.remove('expanded');
            }
            
            // Return to show all emails in Archive mode
            currentFilter = 'all';
            applyFilters();
        });

        // Other Main Folders
        folderItems.forEach(item => {
            item.addEventListener('click', () => {
                // Collapse Archive
                archiveItem.classList.remove('expanded');
                archiveHeader.classList.remove('expanded');
                
                // Set Active State
                document.querySelectorAll('.folder-list li, .category-item, .folder-item, .folder-header').forEach(el => el.classList.remove('active'));
                item.classList.add('active');
                
                currentFilter = (item.id === 'folder-important') ? 'high' : 'all';
                applyFilters();
            });
        });
        
        setupCategoryList();
    }

    function formatEmailBody(body) {
        if (!body) return '';
        if (!body.includes('<p>') && !body.includes('<div>')) {
            return body.replace(/\n/g, '<br>');
        }
        return body;
    }

    function updateStats(emails) {
        if (!emails || emails.length === 0) return;
        
        // Parse dates and filter out invalid ones
        const dates = emails
            .map(e => e.date ? new Date(e.date) : null)
            .filter(d => d && !isNaN(d.getTime()))
            .sort((a, b) => a - b);

        if (dates.length === 0) return;

        const earliest = dates[0];
        const latest = dates[dates.length - 1];
        
        const formatDateShort = (d) => {
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        };

        const timeFormat = (d) => {
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        };

        document.getElementById('stat-total').textContent = emails.length;
        document.getElementById('stat-earliest').textContent = formatDateShort(earliest);
        document.getElementById('stat-latest').textContent = formatDateShort(latest);
        document.getElementById('stat-last-activity').textContent = `${formatDateShort(latest)} ${timeFormat(latest)}`;
    }

    // --- Sync Scrolling Logic ---
    const syncScroll = (source, target) => {
        // Only run sync if we are in split view
        if (!dom.bodyContainer.classList.contains('split-view')) return;
        
        if (isSyncingScroll) {
            isSyncingScroll = false;
            return;
        }
        isSyncingScroll = true;
        const percentage = source.scrollTop / (source.scrollHeight - source.clientHeight);
        target.scrollTop = percentage * (target.scrollHeight - target.clientHeight);
    };

    panelOriginal.addEventListener('scroll', () => syncScroll(panelOriginal, panelTranslation));
    panelTranslation.addEventListener('scroll', () => syncScroll(panelTranslation, panelOriginal));

    // --- View Toggle Logic ---
    const updateActiveButton = (id) => {
        document.querySelectorAll('.view-controls button').forEach(btn => btn.classList.remove('active'));
        document.getElementById(id).classList.add('active');
        
        if (id === 'btn-original') {
            panelTranslation.classList.add('hidden');
            panelOriginal.classList.remove('hidden');
        } else if (id === 'btn-translation') {
            panelOriginal.classList.add('hidden');
            panelTranslation.classList.remove('hidden');
        } else {
            panelOriginal.classList.remove('hidden');
            panelTranslation.classList.remove('hidden');
        }
    };

    document.getElementById('btn-split').addEventListener('click', () => {
        document.getElementById('body-container').className = 'body-container split-view';
        updateActiveButton('btn-split');
    });

    document.getElementById('btn-original').addEventListener('click', () => {
        document.getElementById('body-container').className = 'body-container only-original';
        updateActiveButton('btn-original');
    });

    document.getElementById('btn-translation').addEventListener('click', () => {
        document.getElementById('body-container').className = 'body-container only-translation';
        updateActiveButton('btn-translation');
    });

    // --- Filtering Logic ---
    const filterSelect = document.getElementById('filter-importance');
    if (filterSelect) {
        filterSelect.addEventListener('change', applyFilters);
    }

    setupSidebar();

    // --- Actions ---
    function updateSyncProgress(data) {
        const container = document.getElementById('sync-progress-container');
        const bar = document.getElementById('sync-progress-bar');
        const statusText = document.getElementById('sync-status-text');
        const percentText = document.getElementById('sync-percent');
        const detailText = document.getElementById('sync-detail-text');

        if (!container) return;

        container.style.display = 'block';
        if (data.progress) {
            bar.style.width = data.progress + '%';
            percentText.textContent = data.progress + '%';
        }
        if (data.message) statusText.textContent = data.message;
        if (data.details && data.details.last_subject) {
            detailText.textContent = `最新: ${data.details.last_subject}`;
        } else if (data.status === 'done') {
            detailText.textContent = '所有邮件已同步';
        }
    }

    async function syncAndRefresh() {
        const refreshBtn = document.getElementById('refresh-btn');
        const icon = refreshBtn.querySelector('i');
        const container = document.getElementById('sync-progress-container');
        
        // 1. 进入同步状态
        refreshBtn.disabled = true;
        icon.classList.add('fa-spin-custom');
        refreshBtn.style.opacity = '0.5';
        
        try {
            console.log('Starting streaming sync...');
            const eventSource = new EventSource('/api/sync/progress');

            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Sync Update:', data);
                
                updateSyncProgress(data);

                if (data.status === 'done') {
                    eventSource.close();
                    
                    // 恢复状态并刷新列表
                    setTimeout(() => {
                        container.style.display = 'none';
                        refreshBtn.disabled = false;
                        icon.classList.remove('fa-spin-custom');
                        refreshBtn.style.opacity = '1';
                        fetchEmails();
                        updateStats();
                    }, 1500);
                }
            };

            eventSource.onerror = (err) => {
                console.error('SSE Error:', err);
                eventSource.close();
                container.style.display = 'none';
                refreshBtn.disabled = false;
                icon.classList.remove('fa-spin-custom');
                refreshBtn.style.opacity = '1';
            };
            
        } catch (error) {
            console.error('Sync failed:', error);
            refreshBtn.disabled = false;
            icon.classList.remove('fa-spin-custom');
            refreshBtn.style.opacity = '1';
        }
    }

    document.getElementById('refresh-btn').addEventListener('click', syncAndRefresh);

    const toggleHeader = document.getElementById('toggle-action-items');
    const actionItemsList = document.getElementById('detail-action-items');
    
    if (toggleHeader && actionItemsList) {
        toggleHeader.addEventListener('click', () => {
            const isCollapsed = actionItemsList.classList.toggle('collapsed');
            toggleHeader.classList.toggle('active', !isCollapsed);
        });
    }

    // Initial Load
    fetchEmails();
});
