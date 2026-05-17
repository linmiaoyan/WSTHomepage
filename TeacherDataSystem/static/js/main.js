// 主应用JavaScript
const API_BASE = '/api';

// HTML转义函数，防止XSS
function escapeHtml(text) {
    if (text == null) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 等待bootstrap加载的辅助函数
function getBootstrap() {
    if (typeof bootstrap !== 'undefined') {
        return bootstrap;
    }
    // 如果bootstrap未定义，尝试从window获取
    if (typeof window !== 'undefined' && window.bootstrap) {
        return window.bootstrap;
    }
    console.error('Bootstrap未加载，请检查bootstrap.bundle.min.js是否正确加载');
    return null;
}

// 初始化导航事件监听器
function initNavigation() {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.getAttribute('data-page');
            if (page) {
                switchPage(page);
                
                // 更新导航状态
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                link.classList.add('active');
            }
        });
    });
}

function switchPage(page) {
    // 隐藏所有页面
    document.querySelectorAll('.page-content').forEach(p => {
        p.style.display = 'none';
    });
    
    // 显示目标页面
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
        loadPageData(page);
        
        // 更新URL hash，以便刷新后保持当前标签页
        if (window.location.pathname.startsWith('/admin')) {
            window.location.hash = `page-${page}`;
        }
    } else {
        console.error('页面不存在:', page);
    }
}

function loadPageData(page) {
    switch(page) {
        case 'teachers':
            loadTeachers();
            break;
        case 'templates':
            loadTemplates();
            break;
        case 'tasks':
            loadTasks();
            break;
    }
}

// ========== 教师管理 ==========
// 导出教师数据为CSV
async function exportTeachersToCSV() {
    try {
        const response = await fetch(`${API_BASE}/teachers/export/csv`, {
            method: 'GET',
            headers: {
                'X-Admin-Token': localStorage.getItem('admin_token') || ''
            }
        });
        
        if (response.ok) {
            // 获取文件名
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'teachers_export.csv';
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
                if (filenameMatch) {
                    filename = filenameMatch[1];
                }
            }
            
            // 下载文件
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            alert('导出成功！');
        } else {
            const error = await response.json();
            alert('导出失败：' + (error.detail || '未知错误'));
        }
    } catch (error) {
        console.error('导出失败:', error);
        alert('导出失败：' + error.message);
    }
}

async function loadTeachers() {
    try {
        // 传递limit参数，确保获取所有教师数据
        const response = await fetch(`${API_BASE}/teachers/?limit=10000`);
        const teachers = await response.json();
        const tbody = document.getElementById('teachers-table-body');
        if (teachers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">暂无教师数据</td></tr>';
        } else {
            tbody.innerHTML = teachers.map(teacher => `
                <tr>
                    <td>${teacher.id}</td>
                    <td>${teacher.name}</td>
                    <td>${teacher.sex || '-'}</td>
                    <td>${teacher.department || '-'}</td>
                    <td>${teacher.position || '-'}</td>
                    <td>${teacher.phone || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="editTeacher(${teacher.id})">编辑</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteTeacher(${teacher.id})">删除</button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (error) {
        console.error('加载教师列表失败:', error);
        document.getElementById('teachers-table-body').innerHTML = '<tr><td colspan="7" class="text-center text-danger">加载失败</td></tr>';
    }
}

async function editTeacher(id) {
    try {
        // 加载教师信息
        const response = await fetch(`${API_BASE}/teachers/${id}`);
        if (!response.ok) {
            alert('加载教师信息失败：' + (await response.json()).detail);
            return;
        }
        
        const teacher = await response.json();
        
        // 创建编辑模态框
        const modal = createModal('编辑教师信息', `
            <form id="edit-teacher-form">
                <div class="mb-3">
                    <label class="form-label">姓名 *</label>
                    <input type="text" class="form-control" name="name" value="${escapeHtml(teacher.name || '未命名')}" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">性别</label>
                    <select class="form-select" name="sex">
                        <option value="">请选择</option>
                        <option value="男" ${teacher.sex === '男' || !teacher.sex ? 'selected' : ''}>男</option>
                        <option value="女" ${teacher.sex === '女' ? 'selected' : ''}>女</option>
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label">身份证号</label>
                    <input type="text" class="form-control" name="id_number" value="${escapeHtml(teacher.id_number || '')}">
                </div>
                <div class="mb-3">
                    <label class="form-label">手机号</label>
                    <input type="text" class="form-control" name="phone" value="${escapeHtml(teacher.phone || '')}">
                </div>
                <div class="mb-3">
                    <label class="form-label">邮箱</label>
                    <input type="email" class="form-control" name="email" value="${escapeHtml(teacher.email || '')}">
                </div>
                <div class="mb-3">
                    <label class="form-label">部门</label>
                    <input type="text" class="form-control" name="department" value="${escapeHtml(teacher.department || '')}">
                </div>
                <div class="mb-3">
                    <label class="form-label">职位</label>
                    <input type="text" class="form-control" name="position" value="${escapeHtml(teacher.position || '')}">
                </div>
                <div class="mb-3">
                    <label class="form-label">职称</label>
                    <input type="text" class="form-control" name="title" value="${escapeHtml(teacher.title || '')}">
                </div>
                ${teacher.extra_data && Object.keys(teacher.extra_data).length > 0 ? `
                    <div class="mb-3">
                        <label class="form-label">扩展数据</label>
                        <textarea class="form-control" name="extra_data_json" rows="4" readonly style="background-color: #f8f9fa; font-family: monospace; font-size: 0.9em;">${JSON.stringify(teacher.extra_data, null, 2)}</textarea>
                        <small class="form-text text-muted">扩展数据为只读，如需修改请通过Excel导入功能</small>
                    </div>
                ` : ''}
            </form>
        `, async () => {
            const form = document.getElementById('edit-teacher-form');
            const formData = new FormData(form);
            const data = {};
            
            // 收集表单数据
            for (const [key, value] of formData.entries()) {
                if (key !== 'extra_data_json' && value.trim() !== '') {
                    // 确保手机号等字段始终为字符串
                    if (key === 'phone' || key === 'id_number') {
                        data[key] = String(value.trim());
                    } else {
                        data[key] = value.trim();
                    }
                }
            }
            
            try {
                const updateResponse = await fetch(`${API_BASE}/teachers/${id}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                
                if (updateResponse.ok) {
                    alert('更新成功！');
                    loadTeachers();
                    const bs = getBootstrap();
                    if (bs) {
                        const modalElement = document.querySelector('.modal');
                        if (modalElement) {
                            const modalInstance = bs.Modal.getInstance(modalElement);
                            if (modalInstance) {
                                modalInstance.hide();
                            }
                        }
                    }
                } else {
                    const error = await updateResponse.json();
                    alert('更新失败：' + (error.detail || '未知错误'));
                }
            } catch (error) {
                alert('更新失败：' + error.message);
            }
        });
        
        document.body.appendChild(modal);
        showModal(modal);
    } catch (error) {
        alert('加载教师信息失败：' + error.message);
        console.error(error);
    }
}

// HTML转义函数，防止XSS攻击
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showImportModal() {
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">导入Excel数据</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="mb-3">
                        <label class="form-label">选择Excel文件 *</label>
                        <input type="file" class="form-control" id="import-file" accept=".xlsx,.xls" required>
                        <small class="form-text text-muted">支持.xlsx和.xls格式</small>
                    </div>
                    <div class="mb-3">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="skip-duplicates" checked>
                            <label class="form-check-label" for="skip-duplicates">
                                跳过重复记录（根据身份证号判断）
                            </label>
                        </div>
                    </div>
                    <div class="alert alert-info">
                        <strong>提示：</strong>
                        <ul class="mb-0">
                            <li>Excel第一行应为列标题</li>
                            <li>必填字段：姓名</li>
                            <li>支持的字段：姓名、性别、身份证号、联系电话、现聘用岗位2、行政职务等</li>
                            <li>其他字段会自动存储到扩展数据中</li>
                            <li><a href="${API_BASE}/import/template" target="_blank">下载导入模板</a></li>
                        </ul>
                    </div>
                    <div id="import-progress" style="display: none;">
                        <div class="progress">
                            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 100%">正在导入...</div>
                        </div>
                    </div>
                    <div id="import-result"></div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    <button type="button" class="btn btn-primary" id="import-submit-btn">开始导入</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    const bs = getBootstrap();
    const modalInstance = bs ? new bs.Modal(modal) : null;
    
    // 绑定导入按钮事件
    modal.querySelector('#import-submit-btn').addEventListener('click', async () => {
        const fileInput = modal.querySelector('#import-file');
        const skipDuplicates = modal.querySelector('#skip-duplicates').checked;
        const progressDiv = modal.querySelector('#import-progress');
        const resultDiv = modal.querySelector('#import-result');
        const submitBtn = modal.querySelector('#import-submit-btn');
        
        if (!fileInput.files || fileInput.files.length === 0) {
            alert('请选择文件');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('skip_duplicates', skipDuplicates);
        
        // 显示进度，禁用按钮
        progressDiv.style.display = 'block';
        resultDiv.innerHTML = '';
        submitBtn.disabled = true;
        
        try {
            const response = await fetch(`${API_BASE}/import/excel?skip_duplicates=${skipDuplicates}`, {
                method: 'POST',
                body: formData
            });
            
            progressDiv.style.display = 'none';
            submitBtn.disabled = false;
            
            if (response.ok) {
                const result = await response.json();
                let resultHtml = `
                    <div class="alert alert-success">
                        <h6>导入完成！</h6>
                        <p>成功：${result.success_count} 条</p>
                        <p>失败：${result.failed_count} 条</p>
                    </div>
                `;
                
                if (result.errors && result.errors.length > 0) {
                    resultHtml += `
                        <div class="alert alert-warning">
                            <h6>错误信息：</h6>
                            <ul class="mb-0" style="max-height: 200px; overflow-y: auto;">
                                ${result.errors.map(err => `<li>${err}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                }
                
                resultDiv.innerHTML = resultHtml;
                
                // 刷新教师列表
                if (result.success_count > 0) {
                    setTimeout(() => {
                        loadTeachers();
                        modalInstance.hide();
                    }, 2000);
                }
            } else {
                const error = await response.json();
                resultDiv.innerHTML = `
                    <div class="alert alert-danger">
                        <h6>导入失败</h6>
                        <p>${error.detail || '未知错误'}</p>
                    </div>
                `;
            }
        } catch (error) {
            progressDiv.style.display = 'none';
            submitBtn.disabled = false;
            resultDiv.innerHTML = `
                <div class="alert alert-danger">
                    <h6>导入失败</h6>
                    <p>${error.message}</p>
                </div>
            `;
        }
    });
    
    modal.addEventListener('hidden.bs.modal', () => modal.remove());
    if (modalInstance) {
        modalInstance.show();
    } else {
        // 如果bootstrap未加载，使用简单的显示方式
        modal.style.display = 'block';
        modal.classList.add('show');
        document.body.classList.add('modal-open');
    }
}

function showAddTeacherModal() {
    const modal = createModal('添加教师', `
        <form id="teacher-form">
            <div class="mb-3">
                <label class="form-label">姓名 *</label>
                <input type="text" class="form-control" name="name" value="未命名" required>
            </div>
            <div class="mb-3">
                <label class="form-label">性别</label>
                <select class="form-select" name="sex">
                    <option value="">请选择</option>
                    <option value="男" selected>男</option>
                    <option value="女">女</option>
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">身份证号</label>
                <input type="text" class="form-control" name="id_number">
            </div>
            <div class="mb-3">
                <label class="form-label">手机号</label>
                <input type="text" class="form-control" name="phone">
            </div>
            <div class="mb-3">
                <label class="form-label">邮箱</label>
                <input type="email" class="form-control" name="email">
            </div>
            <div class="mb-3">
                <label class="form-label">部门</label>
                <input type="text" class="form-control" name="department">
            </div>
            <div class="mb-3">
                <label class="form-label">职位</label>
                <input type="text" class="form-control" name="position">
            </div>
            <div class="mb-3">
                <label class="form-label">职称</label>
                <input type="text" class="form-control" name="title">
            </div>
        </form>
    `, async () => {
        const form = document.getElementById('teacher-form');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);
        
        try {
            const response = await fetch(`${API_BASE}/teachers/`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (response.ok) {
                alert('添加成功！');
                loadTeachers();
                const bs = getBootstrap();
                if (bs) {
                    const modalElement = document.querySelector('.modal');
                    if (modalElement) {
                        const modalInstance = bs.Modal.getInstance(modalElement);
                        if (modalInstance) {
                            modalInstance.hide();
                        }
                    }
                }
            } else {
                alert('添加失败：' + (await response.json()).detail);
            }
        } catch (error) {
            alert('添加失败：' + error.message);
        }
    });
    document.body.appendChild(modal);
    showModal(modal);
}

async function deleteTeacher(id) {
    if (!confirm('确定要删除这个教师吗？\n\n注意：删除教师将同时删除该教师的所有问卷回答记录。')) return;
    try {
        const response = await fetch(`${API_BASE}/teachers/${id}`, {method: 'DELETE'});
        if (response.ok) {
            alert('删除成功！');
            loadTeachers();
        } else {
            const error = await response.json();
            alert('删除失败：' + (error.detail || '未知错误'));
        }
    } catch (error) {
        alert('删除失败：' + error.message);
    }
}

async function deleteAllTeachers() {
    // 先获取所有教师
    try {
        const response = await fetch(`${API_BASE}/teachers/?limit=10000`);
        const teachers = await response.json();
        
        if (teachers.length === 0) {
            alert('没有可删除的教师');
            return;
        }
        
        const confirmMsg = `确定要删除所有 ${teachers.length} 个教师吗？\n\n警告：此操作不可恢复！\n删除教师将同时删除所有相关的问卷回答记录。\n\n请输入"确认删除"以继续：`;
        const userInput = prompt(confirmMsg);
        
        if (userInput !== '确认删除') {
            alert('已取消删除操作');
            return;
        }
        
        // 获取所有教师ID
        const teacherIds = teachers.map(t => t.id);
        
        // 调用批量删除API
        const deleteResponse = await fetch(`${API_BASE}/teachers/batch-delete`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({teacher_ids: teacherIds})
        });
        
        if (deleteResponse.ok) {
            const result = await deleteResponse.json();
            alert(`删除完成！\n成功删除：${result.deleted_count} 个教师\n${result.failed && result.failed.length > 0 ? '失败：' + result.failed.length + ' 个' : ''}`);
            loadTeachers();
        } else {
            const error = await deleteResponse.json();
            alert('删除失败：' + (error.detail || '未知错误'));
        }
    } catch (error) {
        alert('删除失败：' + error.message);
    }
}

