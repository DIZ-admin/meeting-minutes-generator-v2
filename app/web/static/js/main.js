/**
 * Main JavaScript for the Meeting Protocol Generator web interface
 */

// Global variables
let currentTaskId = null;
let pollingInterval = null;
let currentFilter = 'all';

// DOM elements (will be initialized in initializeApp)
let uploadForm;
let submitBtn;
let refreshTasksBtn;
let refreshProtocolsBtn;
let currentTaskStatus;
let tasksList;
let protocolsList;
let copyProtocolBtn;

// Event listeners
document.addEventListener('DOMContentLoaded', initializeApp);

/**
 * Initialize the application
 */
function initializeApp() {
    // Initialize DOM elements
    uploadForm = document.getElementById('uploadForm');
    submitBtn = document.getElementById('submitBtn');
    refreshTasksBtn = document.getElementById('refreshTasksBtn');
    refreshProtocolsBtn = document.getElementById('refreshProtocolsBtn');
    currentTaskStatus = document.getElementById('currentTaskStatus');
    tasksList = document.getElementById('tasksList');
    protocolsList = document.getElementById('protocolsList');
    copyProtocolBtn = document.getElementById('copyProtocolBtn');
    
    // Set up event listeners based on current page
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleFormSubmit);
        
        // Set default date to today
        const dateInput = document.getElementById('date');
        if (dateInput) {
            dateInput.valueAsDate = new Date();
        }
    }
    
    if (refreshTasksBtn) {
        refreshTasksBtn.addEventListener('click', loadTasks);
        loadTasks(); // Load tasks on page load
    }
    
    if (refreshProtocolsBtn) {
        refreshProtocolsBtn.addEventListener('click', loadProtocols);
        loadProtocols(); // Load protocols on page load
    }
    
    if (copyProtocolBtn) {
        copyProtocolBtn.addEventListener('click', copyProtocolContent);
    }
    
    // Set up filter buttons if they exist
    const filterItems = document.querySelectorAll('.filter-item');
    if (filterItems.length > 0) {
        filterItems.forEach(item => {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Update active filter
                filterItems.forEach(i => i.classList.remove('active'));
                this.classList.add('active');
                
                // Update filter label
                const filterLabel = document.querySelector('.filter-label');
                if (filterLabel) {
                    filterLabel.textContent = this.textContent;
                }
                
                // Apply filter
                currentFilter = this.dataset.filter;
                renderTasks();
            });
        });
    }
    
    // Check if there's a task ID in the URL
    const urlParams = new URLSearchParams(window.location.search);
    const taskId = urlParams.get('id');
    if (taskId && currentTaskStatus) {
        startPolling(taskId);
    }
}

/**
 * Handle form submission
 * @param {Event} event - Form submit event
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    
    // Disable submit button and show loading state
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Загрузка...';
    
    try {
        const formData = new FormData(uploadForm);
        
        // Преобразуем информацию о встрече в JSON
        const meetingInfo = {
            title: formData.get('title'),
            date: formData.get('date'),
            location: formData.get('location'),
            organizer: formData.get('organizer')
        };
        
        // Добавляем участников
        if (formData.get('participants')) {
            meetingInfo.participants = formData.get('participants')
                .split(',')
                .map(p => p.trim())
                .filter(p => p);
        }
        
        // Добавляем повестку
        if (formData.get('agenda')) {
            meetingInfo.agenda_items = formData.get('agenda')
                .split(',')
                .map(a => a.trim())
                .filter(a => a);
        }
        
        // Удаляем отдельные поля и добавляем их в meeting_info
        formData.delete('title');
        formData.delete('date');
        formData.delete('location');
        formData.delete('organizer');
        formData.delete('participants');
        formData.delete('agenda');
        formData.append('meeting_info', JSON.stringify(meetingInfo));
        
        // Показываем статус задачи
        if (currentTaskStatus) {
            currentTaskStatus.classList.remove('d-none');
            const progressBar = currentTaskStatus.querySelector('.progress-bar');
            const statusMessage = currentTaskStatus.querySelector('.status-message');
            const downloadLinks = currentTaskStatus.querySelector('.download-links');
            
            if (progressBar && statusMessage && downloadLinks) {
                progressBar.style.width = '0%';
                progressBar.setAttribute('aria-valuenow', 0);
                statusMessage.textContent = 'Загрузка файла...';
                downloadLinks.classList.add('d-none');
            }
        }
        
        // Отправляем данные на сервер с помощью axios
        const response = await axios.post('/api/v1/upload', formData);
        
        // Проверяем успешность запроса
        if (response.status !== 200) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        console.log('Success:', response.data);
        
        // Очищаем форму, но оставляем дату и другие общие поля
        const audioFileInput = document.getElementById('audioFile');
        const isTranscriptCheckbox = document.getElementById('isTranscript');
        if (audioFileInput) audioFileInput.value = '';
        if (isTranscriptCheckbox) isTranscriptCheckbox.checked = false;
        
        // Начинаем отслеживание статуса задачи
        currentTaskId = response.data.task_id;
        startPolling(currentTaskId);
        
        // Показываем успешное сообщение
        showAlert('success', `Файл успешно загружен. ID задачи: ${currentTaskId}`);
        
    } catch (error) {
        console.error('Error uploading file:', error);
        showAlert('danger', `Ошибка при загрузке файла: ${error.message}`);
    } finally {
        // Re-enable submit button
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Загрузить и обработать';
    }
}

/**
 * Start polling for task status
 * @param {string} taskId - Task ID to poll for
 */
function startPolling(taskId) {
    // Clear any existing polling
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }
    
    // Show current task status section
    currentTaskStatus.classList.remove('d-none');
    
    // Set up polling interval (every 2 seconds)
    pollingInterval = setInterval(() => {
        checkTaskStatus(taskId);
    }, 2000);
    
    // Initial check
    checkTaskStatus(taskId);
}

/**
 * Check the status of a task
 * @param {string} taskId - Task ID to check
 */
async function checkTaskStatus(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        const task = await response.json();
        updateTaskUI(task);
        
        // If task is completed or errored, stop polling
        if (task.status === 'completed' || task.status === 'error') {
            clearInterval(pollingInterval);
            pollingInterval = null;
            
            // Reload all tasks
            loadTasks();
        }
        
    } catch (error) {
        console.error('Error checking task status:', error);
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

/**
 * Update the UI with task status
 * @param {Object} task - Task object
 */
function updateTaskUI(task) {
    // Update progress bar
    const progressBar = currentTaskStatus.querySelector('.progress-bar');
    const statusMessage = currentTaskStatus.querySelector('.status-message');
    const downloadLinks = currentTaskStatus.querySelector('.download-links');
    
    // Set progress
    let progress = 0;
    if (task.status === 'completed') {
        progress = 100;
    } else if (task.status === 'error') {
        progress = 100;
        progressBar.classList.remove('bg-primary');
        progressBar.classList.add('bg-danger');
    } else if (task.progress) {
        progress = task.progress * 100;
    } else {
        // Default progress based on status
        switch (task.status) {
            case 'uploaded': progress = 5; break;
            case 'initializing': progress = 10; break;
            case 'transcribing': progress = 30; break;
            case 'analyzing': progress = 60; break;
            case 'generating': progress = 80; break;
            default: progress = 0;
        }
    }
    
    progressBar.style.width = `${progress}%`;
    progressBar.setAttribute('aria-valuenow', progress);
    
    // Set status message
    let statusText = task.message || `Статус: ${task.status}`;
    statusMessage.textContent = statusText;
    
    // Show download links if completed
    if (task.status === 'completed' && task.result) {
        downloadLinks.classList.remove('d-none');
        
        const mdLink = downloadLinks.querySelector('.download-md');
        const jsonLink = downloadLinks.querySelector('.download-json');
        
        mdLink.href = `/api/download/${task.task_id}/md`;
        jsonLink.href = `/api/download/${task.task_id}/json`;
    } else {
        downloadLinks.classList.add('d-none');
    }
}

/**
 * Load all tasks
 */
async function loadTasks() {
    try {
        const response = await fetch('/api/tasks');
        
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        const tasks = await response.json();
        renderTasksList(tasks);
        
    } catch (error) {
        console.error('Error loading tasks:', error);
        tasksList.innerHTML = '<p class="text-danger">Ошибка при загрузке задач</p>';
    }
}

/**
 * Render the tasks list
 * @param {Object} tasks - Tasks object
 */
function renderTasksList(tasks) {
    // If no tasks, show message
    if (Object.keys(tasks).length === 0) {
        tasksList.innerHTML = '<p class="text-muted text-center">Нет активных задач</p>';
        return;
    }
    
    // Convert to array and sort by created_at (newest first)
    const tasksArray = Object.entries(tasks).map(([taskId, task]) => ({
        taskId,
        ...task
    }));
    
    tasksArray.sort((a, b) => {
        return new Date(b.created_at) - new Date(a.created_at);
    });
    
    // Build HTML
    let html = '';
    
    tasksArray.forEach(task => {
        const statusClass = getStatusClass(task.status);
        const createdDate = new Date(task.created_at).toLocaleString();
        
        html += `
            <div class="task-item ${statusClass}">
                <h6>${task.file_name || 'Задача'}</h6>
                <p><strong>Статус:</strong> ${getStatusText(task.status)}</p>
                <p><strong>Создана:</strong> ${createdDate}</p>
                ${task.message ? `<p><strong>Сообщение:</strong> ${task.message}</p>` : ''}
                
                ${task.status === 'completed' && task.result ? `
                    <div class="download-links">
                        <a href="/api/download/${task.taskId}/md" class="btn btn-sm btn-success">Скачать Markdown</a>
                        <a href="/api/download/${task.taskId}/json" class="btn btn-sm btn-info">Скачать JSON</a>
                    </div>
                ` : ''}
            </div>
        `;
    });
    
    tasksList.innerHTML = html;
}

/**
 * Get CSS class for task status
 * @param {string} status - Task status
 * @returns {string} CSS class
 */
function getStatusClass(status) {
    switch (status) {
        case 'completed': return 'completed';
        case 'error': return 'error';
        case 'uploaded':
        case 'initializing':
        case 'transcribing':
        case 'analyzing':
        case 'generating':
            return 'processing';
        default: return '';
    }
}

/**
 * Get human-readable status text
 * @param {string} status - Task status
 * @returns {string} Status text
 */
function getStatusText(status) {
    switch (status) {
        case 'uploaded': return 'Загружено';
        case 'initializing': return 'Инициализация';
        case 'transcribing': return 'Транскрибация';
        case 'analyzing': return 'Анализ';
        case 'generating': return 'Генерация протокола';
        case 'completed': return 'Завершено';
        case 'error': return 'Ошибка';
        default: return status;
    }
}

/**
 * Show alert message
 * @param {string} type - Alert type (success, danger, etc.)
 * @param {string} message - Alert message
 */
function showAlert(type, message) {
    // Create alert element
    const alertElement = document.createElement('div');
    alertElement.className = `alert alert-${type} alert-dismissible fade show`;
    alertElement.setAttribute('role', 'alert');
    
    // Add message
    alertElement.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Find container to append alert to
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertElement, container.firstChild);
    }
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertElement.classList.remove('show');
        setTimeout(() => alertElement.remove(), 300);
    }, 5000);
}