// ========== 模板管理 ==========
async function loadTemplates() {
    try {
        const response = await fetch(`${API_BASE}/templates/`);
        
        // 检查响应状态
        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail || errorData.message || errorMsg;
            } catch (e) {
                // 如果响应不是JSON，尝试读取文本
                try {
                    const text = await response.text();
                    if (text) {
                        errorMsg += ` - ${text.substring(0, 100)}`;
                    }
                } catch (e2) {
                    // 忽略
                }
            }
            throw new Error(errorMsg);
        }
        
        // 检查Content-Type
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            throw new Error(`服务器返回的不是JSON格式: ${text.substring(0, 100)}`);
        }
        
        const templates = await response.json();
        const list = document.getElementById('templates-list');
        if (templates.length === 0) {
            list.innerHTML = '<div class="col-12 text-center text-muted">暂无模板</div>';
        } else {
            list.innerHTML = templates.map(template => `
                <div class="col-md-4 mb-3">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title">${template.name}</h5>
                            <p class="card-text">${template.description || '无描述'}</p>
                            <p class="text-muted small">类型: ${template.file_type || '未知'}</p>
                            <p class="text-muted small">占位符: ${template.placeholders && template.placeholders.length > 0 ? template.placeholders.join(', ') : '无'}</p>
                            <div class="d-flex gap-2 flex-wrap">
                                <button class="btn btn-sm btn-info" onclick="window.location.href='/admin/edit-placeholder?id=${template.id}'" title="编辑占位符">
                                    ✏️ 编辑占位符
                                </button>
                            <button class="btn btn-sm btn-primary" onclick="useTemplate(${template.id})">使用</button>
                            <button class="btn btn-sm btn-danger" onclick="deleteTemplate(${template.id})">删除</button>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('加载模板列表失败:', error);
        const errorMsg = error instanceof Error ? error.message : String(error);
        document.getElementById('templates-list').innerHTML = 
            `<div class="col-12 text-center text-danger">
                <p>加载失败</p>
                <small class="text-muted">${escapeHtml(errorMsg)}</small>
            </div>`;
    }
}

function showUploadTemplateModal() {
    const modal = createModal('上传模板', `
        <form id="template-form">
                <div class="mb-3">
                <label class="form-label">模板名称 *</label>
                <input type="text" class="form-control" name="name" value="未命名" required>
            </div>
            <div class="mb-3">
                <label class="form-label">描述</label>
                <textarea class="form-control" name="description" rows="3"></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label">模板文件 *</label>
                <input type="file" class="form-control" name="file" accept=".pdf" required>
                <small class="form-text text-muted">仅支持PDF格式，上传后可在编辑占位符界面拖动选择位置添加占位符</small>
            </div>
        </form>
    `, async () => {
        const form = document.getElementById('template-form');
        const formData = new FormData(form);
        formData.append('name', form.name.value);
        formData.append('description', form.description.value);
        
        try {
            const response = await fetch(`${API_BASE}/templates/?name=${encodeURIComponent(form.name.value)}&description=${encodeURIComponent(form.description.value)}`, {
                method: 'POST',
                body: formData
            });
            if (response.ok) {
                alert('上传成功！');
                loadTemplates();
                const bs = getBootstrap();
                if (bs) {
                    const modalElement = document.querySelector('.modal');
                    if (modalElement) {
                        const modalInstance = bs.Modal.getInstance(modalElement);
                        if (modalInstance) {
                            modalInstance.hide();
                        }
                    }
                }
            } else {
                alert('上传失败：' + (await response.json()).detail);
            }
        } catch (error) {
            alert('上传失败：' + error.message);
        }
    });
    document.body.appendChild(modal);
    showModal(modal);
}

// ========== 填报任务 ==========
async function loadTasks() {
    try {
        const response = await fetch(`${API_BASE}/tasks/`);
        const tasks = await response.json();
        const list = document.getElementById('tasks-list');
        if (tasks.length === 0) {
            list.innerHTML = '<div class="text-center text-muted">暂无任务</div>';
        } else {
            list.innerHTML = tasks.map(task => `
                <div class="card mb-3">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start">
                            <div style="flex: 1;">
                                <h5 class="card-title">${escapeHtml(task.name)}</h5>
                                <p class="text-muted mb-1">状态: ${getStatusBadge(task.status)}</p>
                                <p class="text-muted mb-1">创建时间: ${new Date(task.created_at).toLocaleString('zh-CN')}</p>
                                ${task.completed_at ? `<p class="text-muted mb-1">完成时间: ${new Date(task.completed_at).toLocaleString('zh-CN')}</p>` : ''}
                            </div>
                            <div class="d-flex gap-2">
                        ${task.status === 'completed' ? `
                                    <a href="${API_BASE}/tasks/${task.id}/download" class="btn btn-sm btn-primary">下载</a>
                        ` : task.status === 'processing' ? `
                                    <span class="text-info">正在处理中...</span>
                        ` : ''}
                                <button class="btn btn-sm btn-info show-task-detail-btn" data-task-id="${task.id}">查看详情</button>
                                <button class="btn btn-sm btn-danger delete-task-btn" data-task-id="${task.id}" data-task-name="${escapeHtml(task.name)}">删除</button>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
            
            // 绑定按钮事件（使用事件委托，避免重复绑定）
            const tasksList = document.getElementById('tasks-list');
            if (tasksList) {
                // 移除旧的事件监听器（如果存在）
                tasksList.removeEventListener('click', handleTaskListClick);
                // 添加新的事件监听器
                tasksList.addEventListener('click', handleTaskListClick);
            }
        }
    } catch (error) {
        console.error('加载任务列表失败:', error);
        document.getElementById('tasks-list').innerHTML = '<div class="text-center text-danger">加载失败</div>';
    }
}