/**
 * Load protocols list
 */
async function loadProtocols() {
    if (!protocolsList) return;
    
    try {
        protocolsList.innerHTML = '<p class="text-center"><span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Загрузка протоколов...</p>';
        
        const response = await axios.get('/api/v1/protocols');
        
        if (response.status !== 200) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        renderProtocolsList(response.data.protocols);
        
    } catch (error) {
        console.error('Error loading protocols:', error);
        protocolsList.innerHTML = '<div class="alert alert-danger text-center">Ошибка при загрузке протоколов</div>';
    }
}

/**
 * Render protocols list
 * @param {Array} protocols - Array of protocol objects
 */
function renderProtocolsList(protocols) {
    if (!protocolsList) return;
    
    if (!protocols || protocols.length === 0) {
        protocolsList.innerHTML = '<div class="alert alert-info text-center">Нет доступных протоколов</div>';
        return;
    }
    
    let html = '<div class="table-responsive"><table class="table table-hover">';
    html += `
        <thead>
            <tr>
                <th>Название</th>
                <th>Дата</th>
                <th>Организатор</th>
                <th>Участники</th>
                <th>Действия</th>
            </tr>
        </thead>
        <tbody>
    `;
    
    protocols.forEach(function(protocol) {
        const date = protocol.metadata?.date ? new Date(protocol.metadata.date).toLocaleDateString() : 'Не указана';
        const title = protocol.metadata?.title || 'Без названия';
        const organizer = protocol.metadata?.organizer || 'Не указан';
        
        // Получаем список участников
        let participants = 'Нет данных';
        if (protocol.participants && protocol.participants.length > 0) {
            if (typeof protocol.participants[0] === 'string') {
                participants = protocol.participants.join(', ');
            } else if (protocol.participants[0].name) {
                participants = protocol.participants.map(p => p.name).join(', ');
            }
        }
        
        html += `
            <tr>
                <td>${title}</td>
                <td>${date}</td>
                <td>${organizer}</td>
                <td>${participants}</td>
                <td>
                    <div class="btn-group">
                        <button type="button" class="btn btn-sm btn-primary" onclick="viewProtocol('${protocol.id}')">
                            <i class="fas fa-eye me-1"></i> Просмотр
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-primary dropdown-toggle dropdown-toggle-split" data-bs-toggle="dropdown" aria-expanded="false">
                            <span class="visually-hidden">Меню</span>
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/api/v1/protocols/${protocol.id}/md" target="_blank">Скачать MD</a></li>
                            <li><a class="dropdown-item" href="/api/v1/protocols/${protocol.id}/json" target="_blank">Скачать JSON</a></li>
                        </ul>
                    </div>
                </td>
            </tr>
        `;
    });
    
    html += '</tbody></table></div>';
    protocolsList.innerHTML = html;
}

/**
 * View protocol details
 * @param {string} protocolId - Protocol ID
 */
async function viewProtocol(protocolId) {
    // Открываем модальное окно
    const modalElement = document.getElementById('protocolModal');
    if (!modalElement) return;
    
    const modal = new bootstrap.Modal(modalElement);
    modal.show();
    
    // Получаем содержимое протокола
    const protocolContent = document.querySelector('.protocol-content');
    if (!protocolContent) return;
    
    protocolContent.innerHTML = '<div class="text-center"><span class="spinner-border" role="status" aria-hidden="true"></span><p>Загрузка содержимого протокола...</p></div>';
    
    // Обновляем ссылки для скачивания
    const downloadMdBtn = document.getElementById('downloadMdBtn');
    const downloadJsonBtn = document.getElementById('downloadJsonBtn');
    
    if (downloadMdBtn) downloadMdBtn.href = `/api/v1/protocols/${protocolId}/md`;
    if (downloadJsonBtn) downloadJsonBtn.href = `/api/v1/protocols/${protocolId}/json`;
    
    try {
        const response = await axios.get(`/api/v1/protocols/${protocolId}`);
        
        if (response.status !== 200) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        renderProtocolContent(response.data);
        
    } catch (error) {
        console.error('Error loading protocol:', error);
        protocolContent.innerHTML = '<div class="alert alert-danger">Ошибка при загрузке протокола</div>';
    }
}

/**
 * Render protocol content
 * @param {Object} protocol - Protocol object
 */