// 显示任务详情（设置为全局函数）
window.showTaskDetail = async function(taskId) {
    try {
        const [taskRes, detailRes] = await Promise.all([
            fetch(`${API_BASE}/tasks/${taskId}`),
            fetch(`${API_BASE}/tasks/${taskId}/detail`)
        ]);
        
        if (!taskRes.ok || !detailRes.ok) {
            throw new Error('加载任务详情失败');
        }
        
        const task = await taskRes.json();
        const detail = await detailRes.json();
        const unknownFields = detail.unknown_fields || [];
        const extraPlaceholders = detail.extra_placeholders || [];
        const hasExtraPlaceholders = detail.has_extra_placeholders || false;
        const hasQuestionnaire = detail.has_questionnaire || false;
        const questionnaireId = detail.questionnaire_id;
        
        // 获取教师信息
        const teachersRes = await fetch(`${API_BASE}/teachers/?limit=10000`);
        const allTeachers = await teachersRes.json();
        const taskTeachers = allTeachers.filter(t => task.teacher_ids.includes(t.id));
        
        // 获取问卷回答（如果有）
        let responses = [];
        if (hasQuestionnaire && questionnaireId) {
            try {
                const responsesRes = await fetch(`${API_BASE}/questionnaires/${questionnaireId}/responses`);
                if (responsesRes.ok) {
                    responses = await responsesRes.json();
                }
            } catch (e) {
                console.error('加载问卷回答失败:', e);
            }
        }
        
        // 过滤出当前任务的教师的回答
        const taskTeacherIds = new Set(task.teacher_ids.map(id => parseInt(id)));
        const taskResponses = responses.filter(r => taskTeacherIds.has(parseInt(r.teacher_id)));
        
        // 调试信息：输出检查结果
        console.log('[导出检查] 任务ID:', taskId);
        console.log('[导出检查] 任务教师数量:', taskTeachers.length);
        console.log('[导出检查] 任务教师IDs:', Array.from(taskTeacherIds));
        console.log('[导出检查] 所有回答数量:', responses.length);
        console.log('[导出检查] 任务相关回答数量:', taskResponses.length);
        console.log('[导出检查] 任务相关回答详情:', taskResponses.map(r => ({
            teacher_id: r.teacher_id,
            submitted_at: r.submitted_at,
            has_answers: !!r.answers && Object.keys(r.answers).length > 0
        })));
        
        // 检查是否所有教师都已填写或确认（只检查当前任务的教师）
        // 需要：1. 有教师 2. 回答数量等于教师数量 3. 所有回答都有submitted_at或confirmed_status为confirmed
        const allTeachersSubmitted = taskTeachers.length > 0 && 
                                     taskResponses.length === taskTeachers.length && 
                                     taskResponses.every(r => r.submitted_at || r.confirmed_status === 'confirmed');
        
        console.log('[导出检查] 所有教师是否已提交:', allTeachersSubmitted);
        if (!allTeachersSubmitted && taskResponses.length > 0) {
            const missingSubmissions = taskResponses.filter(r => !r.submitted_at);
            console.log('[导出检查] 未提交的回答:', missingSubmissions);
        }
        
        // 获取模板的占位符信息，用于判断字段类型
        const template = detail.template || {};
        const placeholderPositions = template.placeholder_positions || [];
        
        // 创建字段类型映射（根据占位符的is_signature标记）
        const fieldTypeMap = {};
        placeholderPositions.forEach(pos => {
            const fieldName = pos.field_name;
            // 检查is_signature标记（可能是布尔值、字符串或数字）
            const isSignature = pos.is_signature === true || 
                               pos.is_signature === 'true' || 
                               pos.is_signature === 1 ||
                               pos.is_signature === '1' ||
                               String(pos.is_signature).toLowerCase() === 'true';
            if (fieldName && isSignature) {
                fieldTypeMap[fieldName] = 'signature';
                console.log(`[字段类型映射] ${fieldName} 标记为签名类型`, {
                    fieldName: fieldName,
                    is_signature: pos.is_signature,
                    type: typeof pos.is_signature
                });
            }
        });
        
        // 也检查extra_placeholders，确保它们也被包含在类型映射中
        extraPlaceholders.forEach(fieldName => {
            const pos = placeholderPositions.find(p => p.field_name === fieldName);
            if (pos) {
                const isSignature = pos.is_signature === true || 
                                   pos.is_signature === 'true' || 
                                   pos.is_signature === 1 ||
                                   pos.is_signature === '1' ||
                                   String(pos.is_signature).toLowerCase() === 'true';
                if (isSignature) {
                    fieldTypeMap[fieldName] = 'signature';
                    console.log(`[字段类型映射] 额外占位符 ${fieldName} 标记为签名类型`);
                }
            }
        });
        
        console.log('[字段类型映射] 完整的fieldTypeMap:', fieldTypeMap);
        console.log('[字段类型映射] placeholderPositions数量:', placeholderPositions.length);
        console.log('[字段类型映射] 包含is_signature的占位符:', placeholderPositions.filter(p => p.is_signature));
        
        // 存储字段数据到全局变量（避免HTML属性中的JSON解析问题）
        // 使用全局变量，确保事件监听器可以访问
        window.questionnaireFieldsData = {
            taskId: taskId,
            extraPlaceholders: hasExtraPlaceholders ? extraPlaceholders : null,
            unknownFields: unknownFields.length > 0 ? unknownFields : null,
            fieldTypeMap: fieldTypeMap  // 存储字段类型映射
        };
        
        // 创建详情模态框（安全处理任务名称）
        const safeTaskNameForTitle = escapeHtml(task.name || '');
        const modal = createModal(`任务详情 - ${safeTaskNameForTitle}`, `
            <input type="hidden" id="task-detail-id" value="${taskId}">
            <div class="mb-3 d-flex justify-content-between align-items-start">
                <div>
                <p><strong>状态：</strong>${getStatusBadge(task.status)}</p>
                <p><strong>创建时间：</strong>${new Date(task.created_at).toLocaleString('zh-CN')}</p>
                ${task.completed_at ? `<p><strong>完成时间：</strong>${new Date(task.completed_at).toLocaleString('zh-CN')}</p>` : ''}
                <p><strong>教师数量：</strong>${task.teacher_ids.length} 人</p>
                </div>
                <button class="btn btn-sm btn-outline-secondary" onclick="showTaskDetail(${taskId})" title="刷新">
                    <i class="bi bi-arrow-clockwise"></i> 刷新
                </button>
            </div>
            
            ${hasExtraPlaceholders ? `
                <div class="alert alert-info mb-3">
                    <strong>额外占位符：</strong>${extraPlaceholders.join('、')}
                    <br><small>这些占位符需要用户填写，请发起问卷收集信息。</small>
                </div>
                ${!hasQuestionnaire ? `
                    <button class="btn btn-primary mb-3 create-questionnaire-btn" data-type="extra">发起问卷</button>
                ` : ''}
            ` : ''}
            
            ${unknownFields.length > 0 ? `
                <div class="alert alert-warning mb-3">
                    <strong>检测到未知字段：</strong>${unknownFields.join('、')}
                    <br><small>这些字段不在教师数据中，需要发起问卷让教师填写。</small>
                </div>
                ${!hasQuestionnaire && !hasExtraPlaceholders ? `
                    <button class="btn btn-primary mb-3 create-questionnaire-btn" data-type="unknown">发起问卷</button>
                ` : ''}
            ` : ''}
            
            ${hasQuestionnaire ? `
                <div class="card mb-3">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <strong>问卷填写情况</strong>
                        ${task.status === 'pending' || task.status === 'processing' ? `
                            <button class="btn btn-sm btn-success" onclick="completeTaskExport(${taskId})">完成导出</button>
                            ${!allTeachersSubmitted ? `
                                <small class="text-warning d-block mt-1">
                                    <i class="bi bi-exclamation-triangle"></i> 注意：有 ${taskTeachers.length - taskResponses.filter(r => r.submitted_at || r.confirmed_status === 'confirmed').length} 位教师尚未完成填写，导出时将只包含已填写教师的数据
                                </small>
                            ` : ''}
                        ` : ''}
                    </div>
                    <div class="card-body">
                        <div style="max-height: 400px; overflow-y: auto;">
                            <table class="table table-sm">
                                <thead>
                                    <tr>
                                        <th>教师姓名</th>
                                        <th>填写状态</th>
                                        <th>确认状态</th>
                                        <th>填写时间</th>
                                        <th>操作</th>
                                    </tr>
                                </thead>
                                <tbody id="questionnaire-responses-table">
                                    ${taskTeachers.map(teacher => {
                                        const response = taskResponses.find(r => parseInt(r.teacher_id) === teacher.id);
                                        const hasResponse = response && (response.submitted_at || response.confirmed_status === 'confirmed');
                                        const confirmedStatus = response ? (response.confirmed_status || 'pending') : 'pending';
                                        const statusBadge = confirmedStatus === 'confirmed' 
                                            ? '<span class="badge bg-success">已确认</span>' 
                                            : confirmedStatus === 'rejected' 
                                            ? '<span class="badge bg-danger">已拒绝</span>' 
                                            : '<span class="badge bg-warning">待确认</span>';
                                        return `
                                            <tr>
                                                <td>${teacher.name}</td>
                                                <td>${hasResponse ? '<span class="badge bg-success">已填写</span>' : '<span class="badge bg-warning">未填写</span>'}</td>
                                                <td>${statusBadge}</td>
                                                <td>${response && response.submitted_at ? new Date(response.submitted_at).toLocaleString('zh-CN') : '-'}</td>
                                                <td>
                                                    ${response ? `
                                                        <button class="btn btn-sm btn-info" onclick="viewResponse(${response.id})">查看</button>
                                                        <button class="btn btn-sm btn-warning" onclick="editResponseForTeacher(${response.id}, ${teacher.id}, ${questionnaireId})">代填</button>
                                                    ` : `
                                                        <button class="btn btn-sm btn-primary" onclick="fillResponseForTeacher(${teacher.id}, ${questionnaireId})">代填</button>
                                                    `}
                                                </td>
                                            </tr>
                                        `;
                                    }).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            ` : ''}
            
            ${!hasQuestionnaire && (task.status === 'pending' || task.status === 'processing') ? `
                <div class="card mb-3">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <strong>导出任务</strong>
                        <button class="btn btn-sm btn-success" onclick="completeTaskExport(${taskId})">完成导出</button>
                    </div>
                    <div class="card-body">
                        <small class="text-warning">
                            <i class="bi bi-exclamation-triangle"></i> 注意：当前没有问卷，将导出空的ZIP文件
                        </small>
                    </div>
                </div>
            ` : ''}
            
            ${task.status === 'completed' ? `
                <div class="mt-3">
                    <a href="${API_BASE}/tasks/${taskId}/download" class="btn btn-primary">下载导出文件</a>
                </div>
            ` : ''}
        `, null);
        
        document.body.appendChild(modal);
        showModal(modal);
        
        // 绑定发起问卷按钮事件
        const createBtns = modal.querySelectorAll('.create-questionnaire-btn');
        createBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                try {
                    const type = this.getAttribute('data-type');
                    
                    // 从全局变量获取数据
                    const fieldsData = window.questionnaireFieldsData;
                    if (!fieldsData) {
                        alert('数据错误：无法获取字段信息');
                        return;
                    }
                    
                    let fields = null;
                    if (type === 'extra' && fieldsData.extraPlaceholders) {
                        fields = fieldsData.extraPlaceholders;
                    } else if (type === 'unknown' && fieldsData.unknownFields) {
                        fields = fieldsData.unknownFields;
                    }
                    
                    if (!fields || fields.length === 0) {
                        alert('数据错误：无法获取字段信息');
                        return;
                    }
                    
                    // 调试：输出字段类型映射
                    console.log('[创建问卷] 字段列表:', fields);
                    console.log('[创建问卷] 字段类型映射:', fieldsData.fieldTypeMap);
                    
                    // 确保使用全局函数
                    if (typeof window.createQuestionnaireForTask === 'function') {
                        window.createQuestionnaireForTask(fieldsData.taskId, fields);
                    } else {
                        console.error('createQuestionnaireForTask 函数未定义');
                        alert('系统错误：创建问卷功能不可用');
                    }
                } catch (error) {
                    console.error('创建问卷失败:', error);
                    alert('创建问卷失败：' + error.message);
                }
            });
        });
        
    } catch (error) {
        console.error('加载任务详情失败:', error);
        alert('加载失败：' + error.message);
    }
};

// 为任务创建问卷
window.createQuestionnaireForTask = async function(taskId, unknownFields) {
    try {
        // 获取任务信息
        const taskRes = await fetch(`${API_BASE}/tasks/${taskId}`);
        const task = await taskRes.json();
        
        // 从全局变量获取字段类型映射
        const fieldTypeMap = window.questionnaireFieldsData?.fieldTypeMap || {};
        
        // 创建问卷字段
        const fields = unknownFields.map(fieldName => {
            // 检查是否是签名类型
            // 优先使用字段类型映射，然后检查字段名
            const isSignature = fieldTypeMap[fieldName] === 'signature' || 
                               fieldName.includes('签名') || 
                               fieldName.includes('signature');
            
            console.log(`[创建问卷字段] ${fieldName}:`, {
                fieldTypeMapValue: fieldTypeMap[fieldName],
                isSignature: isSignature,
                finalType: isSignature ? "signature" : "text"
            });
            
            return {
            name: fieldName,
            label: fieldName,
                type: isSignature ? "signature" : "text",
            required: true
            };
        });
        
        console.log('[创建问卷] 最终字段列表:', fields);
        
        // 安全地处理任务名称，避免特殊字符导致问题
        const safeTaskName = String(task.name || '').replace(/"/g, '&quot;');
        const data = {
            title: '任务"' + safeTaskName + '"补充信息',
            description: "请填写以下信息",
            fields: fields,
            teacher_ids: task.teacher_ids
        };
        
        const response = await fetch(`${API_BASE}/questionnaires/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            const questionnaire = await response.json();
            
            // 获取教师信息，随机选择一个作为登录示例
            const teachersRes = await fetch(`${API_BASE}/teachers/?limit=10000`);
            const allTeachers = await teachersRes.json();
            const taskTeachers = allTeachers.filter(t => task.teacher_ids.includes(t.id));
            
            let loginExample = '';
            if (taskTeachers.length > 0) {
                const exampleTeacher = taskTeachers[Math.floor(Math.random() * taskTeachers.length)];
                loginExample = `
                    <div class="alert alert-info mt-3">
                        <strong>登录示例：</strong><br>
                        身份证号：<code>${exampleTeacher.id_number || '未设置'}</code><br>
                        手机号：<code>${exampleTeacher.phone || '未设置'}</code><br>
                        <small>您可以使用此账号登录 <a href="/query" target="_blank">查询页面</a> 查看问卷</small>
                    </div>
                `;
            }
            
            alert('问卷创建成功！' + (loginExample ? '\n\n登录示例已显示在任务详情中。' : ''));
            showTaskDetail(taskId);  // 刷新详情
            
            // 显示登录示例（如果任务详情模态框已打开）
            setTimeout(() => {
                const modal = document.querySelector('.modal.show');
                if (modal) {
                    const modalBody = modal.querySelector('.modal-body');
                    if (modalBody && loginExample) {
                        modalBody.insertAdjacentHTML('afterbegin', loginExample);
                    }
                }
            }, 500);
        } else {
            const error = await response.json();
            alert('创建问卷失败：' + (error.detail || '未知错误'));
        }
    } catch (error) {
        console.error('创建问卷失败:', error);
        alert('创建失败：' + error.message);
    }
};

// 查看问卷回答
async function viewResponse(responseId) {
    try {
        const response = await fetch(`${API_BASE}/questionnaires/responses/${responseId}`);
        if (!response.ok) throw new Error('加载失败');
        
        const data = await response.json();
        const answersHtml = Object.entries(data.answers || {}).map(([key, value]) => 
            `<tr><td><strong>${key}</strong></td><td>${escapeHtml(String(value))}</td></tr>`
        ).join('');
        
        const modal = createModal(`查看回答 - ${data.teacher_name}`, `
            <table class="table">
                <thead>
                    <tr>
                        <th>字段</th>
                        <th>值</th>
                    </tr>
                </thead>
                <tbody>
                    ${answersHtml}
                </tbody>
            </table>
            ${data.submitted_at ? `<p class="text-muted">提交时间：${new Date(data.submitted_at).toLocaleString('zh-CN')}</p>` : ''}
        `, null);
        
        document.body.appendChild(modal);
        showModal(modal);
    } catch (error) {
        alert('查看失败：' + error.message);
    }
}

// 代填问卷（为教师填写）
async function fillResponseForTeacher(teacherId, questionnaireId) {
    try {
        // 获取问卷信息
        const questionnaireRes = await fetch(`${API_BASE}/questionnaires/${questionnaireId}`);
        if (!questionnaireRes.ok) throw new Error('加载问卷失败');
        const questionnaire = await questionnaireRes.json();
        
        // 获取教师信息
        const teacherRes = await fetch(`${API_BASE}/teachers/${teacherId}`);
        if (!teacherRes.ok) throw new Error('加载教师信息失败');
        const teacher = await teacherRes.json();
        
        // 创建填写表单
        const fieldsHtml = questionnaire.fields.map(field => {
            // 检查是否是签名类型
            const isSignature = field.type === 'signature' ||
                               (field.name && (field.name.includes('签名') || field.name.includes('signature'))) ||
                               (field.label && (field.label.includes('签名') || field.label.includes('signature')));
            
            if (isSignature) {
                return `
                    <div class="mb-3">
                        <label class="form-label">${field.label}${field.required ? ' *' : ''}</label>
                        <div class="signature-container">
                            <canvas id="signature-canvas-${field.name}" class="signature-canvas" width="400" height="150" style="border: 1px solid #ddd; border-radius: 4px; cursor: crosshair; background: white;"></canvas>
                            <div class="mt-2">
                                <button type="button" class="btn btn-sm btn-outline-secondary" onclick="clearSignature('${field.name}')">清除</button>
                            </div>
                            <input type="hidden" name="${field.name}" id="signature-input-${field.name}" ${field.required ? 'required' : ''} value="">
                        </div>
                    </div>
                `;
            } else {
                return `
            <div class="mb-3">
                <label class="form-label">${field.label}${field.required ? ' *' : ''}</label>
                <input type="text" class="form-control" name="${field.name}" 
                       value="" ${field.required ? 'required' : ''}>
            </div>
                `;
            }
        }).join('');
        
        const modal = createModal(`代填问卷 - ${teacher.name}`, `
            <form id="fill-response-form">
                ${fieldsHtml}
            </form>
        `, async () => {
            const form = document.getElementById('fill-response-form');
            const formData = new FormData(form);
            const answers = {};
            questionnaire.fields.forEach(field => {
                answers[field.name] = formData.get(field.name) || '';
            });
            
            const response = await fetch(`${API_BASE}/questionnaires/responses/`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    questionnaire_id: questionnaireId,
                    teacher_id: teacherId,
                    answers: answers
                })
            });
            
            if (response.ok) {
                alert('保存成功！');
                const bs = getBootstrap();
                if (bs) {
                    const modalInstance = bs.Modal.getInstance(modal);
                if (modalInstance) modalInstance.hide();
                } else {
                    modal.remove();
                }
                // 刷新任务详情
                const taskIdInput = document.getElementById('task-detail-id');
                if (taskIdInput) {
                    showTaskDetail(parseInt(taskIdInput.value));
                }
            } else {
                const error = await response.json();
                alert('保存失败：' + (error.detail || '未知错误'));
            }
        });
        
        document.body.appendChild(modal);
        showModal(modal);
        
        // 初始化签名画板（如果有）
        setTimeout(() => {
            questionnaire.fields.forEach(field => {
                const isSignature = field.type === 'signature' ||
                                   (field.name && (field.name.includes('签名') || field.name.includes('signature'))) ||
                                   (field.label && (field.label.includes('签名') || field.label.includes('signature')));
                if (isSignature) {
                    initSignatureCanvas(field.name);
                }
            });
        }, 100);
        
        // 绑定表单提交事件，阻止默认提交行为
        const form = modal.querySelector('#fill-response-form');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // 触发确认按钮的点击事件
                const confirmBtn = modal.querySelector('.confirm-btn');
                if (confirmBtn) {
                    confirmBtn.click();
                }
            });
        }
        
    } catch (error) {
        alert('代填失败：' + error.message);
    }
}

// 编辑问卷回答（管理员代填）
async function editResponseForTeacher(responseId, teacherId, questionnaireId) {
    try {
        // 获取现有回答
        const responseRes = await fetch(`${API_BASE}/questionnaires/responses/${responseId}`);
        if (!responseRes.ok) throw new Error('加载回答失败');
        const existingResponse = await responseRes.json();
        
        // 获取问卷信息
        const questionnaireRes = await fetch(`${API_BASE}/questionnaires/${questionnaireId}`);
        if (!questionnaireRes.ok) throw new Error('加载问卷失败');
        const questionnaire = await questionnaireRes.json();
        
        // 获取教师信息
        const teacherRes = await fetch(`${API_BASE}/teachers/${teacherId}`);
        if (!teacherRes.ok) throw new Error('加载教师信息失败');
        const teacher = await teacherRes.json();
        
        // 创建编辑表单
        const fieldsHtml = questionnaire.fields.map(field => {
            const value = existingResponse.answers[field.name] || '';
            // 检查是否是签名类型
            const isSignature = field.type === 'signature' ||
                               (field.name && (field.name.includes('签名') || field.name.includes('signature'))) ||
                               (field.label && (field.label.includes('签名') || field.label.includes('signature')));
            
            if (isSignature) {
                const existingValue = value && value.startsWith('data:image') ? value : '';
                return `
                    <div class="mb-3">
                        <label class="form-label">${field.label}${field.required ? ' *' : ''}</label>
                        <div class="signature-container">
                            <canvas id="signature-canvas-${field.name}" class="signature-canvas" width="400" height="150" style="border: 1px solid #ddd; border-radius: 4px; cursor: crosshair; background: white;"></canvas>
                            <div class="mt-2">
                                <button type="button" class="btn btn-sm btn-outline-secondary" onclick="clearSignature('${field.name}')">清除</button>
                            </div>
                            <input type="hidden" name="${field.name}" id="signature-input-${field.name}" ${field.required ? 'required' : ''} value="${existingValue}">
                            ${existingValue ? `
                                <div class="mt-2">
                                    <img src="${existingValue}" alt="已保存的签名" style="max-width: 400px; border: 1px solid #ddd; border-radius: 4px;">
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            } else {
            return `
                <div class="mb-3">
                    <label class="form-label">${field.label}${field.required ? ' *' : ''}</label>
                    <input type="text" class="form-control" name="${field.name}" 
                           value="${escapeHtml(String(value))}" ${field.required ? 'required' : ''}>
                </div>
            `;
            }
        }).join('');
        
        const modal = createModal(`编辑回答 - ${teacher.name}`, `
            <form id="edit-response-form">
                ${fieldsHtml}
            </form>
        `, async () => {
            const form = document.getElementById('edit-response-form');
            const formData = new FormData(form);
            const answers = {};
            questionnaire.fields.forEach(field => {
                answers[field.name] = formData.get(field.name) || '';
            });
            
            const response = await fetch(`${API_BASE}/questionnaires/responses/${responseId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    answers: answers
                })
            });
            
            if (response.ok) {
                alert('保存成功！');
                const bs = getBootstrap();
                if (bs) {
                    const modalInstance = bs.Modal.getInstance(modal);
                if (modalInstance) modalInstance.hide();
                } else {
                    modal.remove();
                }
                // 刷新任务详情
                const taskIdInput = document.getElementById('task-detail-id');
                if (taskIdInput) {
                    showTaskDetail(parseInt(taskIdInput.value));
                }
            } else {
                const error = await response.json();
                alert('保存失败：' + (error.detail || '未知错误'));
            }
        });
        
        document.body.appendChild(modal);
        showModal(modal);
        
        // 初始化签名画板（如果有）
        setTimeout(() => {
            questionnaire.fields.forEach(field => {
                const isSignature = field.type === 'signature' ||
                                   (field.name && (field.name.includes('签名') || field.name.includes('signature'))) ||
                                   (field.label && (field.label.includes('签名') || field.label.includes('signature')));
                if (isSignature) {
                    initSignatureCanvas(field.name);
                    // 如果有已保存的签名，显示在画板上
                    const existingValue = existingResponse.answers[field.name] || '';
                    if (existingValue && existingValue.startsWith('data:image')) {
                        const img = new Image();
                        img.onload = function() {
                            if (window.signatureCanvases && window.signatureCanvases[field.name] && 
                                window.signatureContexts && window.signatureContexts[field.name]) {
                                const canvas = window.signatureCanvases[field.name];
                                const ctx = window.signatureContexts[field.name];
                                ctx.drawImage(img, 0, 0);
                            }
                        };
                        img.src = existingValue;
                    }
                }
            });
        }, 100);
        
        // 绑定表单提交事件，阻止默认提交行为
        const form = modal.querySelector('#edit-response-form');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                e.stopPropagation();
                // 自动保存签名到输入框（如果有签名字段）
                questionnaire.fields.forEach(field => {
                    const isSignature = field.type === 'signature' ||
                                       (field.name && (field.name.includes('签名') || field.name.includes('signature'))) ||
                                       (field.label && (field.label.includes('签名') || field.label.includes('signature')));
                    if (isSignature) {
                        const canvas = window.signatureCanvases && window.signatureCanvases[field.name];
                        const input = document.getElementById(`signature-input-${field.name}`);
                        if (canvas && input) {
                            const dataURL = canvas.toDataURL('image/png');
                            input.value = dataURL;
                        }
                    }
                });
                // 触发确认按钮的点击事件
                const confirmBtn = modal.querySelector('.confirm-btn');
                if (confirmBtn) {
                    confirmBtn.click();
                }
            });
        }
        
    } catch (error) {
        alert('编辑失败：' + error.message);
    }
}

// 处理任务列表按钮点击（事件委托）
function handleTaskListClick(e) {
    // 处理删除按钮
    if (e.target.classList.contains('delete-task-btn') || e.target.closest('.delete-task-btn')) {
        const btn = e.target.classList.contains('delete-task-btn') ? e.target : e.target.closest('.delete-task-btn');
        const taskId = parseInt(btn.getAttribute('data-task-id'));
        const taskName = btn.getAttribute('data-task-name');
        if (taskId && taskName) {
            // 确保使用全局函数
            if (typeof window.deleteTask === 'function') {
                window.deleteTask(taskId, taskName);
            } else {
                console.error('deleteTask 函数未定义');
                alert('系统错误：删除功能不可用');
            }
        }
        e.stopPropagation();
        return;
    }
    
    // 处理查看详情按钮
    if (e.target.classList.contains('show-task-detail-btn') || e.target.closest('.show-task-detail-btn')) {
        const btn = e.target.classList.contains('show-task-detail-btn') ? e.target : e.target.closest('.show-task-detail-btn');
        const taskId = parseInt(btn.getAttribute('data-task-id'));
        if (taskId) {
            // 确保使用全局函数
            if (typeof window.showTaskDetail === 'function') {
                window.showTaskDetail(taskId);
            } else {
                console.error('showTaskDetail 函数未定义');
                alert('系统错误：查看详情功能不可用');
            }
        }
        e.stopPropagation();
        return;
    }
}

// 删除任务（设置为全局函数）
window.deleteTask = async function(id, name) {
    // 安全地处理任务名称，避免特殊字符导致语法错误
    const safeName = String(name || '').replace(/"/g, '&quot;').replace(/\n/g, ' ');
    if (!confirm('确定要删除任务"' + safeName + '"吗？\n\n注意：删除任务将同时删除相关的导出文件（如果存在）。')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // 检查响应是否有内容
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                try {
                    const data = await response.json();
                    // 如果有消息，显示它
                    if (data.message) {
                        alert(data.message);
                    } else {
                        alert('删除成功！');
                    }
                } catch (e) {
                    // JSON解析失败，但状态码是200，认为删除成功
                    alert('删除成功！');
                }
            } else {
                alert('删除成功！');
            }
            loadTasks();
        } else {
            // 处理错误响应
            let errorMsg = '删除失败：';
            try {
                const error = await response.json();
                errorMsg += error.detail || error.message || `HTTP ${response.status}`;
            } catch (e) {
                // 如果响应不是JSON，使用状态文本
                errorMsg += `HTTP ${response.status}: ${response.statusText || '未知错误'}`;
            }
            alert(errorMsg);
        }
    } catch (error) {
        console.error('删除任务错误:', error);
        alert('删除失败：' + (error.message || String(error)));
    }
};