function renderProtocolContent(protocol) {
    const protocolContent = document.querySelector('.protocol-content');
    if (!protocolContent) return;
    
    // Обновляем заголовок модального окна
    const modalTitle = document.getElementById('protocolModalLabel');
    if (modalTitle) {
        modalTitle.textContent = protocol.metadata?.title || 'Протокол совещания';
    }
    
    // Форматируем содержимое протокола
    let html = '<div class="protocol-container">';
    
    // Метаданные
    html += '<div class="metadata mb-4">';
    html += `<h3>${protocol.metadata?.title || 'Протокол совещания'}</h3>`;
    
    if (protocol.metadata) {
        const date = protocol.metadata.date ? new Date(protocol.metadata.date).toLocaleDateString() : 'Не указана';
        html += `<p><strong>Дата:</strong> ${date}</p>`;
        
        if (protocol.metadata.location) {
            html += `<p><strong>Место проведения:</strong> ${protocol.metadata.location}</p>`;
        }
        
        if (protocol.metadata.organizer) {
            html += `<p><strong>Организатор:</strong> ${protocol.metadata.organizer}</p>`;
        }
    }
    
    html += '</div>';
    
    // Участники
    if (protocol.participants && protocol.participants.length > 0) {
        html += '<div class="participants mb-4">';
        html += '<h4>Участники</h4>';
        html += '<ul>';
        
        protocol.participants.forEach(function(participant) {
            if (typeof participant === 'string') {
                html += `<li>${participant}</li>`;
            } else if (participant.name) {
                let participantInfo = participant.name;
                if (participant.role) {
                    participantInfo += ` (${participant.role})`;
                }
                html += `<li>${participantInfo}</li>`;
            }
        });
        
        html += '</ul>';
        html += '</div>';
    }
    
    // Повестка
    if (protocol.agenda_items && protocol.agenda_items.length > 0) {
        html += '<div class="agenda mb-4">';
        html += '<h4>Повестка</h4>';
        html += '<ol>';
        
        protocol.agenda_items.forEach(function(item) {
            if (typeof item === 'string') {
                html += `<li>${item}</li>`;
            } else if (item.title) {
                let itemInfo = item.title;
                if (item.description) {
                    itemInfo += ` - ${item.description}`;
                }
                html += `<li>${itemInfo}</li>`;
            }
        });
        
        html += '</ol>';
        html += '</div>';
    }
    
    // Обсуждения
    if (protocol.discussions && protocol.discussions.length > 0) {
        html += '<div class="discussions mb-4">';
        html += '<h4>Обсуждения</h4>';
        
        protocol.discussions.forEach(function(discussion, index) {
            html += `<div class="discussion-item mb-3">`;
            html += `<h5>Тема ${index + 1}: ${discussion.topic || 'Без названия'}</h5>`;
            html += `<p>${discussion.summary || 'Нет содержимого'}</p>`;
            html += `</div>`;
        });
        
        html += '</div>';
    }
    
    // Решения
    if (protocol.decisions && protocol.decisions.length > 0) {
        html += '<div class="decisions mb-4">';
        html += '<h4>Решения</h4>';
        html += '<ul>';
        
        protocol.decisions.forEach(function(decision) {
            if (typeof decision === 'string') {
                html += `<li>${decision}</li>`;
            } else if (decision.text) {
                html += `<li>${decision.text}</li>`;
            }
        });
        
        html += '</ul>';
        html += '</div>';
    }
    
    // Действия
    if (protocol.action_items && protocol.action_items.length > 0) {
        html += '<div class="actions mb-4">';
        html += '<h4>Действия</h4>';
        html += '<ul>';
        
        protocol.action_items.forEach(function(action) {
            if (typeof action === 'string') {
                html += `<li>${action}</li>`;
            } else {
                let actionText = action.text || action.description || '';
                let assignee = action.assignee || '';
                let deadline = action.deadline || action.due_date || '';
                
                let actionInfo = actionText;
                if (assignee) {
                    actionInfo += ` (Ответственный: ${assignee}`;
                    if (deadline) {
                        actionInfo += `, Срок: ${deadline}`;
                    }
                    actionInfo += ')';
                } else if (deadline) {
                    actionInfo += ` (Срок: ${deadline})`;
                }
                
                html += `<li>${actionInfo}</li>`;
            }
        });
        
        html += '</ul>';
        html += '</div>';
    }
    
    // Итоги
    if (protocol.summary) {
        html += '<div class="summary mb-4">';
        html += '<h4>Итоги</h4>';
        html += `<p>${protocol.summary}</p>`;
        html += '</div>';
    }
    
    html += '</div>';
    
    protocolContent.innerHTML = html;
}

/**
 * Copy protocol content to clipboard
 */
function copyProtocolContent() {
    const protocolContainer = document.querySelector('.protocol-container');
    if (!protocolContainer) return;
    
    // Создаем временный элемент для копирования
    const tempElement = document.createElement('div');
    tempElement.innerHTML = protocolContainer.innerHTML;
    
    // Удаляем все HTML-теги, оставляя только текст
    const textContent = tempElement.textContent;
    
    // Копируем текст в буфер обмена
    navigator.clipboard.writeText(textContent)
        .then(() => {
            const copyBtn = document.getElementById('copyProtocolBtn');
            if (!copyBtn) return;
            
            const originalText = copyBtn.innerHTML;
            
            copyBtn.innerHTML = '<i class="fas fa-check me-1"></i> Скопировано';
            
            setTimeout(() => {
                copyBtn.innerHTML = originalText;
            }, 2000);
        })
        .catch(err => {
            console.error('Ошибка при копировании: ', err);
            showAlert('danger', 'Не удалось скопировать текст');
        });
}