function showCreateTaskModal() {
    // 需要先加载模板和教师列表
    Promise.all([
        fetch(`${API_BASE}/templates/`).then(r => r.json()),
        fetch(`${API_BASE}/teachers/?limit=10000`).then(r => r.json())
    ]).then(([templates, teachers]) => {
        const modal = createModal('创建填报任务', `
            <form id="task-form">
                <div class="mb-3">
                    <label class="form-label">任务名称 *</label>
                    <input type="text" class="form-control" name="name" value="未命名" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">选择模板 *</label>
                    <select class="form-select" name="template_id" required>
                        ${templates.length > 0 ? templates.map((t, index) => `<option value="${t.id}" ${index === 0 ? 'selected' : ''}>${t.name}</option>`).join('') : '<option value="">请选择</option>'}
                    </select>
                </div>
                <div class="mb-3">
                    <label class="form-label">选择教师 *</label>
                    <div class="mb-2">
                        <label class="form-label small">快速选择（每行一个姓名）</label>
                        <textarea class="form-control" id="teacher-batch-input" rows="4" placeholder="请输入教师姓名，每行一个，例如：&#10;张三&#10;李四&#10;王五"></textarea>
                        <button type="button" class="btn btn-sm btn-success mt-1" onclick="batchSelectTeachers()">批量匹配并选中</button>
                        <small class="text-muted d-block mt-1">输入教师姓名后点击按钮，系统会自动匹配并选中对应的教师</small>
                    </div>
                    <div class="mb-2">
                        <label class="form-label small">搜索筛选</label>
                        <input type="text" class="form-control" id="teacher-search" placeholder="搜索教师（姓名/手机号/身份证号）" oninput="filterTeachers(this.value)">
                    </div>
                    <div class="mb-2">
                        <button type="button" class="btn btn-sm btn-outline-primary" onclick="selectAllTeachers()">全选</button>
                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="deselectAllTeachers()">全不选</button>
                        <button type="button" class="btn btn-sm btn-outline-info" onclick="invertSelectionTeachers()">反选</button>
                        <span class="ms-2 text-muted" id="teacher-count">已选择: 0</span>
                    </div>
                    <div id="batch-match-result" class="alert" style="display: none;"></div>
                    <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 4px;" id="teacher-list">
                        ${teachers.map(t => `
                            <div class="form-check teacher-item" data-name="${t.name}" data-phone="${t.phone || ''}" data-id-number="${t.id_number || ''}">
                                <input class="form-check-input teacher-checkbox" type="checkbox" name="teacher_ids" value="${t.id}" id="teacher-${t.id}" onchange="updateTeacherCount()">
                                <label class="form-check-label" for="teacher-${t.id}">
                                    ${t.name} ${t.department ? `(${t.department})` : ''}
                                </label>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </form>
        `, async () => {
            const form = document.getElementById('task-form');
            
            // 验证表单
            if (!form.name.value || !form.name.value.trim()) {
                alert('请输入任务名称');
                return;
            }
            
            const templateId = parseInt(form.template_id.value);
            if (!templateId || isNaN(templateId)) {
                alert('请选择模板');
                return;
            }
            
            const teacherIds = Array.from(document.querySelectorAll('.teacher-checkbox:checked'))
                .map(cb => {
                    const id = parseInt(cb.value);
                    return isNaN(id) ? null : id;
                })
                .filter(id => id !== null);
            
            if (teacherIds.length === 0) {
                alert('请至少选择一个教师');
                return;
            }
            
            // 确保所有数据格式正确
            const data = {
                name: form.name.value.trim(),
                template_id: templateId,
                teacher_ids: teacherIds
            };
            
            // 验证数据
            if (!data.name) {
                alert('任务名称不能为空');
                return;
            }
            if (!data.template_id || isNaN(data.template_id)) {
                alert('请选择有效的模板');
                return;
            }
            if (!Array.isArray(data.teacher_ids) || data.teacher_ids.length === 0) {
                alert('请至少选择一个教师');
                return;
            }
            // 确保所有teacher_ids都是整数
            const invalidIds = data.teacher_ids.filter(id => !Number.isInteger(id));
            if (invalidIds.length > 0) {
                console.error('无效的教师ID:', invalidIds);
                alert('教师ID格式错误，请刷新页面重试');
                return;
            }
            
            console.log('创建任务，发送数据:', data);
            console.log('数据验证:', {
                name: typeof data.name, nameLength: data.name.length,
                template_id: typeof data.template_id, template_idValue: data.template_id,
                teacher_ids: Array.isArray(data.teacher_ids), teacher_idsLength: data.teacher_ids.length,
                teacher_idsTypes: data.teacher_ids.map(id => typeof id)
            });
            
            try {
                const response = await fetch(`${API_BASE}/tasks/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Admin-Token': localStorage.getItem('admin_token') || ''
                    },
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    alert('任务创建成功！正在后台处理...');
                    loadTasks();
                    const bs = getBootstrap();
                if (bs) {
                    const modalElement = document.querySelector('.modal');
                    if (modalElement) {
                        const modalInstance = bs.Modal.getInstance(modalElement);
                        if (modalInstance) {
                            modalInstance.hide();
                        }
                    }
                }
                } else {
                    const errorData = await response.json();
                    console.error('创建任务失败:', response.status, errorData);
                    
                    // 显示详细的错误信息
                    let errorMsg = '创建失败：';
                    if (errorData.detail) {
                        if (Array.isArray(errorData.detail)) {
                            // Pydantic验证错误
                            errorMsg += errorData.detail.map(e => {
                                const loc = e.loc ? e.loc.join('.') : '';
                                return `${loc}: ${e.msg}`;
                            }).join('\n');
                        } else {
                            errorMsg += errorData.detail;
                        }
                    } else {
                        errorMsg += `HTTP ${response.status}`;
                    }
                    alert(errorMsg);
                }
            } catch (error) {
                console.error('创建任务异常:', error);
                alert('创建失败：' + error.message);
            }
        });
        document.body.appendChild(modal);
        const bs = getBootstrap();
        if (bs) {
            const modalInstance = new bs.Modal(modal);
            modalInstance.show();
            // 初始化计数
            setTimeout(() => updateTeacherCount(), 100);
        } else {
            modal.style.display = 'block';
            modal.classList.add('show');
            document.body.classList.add('modal-open');
            setTimeout(() => updateTeacherCount(), 100);
        }
        
        // 确保默认值正确应用（在模态框显示后）
        setTimeout(() => {
            const nameInput = modal.querySelector('input[name="name"]');
            if (nameInput) {
                nameInput.value = '未命名';
            }
            const templateSelect = modal.querySelector('select[name="template_id"]');
            if (templateSelect && templates.length > 0) {
                // 确保第一个模板被选中（移除所有选中状态，选中第一个模板）
                templateSelect.querySelectorAll('option').forEach(opt => opt.selected = false);
                const firstTemplateOption = templateSelect.querySelector('option[value]:not([value=""])');
                if (firstTemplateOption) {
                    firstTemplateOption.selected = true;
                    // 触发change事件，确保值被正确设置
                    templateSelect.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        }, 200);
    });
}

// ========== 问卷系统 ==========
async function loadQuestionnaires() {
    try {
        const response = await fetch(`${API_BASE}/questionnaires/`);
        const questionnaires = await response.json();
        const list = document.getElementById('questionnaires-list');
        if (questionnaires.length === 0) {
            list.innerHTML = '<div class="text-center text-muted">暂无问卷</div>';
        } else {
            list.innerHTML = questionnaires.map(q => `
                <div class="card mb-3">
                    <div class="card-body">
                        <h5 class="card-title">${q.title}</h5>
                        <p class="card-text">${q.description || ''}</p>
                        <p class="text-muted">状态: ${getStatusBadge(q.status)}</p>
                        <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-primary" onclick="viewQuestionnaire(${q.id})">查看</button>
                            <button class="btn btn-sm btn-info" onclick="showShareLink(${q.id})">
                                <i class="bi bi-link-45deg"></i> 生成分享链接
                            </button>
                        ${q.status === 'active' ? `
                            <button class="btn btn-sm btn-secondary" onclick="closeQuestionnaire(${q.id})">关闭</button>
                        ` : ''}
                        </div>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('加载问卷列表失败:', error);
        document.getElementById('questionnaires-list').innerHTML = '<div class="text-center text-danger">加载失败</div>';
    }
}

function showCreateQuestionnaireModal() {
    // 需要先加载教师列表
    fetch(`${API_BASE}/teachers/?limit=10000`).then(r => r.json()).then(teachers => {
        const modal = createModal('创建问卷', `
            <form id="questionnaire-form">
                <div class="mb-3">
                    <label class="form-label">问卷标题 *</label>
                    <input type="text" class="form-control" name="title" value="未命名" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">问卷描述</label>
                    <textarea class="form-control" name="description" rows="3"></textarea>
                </div>
                <div class="mb-3">
                    <label class="form-label">选择教师 *</label>
                    <div style="max-height: 200px; overflow-y: auto; border: 1px solid #ddd; padding: 10px;">
                        ${teachers.map(t => `
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" name="teacher_ids" value="${t.id}" id="q-teacher-${t.id}">
                                <label class="form-check-label" for="q-teacher-${t.id}">${t.name}</label>
                            </div>
                        `).join('')}
                    </div>
                </div>
                <div class="mb-3">
                    <label class="form-label">字段定义（JSON格式）*</label>
                    <textarea class="form-control" name="fields" rows="5" required placeholder='[{"name":"field1","label":"字段1","type":"text","required":true}]'></textarea>
                    <small class="form-text text-muted">字段类型：text, number, select, date等</small>
                </div>
            </form>
        `, async () => {
            const form = document.getElementById('questionnaire-form');
            const teacherIds = Array.from(form.querySelectorAll('input[name="teacher_ids"]:checked')).map(cb => parseInt(cb.value));
            
            if (teacherIds.length === 0) {
                alert('请至少选择一个教师');
                return;
            }
            
            try {
                const fields = JSON.parse(form.fields.value);
                const data = {
                    title: form.title.value,
                    description: form.description.value,
                    fields: fields,
                    teacher_ids: teacherIds
                };
                
                const response = await fetch(`${API_BASE}/questionnaires/`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                if (response.ok) {
                    alert('问卷创建成功！');
                    loadQuestionnaires();
                    const bs = getBootstrap();
                if (bs) {
                    const modalElement = document.querySelector('.modal');
                    if (modalElement) {
                        const modalInstance = bs.Modal.getInstance(modalElement);
                        if (modalInstance) {
                            modalInstance.hide();
                        }
                    }
                }
                } else {
                    alert('创建失败：' + (await response.json()).detail);
                }
            } catch (error) {
                alert('创建失败：' + error.message);
            }
        });
        document.body.appendChild(modal);
        showModal(modal);
    });
}

async function viewQuestionnaire(id) {
    try {
        const [questionnaireRes, responsesRes] = await Promise.all([
            fetch(`${API_BASE}/questionnaires/${id}`).then(r => r.json()),
            fetch(`${API_BASE}/questionnaires/${id}/responses`).then(r => r.json())
        ]);
        
        const questionnaire = questionnaireRes;
        const responses = responsesRes;
        
        // 统计确认状态
        const confirmedCount = responses.filter(r => r.confirmed_status === 'confirmed').length;
        const rejectedCount = responses.filter(r => r.confirmed_status === 'rejected').length;
        const pendingCount = responses.filter(r => !r.confirmed_status || r.confirmed_status === 'pending').length;
        
        const modal = createModal(`问卷详情 - ${questionnaire.title}`, `
            <div class="mb-3">
                <p><strong>描述：</strong>${questionnaire.description || '无'}</p>
                <p><strong>创建时间：</strong>${new Date(questionnaire.created_at).toLocaleString('zh-CN')}</p>
                ${questionnaire.deadline ? `<p><strong>截止时间：</strong>${new Date(questionnaire.deadline).toLocaleString('zh-CN')}</p>` : ''}
            </div>
            
            <div class="mb-3">
                <h6>确认状态统计</h6>
                <div class="d-flex gap-3">
                    <span class="badge bg-success">已确认: ${confirmedCount}</span>
                    <span class="badge bg-danger">信息有误: ${rejectedCount}</span>
                    <span class="badge bg-warning">待确认: ${pendingCount}</span>
                </div>
            </div>
            
            <div class="mb-3">
                <h6>教师回答列表</h6>
                <div style="max-height: 400px; overflow-y: auto;">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>教师姓名</th>
                                <th>提交时间</th>
                                <th>审核状态</th>
                                <th>确认状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${responses.map(r => `
                                <tr>
                                    <td>${r.teacher_name}</td>
                                    <td>${new Date(r.submitted_at).toLocaleString('zh-CN')}</td>
                                    <td>${getStatusBadge(r.status)}</td>
                                    <td>${getConfirmedStatusBadge(r.confirmed_status)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `, null);
        
        document.body.appendChild(modal);
        showModal(modal);
    } catch (error) {
        alert('加载问卷详情失败：' + error.message);
        console.error(error);
    }
}

async function showShareLink(questionnaireId) {
    try {
        const response = await fetch(`${API_BASE}/questionnaires/${questionnaireId}/share-link`);
        const data = await response.json();
        
        // 生成完整URL
        const baseUrl = window.location.origin;
        const fullUrl = baseUrl + data.share_url;
        
        const modal = createModal('分享链接', `
            <div class="mb-3">
                <label class="form-label">分享链接（点击复制）</label>
                <div class="input-group">
                    <input type="text" class="form-control" id="share-url-input" value="${fullUrl}" readonly>
                    <button class="btn btn-outline-secondary" type="button" onclick="copyShareLink()">
                        <i class="bi bi-clipboard"></i> 复制
                    </button>
                </div>
                <small class="form-text text-muted">教师可以通过此链接输入身份证号和手机号查看并确认问卷信息</small>
            </div>
            <div class="alert alert-info">
                <i class="bi bi-info-circle"></i> 请将此链接发送给相关教师，教师需要输入身份证号和手机号进行身份验证
            </div>
        `, null);
        
        document.body.appendChild(modal);
        showModal(modal);
    } catch (error) {
        alert('获取分享链接失败：' + error.message);
    }
}

function copyShareLink() {
    const input = document.getElementById('share-url-input');
    input.select();
    input.setSelectionRange(0, 99999); // 移动端支持
    document.execCommand('copy');
    alert('链接已复制到剪贴板！');
}

function getConfirmedStatusBadge(status) {
    if (!status || status === 'pending') {
        return '<span class="badge bg-warning">待确认</span>';
    } else if (status === 'confirmed') {
        return '<span class="badge bg-success">已确认</span>';
    } else if (status === 'rejected') {
        return '<span class="badge bg-danger">信息有误</span>';
    }
    return status;
}

async function closeQuestionnaire(id) {
    if (!confirm('确定要关闭这个问卷吗？')) return;
    try {
        const response = await fetch(`${API_BASE}/questionnaires/${id}/close`, {method: 'PUT'});
        if (response.ok) {
            alert('问卷已关闭');
            loadQuestionnaires();
        }
    } catch (error) {
        alert('操作失败：' + error.message);
    }
}

function useTemplate(id) {
    // 跳转到创建任务页面，并预选模板
    switchPage('tasks');
    // 可以在这里预填充模板选择
    setTimeout(() => {
        showCreateTaskModal();
    }, 100);
}

async function deleteTemplate(id) {
    try {
        // 先查询关联的任务
        const relatedResponse = await fetch(`${API_BASE}/templates/${id}/related-tasks`);
        let relatedTasks = [];
        let templateName = '';
        
        if (relatedResponse.ok) {
            const relatedData = await relatedResponse.json();
            relatedTasks = relatedData.related_tasks || [];
            templateName = relatedData.template_name || '';
        }
        
        // 构建确认消息
        let confirmMessage = `确定要删除模板"${templateName || '此模板'}"吗？`;
        if (relatedTasks.length > 0) {
            confirmMessage += `\n\n⚠️ 警告：此模板关联了 ${relatedTasks.length} 个任务，删除模板将同时删除以下任务：\n\n`;
            relatedTasks.forEach((task, index) => {
                confirmMessage += `${index + 1}. ${task.name} (状态: ${task.status === 'completed' ? '已完成' : '待处理'})\n`;
            });
            confirmMessage += '\n此操作不可撤销！';
        } else {
            confirmMessage += '\n\n此操作不可撤销！';
        }
        
        if (!confirm(confirmMessage)) {
            return;
        }
        
        // 执行删除
        const response = await fetch(`${API_BASE}/templates/${id}`, {method: 'DELETE'});
        if (response.ok) {
            const result = await response.json();
            alert(result.message || '删除成功！');
            loadTemplates();
            // 如果有关联任务，也刷新任务列表
            if (relatedTasks.length > 0) {
                loadTasks();
            }
        } else {
            const error = await response.json();
            alert('删除失败：' + (error.detail || '未知错误'));
        }
    } catch (error) {
        console.error('删除模板错误:', error);
        alert('删除失败：' + (error.message || String(error)));
    }
}

// 教师选择辅助函数
function filterTeachers(searchText) {
    const items = document.querySelectorAll('.teacher-item');
    const searchLower = searchText.toLowerCase();
    items.forEach(item => {
        const name = item.dataset.name.toLowerCase();
        const phone = (item.dataset.phone || '').toLowerCase();
        const idNumber = (item.dataset.idNumber || '').toLowerCase();
        const matches = name.includes(searchLower) || phone.includes(searchLower) || idNumber.includes(searchLower);
        item.style.display = matches ? '' : 'none';
    });
    updateTeacherCount();
}

function selectAllTeachers() {
    document.querySelectorAll('.teacher-item:not([style*="display: none"]) .teacher-checkbox').forEach(cb => {
        cb.checked = true;
    });
    updateTeacherCount();
}

function deselectAllTeachers() {
    document.querySelectorAll('.teacher-checkbox').forEach(cb => {
        cb.checked = false;
    });
    updateTeacherCount();
}

function invertSelectionTeachers() {
    document.querySelectorAll('.teacher-item:not([style*="display: none"]) .teacher-checkbox').forEach(cb => {
        cb.checked = !cb.checked;
    });
    updateTeacherCount();
}

function updateTeacherCount() {
    const count = document.querySelectorAll('.teacher-checkbox:checked').length;
    const countEl = document.getElementById('teacher-count');
    if (countEl) {
        countEl.textContent = `已选择: ${count}`;
    }
}

// 批量匹配并选中教师
function batchSelectTeachers() {
    const textarea = document.getElementById('teacher-batch-input');
    const resultDiv = document.getElementById('batch-match-result');
    
    if (!textarea || !resultDiv) return;
    
    const inputText = textarea.value.trim();
    if (!inputText) {
        resultDiv.className = 'alert alert-warning';
        resultDiv.textContent = '请输入教师姓名';
        resultDiv.style.display = 'block';
        setTimeout(() => {
            resultDiv.style.display = 'none';
        }, 3000);
        return;
    }
    
    // 按行分割，去除空行和首尾空格
    const names = inputText.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);
    
    if (names.length === 0) {
        resultDiv.className = 'alert alert-warning';
        resultDiv.textContent = '请输入至少一个教师姓名';
        resultDiv.style.display = 'block';
        setTimeout(() => {
            resultDiv.style.display = 'none';
        }, 3000);
        return;
    }
    
    // 获取所有教师项
    const teacherItems = document.querySelectorAll('.teacher-item');
    const matchedNames = [];
    const notFoundNames = [];
    
    // 先全不选
    deselectAllTeachers();
    
    // 遍历输入的每个姓名
    names.forEach(inputName => {
        let found = false;
        
        // 精准匹配（完全匹配）
        teacherItems.forEach(item => {
            const teacherName = item.dataset.name.trim();
            if (teacherName === inputName) {
                const checkbox = item.querySelector('.teacher-checkbox');
                if (checkbox && !checkbox.checked) {
                    checkbox.checked = true;
                    found = true;
                }
            }
        });
        
        if (found) {
            matchedNames.push(inputName);
        } else {
            notFoundNames.push(inputName);
        }
    });
    
    // 更新计数
    updateTeacherCount();
    
    // 显示结果
    let resultHtml = '';
    if (matchedNames.length > 0) {
        resultHtml += `<strong>成功匹配 ${matchedNames.length} 个：</strong>${matchedNames.join('、')}`;
    }
    if (notFoundNames.length > 0) {
        resultHtml += `<br><strong class="text-danger">未找到 ${notFoundNames.length} 个：</strong>${notFoundNames.join('、')}`;
        resultDiv.className = 'alert alert-warning';
    } else {
        resultDiv.className = 'alert alert-success';
    }
    
    resultDiv.innerHTML = resultHtml;
    resultDiv.style.display = 'block';
    
    // 5秒后自动隐藏
    setTimeout(() => {
        resultDiv.style.display = 'none';
    }, 5000);
}

// 编辑模板占位符 - PDF文件：拖动选择位置添加占位符
async function editTemplatePlaceholders(templateId) {
    try {
        // 加载模板信息和可用字段
        const [templateResponse, fieldsResponse] = await Promise.all([
            fetch(`${API_BASE}/templates/${templateId}`),
            fetch(`${API_BASE}/templates/available-fields`)
        ]);
        
        // 检查响应状态
        if (!templateResponse.ok) {
            let errorMsg = '加载模板信息失败';
            try {
                const error = await templateResponse.json();
                errorMsg = error.detail || error.message || errorMsg;
            } catch (e) {
                errorMsg = `HTTP ${templateResponse.status}: ${templateResponse.statusText}`;
            }
            throw new Error(errorMsg);
        }
        
        if (!fieldsResponse.ok) {
            let errorMsg = '加载可用字段失败';
            try {
                const error = await fieldsResponse.json();
                errorMsg = error.detail || error.message || errorMsg;
            } catch (e) {
                errorMsg = `HTTP ${fieldsResponse.status}: ${fieldsResponse.statusText}`;
            }
            throw new Error(errorMsg);
        }
        
        let template, fieldsRes;
        try {
            template = await templateResponse.json();
            fieldsRes = await fieldsResponse.json();
        } catch (e) {
            console.error('JSON解析错误:', e);
            throw new Error('解析响应数据失败：' + (e.message || String(e)));
        }
        
        // 检查模板数据
        if (!template || !template.id) {
            console.error('模板数据格式错误:', template);
            throw new Error('模板数据格式错误，缺少id字段');
        }
        
        // 检查是否为PDF文件
        if (template.file_type !== '.pdf') {
            alert('当前只支持PDF文件模板');
            return;
        }
        
        // 检查数据格式
        if (!fieldsRes || !fieldsRes.all_fields || !Array.isArray(fieldsRes.all_fields)) {
            console.error('可用字段数据格式错误:', fieldsRes);
            throw new Error('可用字段数据格式错误');
        }
        
        const fields = fieldsRes.all_fields;
        
        // 获取PDF信息
        let pdfInfo;
        try {
            const pdfInfoResponse = await fetch(`${API_BASE}/templates/${templateId}/content`);
            if (pdfInfoResponse.ok) {
                pdfInfo = await pdfInfoResponse.json();
            }
        } catch (e) {
            console.error('获取PDF信息失败:', e);
        }
        
        const numPages = pdfInfo?.num_pages || 1;
        const pageWidth = pdfInfo?.page_width || 595;
        const pageHeight = pdfInfo?.page_height || 842;
        
        // 获取已有的占位符位置
        const existingPositions = template.placeholder_positions || [];
        
        // 按分类组织字段
        const fieldsByCategory = {};
        if (fields && Array.isArray(fields)) {
            fields.forEach(field => {
                if (!fieldsByCategory[field.category]) {
                    fieldsByCategory[field.category] = [];
                }
                fieldsByCategory[field.category].push(field);
            });
        }
        
        // 生成PDF编辑界面
        const placeholderPositions = existingPositions;
        
        // 创建PDF编辑界面HTML
        const pdfContentHtml = `
            <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
                <div class="mb-2 d-flex justify-content-between align-items-center">
                    <div>
                        <strong>编辑PDF模板 - ${template.name}</strong>
                        <small class="text-muted ms-2">拖动选择位置，然后点击右侧变量添加占位符</small>
                    </div>
                    <div>
                        <label class="me-2">页码：</label>
                        <select id="pdf-page-select" class="form-select form-select-sm" style="width: auto; display: inline-block;">
                            ${Array.from({length: numPages}, (_, i) => `
                                <option value="${i}">第 ${i + 1} 页</option>
                            `).join('')}
                        </select>
                    </div>
                </div>
                <div id="pdf-container" style="flex: 1; overflow: auto; border: 1px solid #ddd; border-radius: 4px; background: #f5f5f5; position: relative;">
                    <div id="pdf-viewer" style="position: relative; margin: 20px auto; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <canvas id="pdf-canvas" style="max-width: 100%; height: auto; display: block;"></canvas>
                        <div id="placeholder-markers"></div>
                        <div id="pdf-loading" class="text-center p-4">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">加载中...</span>
                            </div>
                            <p class="mt-2">正在加载PDF...</p>
                        </div>
                    </div>
                </div>
                <div class="mt-2">
                    <button class="btn btn-sm btn-outline-danger" onclick="clearAllPlaceholders()">清除所有占位符</button>
                    <small class="text-muted ms-2">已添加 ${placeholderPositions.length} 个占位符</small>
                </div>
            </div>
        `;
        
        // 创建编辑界面
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = `pdf-editor-modal-${templateId}`;
        modal.style.zIndex = '9999';
        modal.innerHTML = `
            <div class="modal-dialog modal-xl" style="max-width: 95vw;">
                <div class="modal-content" style="height: 90vh;">
                    <div class="modal-header">
                        <h5 class="modal-title">编辑PDF模板占位符 - ${template.name}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="overflow: hidden; display: flex; flex-direction: column; height: calc(90vh - 120px);">
                        <div style="display: flex; gap: 15px; flex: 1; overflow: hidden;">
                            <!-- 左侧：PDF编辑器 -->
                            ${pdfContentHtml}
                            
                            <!-- 右侧：变量列表 -->
                            <div style="width: 300px; display: flex; flex-direction: column; border-left: 1px solid #ddd; padding-left: 15px;">
                                <div class="mb-2">
                                    <strong>可用变量</strong>
                                    <small class="text-muted d-block">拖动选择位置后，点击变量添加占位符</small>
                                </div>
                                <div style="flex: 1; overflow-y: auto;">
                                    ${Object.keys(fieldsByCategory).length > 0 ? Object.keys(fieldsByCategory).map(category => {
                                        const categoryFields = fieldsByCategory[category];
                                        if (!categoryFields || !Array.isArray(categoryFields) || categoryFields.length === 0) {
                                            return '';
                                        }
                                        return `
                                            <div class="mb-3">
                                                <h6 style="color: #666; font-size: 0.9em; margin-bottom: 8px;">${category}</h6>
                                                <div class="d-flex flex-wrap gap-2">
                                                    ${categoryFields.map(field => `
                                                        <button class="btn btn-sm btn-outline-info variable-btn" 
                                                                title="${field.label || field.name || ''}"
                                                                style="font-size: 0.85em;">
                                                            ${field.label || field.name || ''}
                                                        </button>
                                                    `).join('')}
                                                </div>
                                            </div>
                                        `;
                                    }).join('') : '<div class="alert alert-warning">暂无可用字段</div>'}
                                </div>
                                <div class="mt-2 p-2 bg-light rounded">
                                    <small class="text-muted">
                                        <strong>提示：</strong><br>
                                        1. 在PDF上拖动选择位置<br>
                                        2. 在弹出的对话框中选择变量<br>
                                        3. 占位符会显示在PDF上<br>
                                        4. 点击占位符标记可删除
                                    </small>
                                </div>
                            </div>
                            
                            <!-- 右侧：变量列表 -->
                            <div style="width: 300px; display: flex; flex-direction: column; border-left: 1px solid #ddd; padding-left: 15px;">
                                <div class="mb-2">
                                    <strong>可用变量</strong>
                                    <small class="text-muted d-block">点击变量插入到当前位置</small>
                                </div>
                                <div style="flex: 1; overflow-y: auto;">
                                    ${Object.keys(fieldsByCategory).length > 0 ? Object.keys(fieldsByCategory).map(category => {
                                        const categoryFields = fieldsByCategory[category];
                                        if (!categoryFields || !Array.isArray(categoryFields) || categoryFields.length === 0) {
                                            return '';
                                        }
                                        return `
                                            <div class="mb-3">
                                                <h6 style="color: #666; font-size: 0.9em; margin-bottom: 8px;">${category}</h6>
                                                <div class="d-flex flex-wrap gap-2">
                                                    ${categoryFields.map(field => `
                                                        <button class="btn btn-sm btn-outline-info variable-btn" 
                                                                onclick="insertVariable('{{${field.name || ''}}}')"
                                                                title="${field.label || field.name || ''}"
                                                                style="font-size: 0.85em;">
                                                            ${field.label || field.name || ''}
                                                        </button>
                                                    `).join('')}
                                                </div>
                                            </div>
                                        `;
                                    }).join('') : '<div class="alert alert-warning">暂无可用字段</div>'}
                                </div>
                                <div class="mt-2 p-2 bg-light rounded">
                                    <small class="text-muted">
                                        <strong>提示：</strong><br>
                                        1. 点击内容进行编辑<br>
                                        2. 点击右侧变量按钮插入占位符<br>
                                        3. 占位符格式：{{字段名}}
                                    </small>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" onclick="savePDFPlaceholderPositions(${templateId})">保存占位符位置</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // PDF编辑相关全局变量
        window.pdfEditorData = window.pdfEditorData || {};
        window.pdfEditorData[templateId] = {
            positions: [...placeholderPositions],
            pageWidth: pageWidth,
            pageHeight: pageHeight,
            currentPage: 0,
            scale: 1
        };
        
        // 初始化PDF编辑器 - 使用PDF.js
        window.initPDFEditor = async function(templateId, pdfWidth, pdfHeight) {
            const canvas = document.getElementById('pdf-canvas');
            const loadingDiv = document.getElementById('pdf-loading');
            if (!canvas) return;
            
            // 检查PDF.js是否可用
            if (typeof pdfjsLib === 'undefined') {
                loadingDiv.innerHTML = '<div class="alert alert-danger">PDF.js未加载，请刷新页面重试</div>';
                return;
            }
            
            try {
                // 设置PDF.js worker（使用本地文件）
                pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/js/pdf.worker.min.js';
                
                // 加载PDF文件
                const pdfUrl = `${API_BASE}/templates/${templateId}/pdf-file`;
                const loadingTask = pdfjsLib.getDocument(pdfUrl);
                const pdf = await loadingTask.promise;
                
                // 隐藏加载提示
                loadingDiv.style.display = 'none';
                
                // 渲染函数
                const renderPage = async (pageNum) => {
                    const page = await pdf.getPage(pageNum);
                    const viewport = page.getViewport({ scale: 1.5 });
                    
                    // 设置canvas尺寸
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;
                    
                    // 渲染PDF页面
                    const renderContext = {
                        canvasContext: canvas.getContext('2d'),
                        viewport: viewport
                    };
                    await page.render(renderContext).promise;
                    
                    // 更新PDF编辑器数据
                    const scale = canvas.width / page.view[2]; // view[2]是页面宽度（点）
                    window.pdfEditorData[templateId].scale = scale;
                    window.pdfEditorData[templateId].pageWidth = page.view[2];
                    window.pdfEditorData[templateId].pageHeight = page.view[3];
                    
                    // 渲染已有的占位符标记
                    renderPlaceholderMarkers(templateId);
                };
                
                // 渲染第一页
                await renderPage(0);
                
                // 添加拖动选择功能
                let isDragging = false;
                let startX = 0, startY = 0;
                
                canvas.addEventListener('mousedown', function(e) {
                    if (e.button !== 0) return; // 只处理左键
                    isDragging = true;
                    const rect = canvas.getBoundingClientRect();
                    startX = e.clientX - rect.left;
                    startY = e.clientY - rect.top;
                });
                
                canvas.addEventListener('mousemove', function(e) {
                    if (!isDragging) return;
                    // 可以在这里显示拖动预览
                });
                
                canvas.addEventListener('mouseup', async function(e) {
                    if (!isDragging) return;
                    isDragging = false;
                    
                    const rect = canvas.getBoundingClientRect();
                    const endX = e.clientX - rect.left;
                    const endY = e.clientY - rect.top;
                    
                    const data = window.pdfEditorData[templateId];
                    const scale = data.scale;
                    const pageHeight = data.pageHeight;
                    
                    // 计算PDF坐标（以点为单位，左下角为原点）
                    const pdfX = Math.min(startX, endX) / scale;
                    const pdfY = pageHeight - Math.max(startY, endY) / scale; // PDF坐标系Y从下往上
                    
                    // 显示选择变量对话框
                    showFieldSelector(templateId, pdfX, pdfY);
                });
                
                // 页码切换
                document.getElementById('pdf-page-select').addEventListener('change', async function(e) {
                    const pageNum = parseInt(e.target.value);
                    window.pdfEditorData[templateId].currentPage = pageNum;
                    loadingDiv.style.display = 'block';
                    await renderPage(pageNum);
                    loadingDiv.style.display = 'none';
                });
                
            } catch (error) {
                console.error('加载PDF失败:', error);
                loadingDiv.innerHTML = `<div class="alert alert-danger">加载PDF失败: ${error.message}</div>`;
            }
        };
        
        // 页面加载完成后初始化PDF编辑器
        setTimeout(() => {
            initPDFEditor(templateId, pageWidth, pageHeight);
        }, 100);
        
        // 渲染占位符标记
        function renderPlaceholderMarkers(templateId) {
            const markersContainer = document.getElementById('placeholder-markers');
            if (!markersContainer) return;
            
            markersContainer.innerHTML = '';
            const data = window.pdfEditorData[templateId];
            const currentPage = data.currentPage;
            const scale = data.scale;
            
            data.positions.filter(pos => pos.page === currentPage).forEach((pos, idx) => {
                const marker = document.createElement('div');
                marker.className = 'placeholder-marker';
                marker.style.cssText = `
                    position: absolute;
                    left: ${pos.x * scale}px;
                    top: ${(data.pageHeight - pos.y) * scale}px;
                    width: 100px;
                    height: 20px;
                    background: rgba(13, 110, 253, 0.3);
                    border: 2px solid #0d6efd;
                    border-radius: 3px;
                    cursor: pointer;
                    font-size: 10px;
                    padding: 2px 5px;
                    color: #0d6efd;
                    font-weight: bold;
                `;
                marker.textContent = pos.field_name || '占位符';
                marker.title = `字段: ${pos.field_name}, 位置: (${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})`;
                marker.onclick = () => {
                    if (confirm('确定要删除这个占位符吗？')) {
                        data.positions.splice(data.positions.indexOf(pos), 1);
                        renderPlaceholderMarkers(templateId);
                    }
                };
                markersContainer.appendChild(marker);
            });
        }
        
        // 显示字段选择器
        function showFieldSelector(templateId, x, y) {
            const fields = fieldsRes.all_fields;
            const fieldsByCategory = {};
            fields.forEach(field => {
                if (!fieldsByCategory[field.category]) {
                    fieldsByCategory[field.category] = [];
                }
                fieldsByCategory[field.category].push(field);
            });
            
            const selectorHtml = Object.keys(fieldsByCategory).map(category => {
                const categoryFields = fieldsByCategory[category];
                return `
                    <div class="mb-3">
                        <h6 style="font-size: 0.9em; margin-bottom: 8px;">${category}</h6>
                        <div class="d-flex flex-wrap gap-2">
                            ${categoryFields.map(field => `
                                <button class="btn btn-sm btn-outline-primary" 
                                        onclick="addPlaceholderAtPosition(${templateId}, ${x}, ${y}, '${field.name}')">
                                    ${field.label || field.name}
                                </button>
                            `).join('')}
                        </div>
                    </div>
                `;
            }).join('');
            
            const selector = document.createElement('div');
            selector.className = 'modal fade';
            selector.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">选择要添加的字段</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            ${selectorHtml}
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(selector);
            const bs = getBootstrap();
            if (bs) {
                const modalInstance = new bs.Modal(selector);
                // 确保显示时移除 aria-hidden
                selector.addEventListener('shown.bs.modal', () => {
                    selector.removeAttribute('aria-hidden');
                }, { once: true });
                modalInstance.show();
                selector.addEventListener('hidden.bs.modal', () => selector.remove());
            }
        }
        
        // 在指定位置添加占位符
        window.addPlaceholderAtPosition = function(templateId, x, y, fieldName) {
            const data = window.pdfEditorData[templateId];
            const currentPage = data.currentPage;
            
            data.positions.push({
                field_name: fieldName,
                page: currentPage,
                x: x,
                y: y,
                font_size: 12
            });
            
            renderPlaceholderMarkers(templateId);
            
            // 关闭选择器
            const bs = getBootstrap();
            if (bs) {
                const modals = document.querySelectorAll('.modal.show');
                modals.forEach(m => {
                    const instance = bs.Modal.getInstance(m);
                    if (instance) instance.hide();
                });
            }
        };
        
        // 清除所有占位符
        window.clearAllPlaceholders = function() {
            if (confirm('确定要清除所有占位符吗？')) {
                const templateId = parseInt(document.getElementById('pdf-page-select').closest('.modal').id.replace('pdf-editor-modal-', ''));
                window.pdfEditorData[templateId].positions = [];
                renderPlaceholderMarkers(templateId);
            }
        };
        
        // 保存占位符位置
        window.savePDFPlaceholderPositions = async function(templateId) {
            try {
                const data = window.pdfEditorData[templateId];
                const response = await fetch(`${API_BASE}/templates/${templateId}/placeholder-positions`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data.positions)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    alert('占位符位置保存成功！\n已保存 ' + result.placeholders.length + ' 个占位符');
                    loadTemplates();
                    const bs = getBootstrap();
                    if (bs) {
                        const modal = document.getElementById(`pdf-editor-modal-${templateId}`);
                        if (modal) {
                            const modalInstance = bs.Modal.getInstance(modal);
                            if (modalInstance) modalInstance.hide();
                        }
                    }
                } else {
                    const error = await response.json();
                    alert('保存失败：' + (error.detail || '未知错误'));
                }
            } catch (error) {
                console.error('保存占位符位置错误:', error);
                alert('保存失败：' + error.message);
            }
        };
        
        // 添加样式
        const style = document.createElement('style');
        style.textContent = `
            .editable-cell {
                min-width: 100px;
                min-height: 30px;
                padding: 5px;
                cursor: text;
            }
            .editable-cell:focus {
                outline: 2px solid #0d6efd;
                outline-offset: -2px;
            }
            .variable-btn {
                transition: all 0.2s;
            }
            .variable-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
        `;
        document.head.appendChild(style);
        
        const bs = getBootstrap();
        if (bs) {
            new bs.Modal(modal).show();
        } else {
            modal.style.display = 'block';
            modal.classList.add('show');
            document.body.classList.add('modal-open');
        }
        
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
            style.remove();
        });
        
    } catch (error) {
        // 改进错误处理，确保能正确显示错误信息
        let errorMessage = '加载失败：';
        if (error instanceof Error) {
            errorMessage += error.message;
        } else if (error && typeof error === 'object') {
            if (error.detail) {
                errorMessage += error.detail;
            } else if (error.message) {
                errorMessage += error.message;
            } else {
                errorMessage += JSON.stringify(error);
            }
        } else {
            errorMessage += String(error);
        }
        alert(errorMessage);
        console.error('编辑占位符错误详情:', error);
    }
}

// ========== 工具函数 ==========
function createModal(title, content, onConfirm) {
    const modalId = 'modal-title-' + Date.now();
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', modalId);
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="${modalId}">${title}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                </div>
                <div class="modal-body">
                    ${content}
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="button" class="btn btn-primary confirm-btn-visible" onclick="this.closest('.modal').querySelector('.confirm-btn').click()">保存</button>
                </div>
            </div>
        </div>
    `;
    
    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'confirm-btn';
    confirmBtn.style.display = 'none';
    confirmBtn.onclick = () => {
        if (onConfirm) onConfirm();
    };
    modal.querySelector('.modal-footer').appendChild(confirmBtn);
    
    modal.addEventListener('hidden.bs.modal', () => {
        // 关闭模态框时，确保移除焦点，避免 aria-hidden 警告
        const activeElement = document.activeElement;
        if (activeElement && modal.contains(activeElement)) {
            activeElement.blur();
        }
        modal.remove();
    });
    
    // 确保显示时移除 aria-hidden
    modal.addEventListener('shown.bs.modal', () => {
        modal.removeAttribute('aria-hidden');
    });
    
    // 关闭模态框前移除焦点
    modal.addEventListener('hide.bs.modal', () => {
        const activeElement = document.activeElement;
        if (activeElement && modal.contains(activeElement)) {
            activeElement.blur();
        }
    });
    
    return modal;
}

// 辅助函数：显示模态框并确保无障碍属性正确
function showModal(modal) {
    const bs = getBootstrap();
    if (bs) {
        const modalInstance = new bs.Modal(modal);
        // 确保显示时移除 aria-hidden
        modal.addEventListener('shown.bs.modal', () => {
            modal.removeAttribute('aria-hidden');
        }, { once: true });
        // 关闭前移除焦点，避免 aria-hidden 警告
        modal.addEventListener('hide.bs.modal', () => {
            const activeElement = document.activeElement;
            if (activeElement && modal.contains(activeElement)) {
                activeElement.blur();
            }
        }, { once: false });
        modalInstance.show();
    } else {
        // 如果bootstrap未加载，使用简单的显示方式
        modal.style.display = 'block';
        modal.classList.add('show');
        modal.removeAttribute('aria-hidden');
        document.body.classList.add('modal-open');
    }
}

function getStatusBadge(status) {
    const badges = {
        'pending': '<span class="badge bg-warning">待处理</span>',
        'processing': '<span class="badge bg-info">处理中</span>',
        'completed': '<span class="badge bg-success">已完成</span>',
        'failed': '<span class="badge bg-danger">失败</span>',
        'active': '<span class="badge bg-success">进行中</span>',
        'closed': '<span class="badge bg-secondary">已关闭</span>',
        'approved': '<span class="badge bg-success">已通过</span>',
        'rejected': '<span class="badge bg-danger">已拒绝</span>'
    };
    return badges[status] || status;
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    // 检查bootstrap是否已加载
    if (typeof bootstrap === 'undefined') {
        console.warn('Bootstrap未加载，某些功能可能无法使用');
        // 尝试延迟加载
        setTimeout(() => {
            if (typeof bootstrap === 'undefined') {
                console.error('Bootstrap加载失败，请检查静态文件路径');
            }
        }, 1000);
    }
    
    // 检查是否在管理员页面，如果是，检查登录状态
    if (window.location.pathname.startsWith('/admin')) {
        const token = localStorage.getItem('admin_token');
        if (!token && !window.location.pathname.includes('/login')) {
            window.location.href = '/admin/login';
            return;
        }
        // 设置所有API请求的header
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            if (args[0] && (args[0].startsWith('/api/') || args[0].startsWith(API_BASE))) {
                if (!args[1]) args[1] = {};
                if (!args[1].headers) args[1].headers = {};
                args[1].headers['X-Admin-Token'] = token || '';
            }
            return originalFetch.apply(this, args);
        }
    }
    
    // 初始化导航
    initNavigation();
    
    // 检查URL hash，如果有则切换到对应页面，否则默认显示教师管理
    const hash = window.location.hash;
    if (hash && hash.startsWith('#page-')) {
        const page = hash.substring(6); // 去掉 '#page-'
        if (['teachers', 'templates', 'tasks'].includes(page)) {
            switchPage(page);
            // 更新导航状态
            document.querySelectorAll('.nav-link').forEach(l => {
                l.classList.remove('active');
                if (l.getAttribute('data-page') === page) {
                    l.classList.add('active');
                }
            });
        } else {
            switchPage('teachers');
        }
    } else {
    // 加载默认页面（教师管理）
    switchPage('teachers');
    }
});

// ========== 签名画板相关函数 ==========
// 签名画板存储
if (!window.signatureCanvases) {
    window.signatureCanvases = {};
}
if (!window.signatureContexts) {
    window.signatureContexts = {};
}

// 初始化签名画板
function initSignatureCanvas(fieldName) {
    console.log(`[签名画板] 初始化字段: ${fieldName}`);
    const canvas = document.getElementById(`signature-canvas-${fieldName}`);
    if (!canvas) {
        console.error(`[签名画板] Canvas元素未找到: signature-canvas-${fieldName}`);
        return;
    }
    
    // 检查是否已经初始化过
    if (window.signatureCanvases[fieldName] && window.signatureCanvases[fieldName] === canvas) {
        console.log(`[签名画板] Canvas已经初始化过，跳过`);
        return;
    }
    
    // 移除旧的事件监听器（如果存在）- 使用克隆节点的方式彻底清除
    const newCanvas = canvas.cloneNode(true);
    canvas.parentNode.replaceChild(newCanvas, canvas);
    const canvasElement = newCanvas;
    
    // 重新获取上下文
    const ctxElement = canvasElement.getContext('2d');
    if (!ctxElement) {
        console.error(`[签名画板] 无法获取2D上下文`);
        return;
    }
    
    ctxElement.strokeStyle = '#000';
    ctxElement.lineWidth = 2;
    ctxElement.lineCap = 'round';
    ctxElement.lineJoin = 'round';
    ctxElement.fillStyle = '#ffffff';
    ctxElement.fillRect(0, 0, canvasElement.width, canvasElement.height);
    
    // 更新引用
    window.signatureCanvases[fieldName] = canvasElement;
    window.signatureContexts[fieldName] = ctxElement;
    
    // 绘制状态
    let isDrawing = false;
    let lastX = 0;
    let lastY = 0;
    
    function getCanvasCoordinates(e) {
        const rect = canvasElement.getBoundingClientRect();
        const scaleX = canvasElement.width / rect.width;
        const scaleY = canvasElement.height / rect.height;
        const clientX = e.clientX || (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
        const clientY = e.clientY || (e.touches && e.touches[0] ? e.touches[0].clientY : 0);
        const x = (clientX - rect.left) * scaleX;
        const y = (clientY - rect.top) * scaleY;
        return { x, y };
    }
    
    function getTouchCoordinates(touch) {
        const rect = canvasElement.getBoundingClientRect();
        const scaleX = canvasElement.width / rect.width;
        const scaleY = canvasElement.height / rect.height;
        const x = (touch.clientX - rect.left) * scaleX;
        const y = (touch.clientY - rect.top) * scaleY;
        return { x, y };
    }
    
    function startDrawing(e) {
        e.preventDefault();
        e.stopPropagation();
        isDrawing = true;
        const coords = getCanvasCoordinates(e);
        lastX = coords.x;
        lastY = coords.y;
        
        // 在起始点画一个小点
        ctxElement.beginPath();
        ctxElement.arc(lastX, lastY, 2, 0, 2 * Math.PI);
        ctxElement.fill();
    }
    
    function draw(e) {
        if (!isDrawing) return;
        e.preventDefault();
        e.stopPropagation();
        const coords = getCanvasCoordinates(e);
        const currentX = coords.x;
        const currentY = coords.y;
        
        ctxElement.beginPath();
        ctxElement.moveTo(lastX, lastY);
        ctxElement.lineTo(currentX, currentY);
        ctxElement.stroke();
        
        lastX = currentX;
        lastY = currentY;
    }
    
    function stopDrawing(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }
        isDrawing = false;
    }
    
    // 确保画布可以接收事件
    canvasElement.style.pointerEvents = 'auto';
    canvasElement.style.position = 'relative';
    canvasElement.style.zIndex = '10';
    
    // 绑定鼠标事件
    canvasElement.addEventListener('mousedown', startDrawing);
    canvasElement.addEventListener('mousemove', draw);
    canvasElement.addEventListener('mouseup', stopDrawing);
    canvasElement.addEventListener('mouseleave', stopDrawing);
    
    // 触摸事件支持
    canvasElement.addEventListener('touchstart', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const touch = e.touches[0];
        const coords = getTouchCoordinates(touch);
        lastX = coords.x;
        lastY = coords.y;
        isDrawing = true;
        
        ctxElement.beginPath();
        ctxElement.arc(lastX, lastY, 1, 0, 2 * Math.PI);
        ctxElement.fill();
    }, { passive: false });
    
    canvasElement.addEventListener('touchmove', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!isDrawing) return;
        const touch = e.touches[0];
        const coords = getTouchCoordinates(touch);
        const currentX = coords.x;
        const currentY = coords.y;
        
        ctxElement.beginPath();
        ctxElement.moveTo(lastX, lastY);
        ctxElement.lineTo(currentX, currentY);
        ctxElement.stroke();
        
        lastX = currentX;
        lastY = currentY;
    }, { passive: false });
    
    canvasElement.addEventListener('touchend', (e) => {
        e.preventDefault();
        e.stopPropagation();
        isDrawing = false;
    }, { passive: false });
    
    canvasElement.addEventListener('touchcancel', (e) => {
        e.preventDefault();
        e.stopPropagation();
        isDrawing = false;
    }, { passive: false });
    
    console.log(`[签名画板] 初始化完成: ${fieldName}`);
}

// 清除签名
function clearSignature(fieldName) {
    const canvas = window.signatureCanvases[fieldName];
    const ctx = window.signatureContexts[fieldName];
    if (canvas && ctx) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        const input = document.getElementById(`signature-input-${fieldName}`);
        if (input) {
            input.value = '';
        }
    }
}

// 保存签名到输入框
function saveSignatureToInput(fieldName) {
    const canvas = window.signatureCanvases[fieldName];
    const input = document.getElementById(`signature-input-${fieldName}`);
    if (canvas && input) {
        const dataURL = canvas.toDataURL('image/png');
        input.value = dataURL;
        alert('签名已保存');
    } else {
        console.error(`[签名画板] 无法保存签名: canvas=${!!canvas}, input=${!!input}`);
    }
}

// 暴露到全局作用域
window.initSignatureCanvas = initSignatureCanvas;
window.clearSignature = clearSignature;
window.saveSignatureToInput = saveSignatureToInput;

// 完成任务导出
async function completeTaskExport(taskId) {
    // 检查有多少教师已填写
    let submittedCount = 0;
    let totalCount = 0;
    try {
        const detailRes = await fetch(`${API_BASE}/tasks/${taskId}/detail`);
        if (detailRes.ok) {
            const detail = await detailRes.json();
            const questionnaireId = detail.questionnaire_id;
            
            if (questionnaireId) {
                const responsesRes = await fetch(`${API_BASE}/questionnaires/${questionnaireId}/responses`);
                if (responsesRes.ok) {
                    const responses = await responsesRes.json();
                    const taskRes = await fetch(`${API_BASE}/tasks/${taskId}`);
                    if (taskRes.ok) {
                        const task = await taskRes.json();
                        const taskTeacherIds = new Set(task.teacher_ids.map(id => parseInt(id)));
                        const taskResponses = responses.filter(r => taskTeacherIds.has(parseInt(r.teacher_id)));
                        submittedCount = taskResponses.filter(r => r.submitted_at || r.confirmed_status === 'confirmed').length;
                        totalCount = task.teacher_ids.length;
                    }
                }
            }
        }
    } catch (e) {
        console.error('检查填写情况失败:', e);
    }
    
    // 根据填写情况显示不同的确认信息
    let confirmMessage = '确定要完成导出吗？';
    if (submittedCount === 0) {
        confirmMessage = '当前没有教师完成填写。\n\n确定要继续导出吗？将创建一个空的ZIP文件。';
    } else if (submittedCount > 0 && submittedCount < totalCount) {
        confirmMessage = `当前有 ${submittedCount}/${totalCount} 位教师已完成填写。\n\n确定要导出吗？导出时将只包含已填写教师的数据。`;
    } else if (submittedCount === totalCount && totalCount > 0) {
        confirmMessage = '确定要完成导出吗？这将开始生成所有教师的PDF文件。';
    }
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/tasks/${taskId}/complete-export`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Token': localStorage.getItem('admin_token') || ''
            }
        });
        
        if (response.ok) {
            alert('导出任务已启动，正在后台处理中。\n\n系统将自动刷新任务状态，请稍候...');
            // 刷新任务详情
            showTaskDetail(taskId);
            
            // 设置自动刷新任务状态
            let refreshCount = 0;
            const maxRefreshes = 60; // 最多刷新60次（5分钟）
            const refreshInterval = setInterval(async () => {
                refreshCount++;
                if (refreshCount > maxRefreshes) {
                    clearInterval(refreshInterval);
                    console.log('[导出任务] 已达到最大刷新次数，停止自动刷新');
                    return;
                }
                
                try {
                    // 检查任务状态
                    const taskRes = await fetch(`${API_BASE}/tasks/${taskId}`);
                    if (taskRes.ok) {
                        const task = await taskRes.json();
                        console.log(`[导出任务] 检查任务状态 (${refreshCount}/${maxRefreshes}):`, task.status);
                        
                        if (task.status === 'completed' || task.status === 'failed') {
                            clearInterval(refreshInterval);
                            console.log('[导出任务] 任务已完成或失败，停止自动刷新');
                            
                            // 刷新任务详情和任务列表
                            showTaskDetail(taskId);
                            loadTasks();
                            
                            if (task.status === 'completed') {
                                alert('导出任务已完成！您可以下载导出文件了。');
                            } else {
                                // 尝试获取更详细的错误信息
                                console.error('[导出任务] 任务失败详情:', task);
                                alert('导出任务失败，请检查浏览器控制台和服务器日志获取详细错误信息，或联系管理员。');
                            }
                        } else if (task.status === 'processing') {
                            // 如果还在处理中，更新任务详情显示
                            const taskIdInput = document.getElementById('task-detail-id');
                            if (taskIdInput && parseInt(taskIdInput.value) === taskId) {
                                // 只更新状态显示，不重新加载整个详情
                                const statusBadge = document.querySelector('.modal.show .badge');
                                if (statusBadge) {
                                    statusBadge.textContent = '处理中';
                                    statusBadge.className = 'badge bg-warning';
                                }
                            }
                        }
                    }
                } catch (e) {
                    console.error('[导出任务] 检查任务状态失败:', e);
                    // 继续尝试，不中断
                }
            }, 5000); // 每5秒检查一次
            
            // 保存interval ID，以便在需要时清除
            window.taskExportInterval = refreshInterval;
        } else {
            const error = await response.json();
            alert('启动导出失败：' + (error.detail || '未知错误'));
        }
    } catch (error) {
        console.error('完成导出失败:', error);
        alert('完成导出失败：' + error.message);
    }
}

// 暴露到全局作用域
window.completeTaskExport = completeTaskExport;

