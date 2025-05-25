/**
 * JavaScript для веб-интерфейса генератора протоколов совещаний
 */

// Глобальные переменные
let currentTaskId = null;
let statusCheckInterval = null;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация формы загрузки
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleFormSubmit);
    }
    
    // Загрузка списка задач
    loadTasksList();
});

/**
 * Обработка отправки формы
 */
async function handleFormSubmit(event) {
    event.preventDefault();
    
    // Получаем элементы формы
    const form = event.target;
    const fileInput = form.querySelector('#audioFile');
    const titleInput = form.querySelector('#title');
    const languageSelect = form.querySelector('#language');
    const dateInput = form.querySelector('#date');
    const skipNotificationsCheckbox = form.querySelector('#skipNotifications');
    const submitButton = form.querySelector('button[type="submit"]');
    
    // Проверяем, выбран ли файл
    if (!fileInput.files || fileInput.files.length === 0) {
        showAlert('Пожалуйста, выберите файл для загрузки', 'danger');
        return;
    }
    
    // Определяем тип файла и эндпоинт
    const file = fileInput.files[0];
    const fileExt = file.name.split('.').pop().toLowerCase();
    const isAudio = ['mp3', 'wav', 'm4a', 'ogg', 'flac'].includes(fileExt);
    const isTranscript = fileExt === 'json';
    
    if (!isAudio && !isTranscript) {
        showAlert('Неподдерживаемый формат файла', 'danger');
        return;
    }
    
    // Формируем данные для отправки
    const formData = new FormData();
    formData.append(isAudio ? 'audio_file' : 'transcript_file', file);
    
    if (titleInput.value) {
        formData.append('title', titleInput.value);
    }
    
    if (languageSelect.value) {
        formData.append('language', languageSelect.value);
    }
    
    if (dateInput.value) {
        formData.append('date', dateInput.value);
    }
    
    formData.append('skip_notifications', skipNotificationsCheckbox.checked);
    
    // Блокируем кнопку отправки
    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Загрузка...';
    
    try {
        // Отправляем запрос
        const endpoint = isAudio ? '/api/upload-audio' : '/api/upload-transcript';
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Ошибка при загрузке файла');
        }
        
        const data = await response.json();
        
        // Показываем сообщение об успехе
        showAlert('Файл успешно загружен и поставлен в очередь на обработку', 'success');
        
        // Сбрасываем форму
        form.reset();
        
        // Устанавливаем текущую задачу и начинаем проверку статуса
        currentTaskId = data.task_id;
        startStatusCheck(currentTaskId);
        
        // Обновляем список задач
        loadTasksList();
        
    } catch (error) {
        showAlert(`Ошибка: ${error.message}`, 'danger');
    } finally {
        // Разблокируем кнопку отправки
        submitButton.disabled = false;
        submitButton.textContent = 'Загрузить и обработать';
    }
}

/**
 * Начинает периодическую проверку статуса задачи
 */
function startStatusCheck(taskId) {
    // Очищаем предыдущий интервал, если он был
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }
    
    // Сразу проверяем статус
    checkTaskStatus(taskId);
    
    // Устанавливаем интервал проверки
    statusCheckInterval = setInterval(() => {
        checkTaskStatus(taskId);
    }, 3000); // Проверяем каждые 3 секунды
}

/**
 * Проверяет статус задачи
 */
async function checkTaskStatus(taskId) {
    try {
        const response = await fetch(`/api/tasks/${taskId}`);
        
        if (!response.ok) {
            throw new Error('Не удалось получить статус задачи');
        }
        
        const taskData = await response.json();
        
        // Обновляем интерфейс
        updateTaskStatusUI(taskData);
        
        // Если задача завершена или произошла ошибка, останавливаем проверку
        if (taskData.status === 'completed' || taskData.status === 'failed') {
            clearInterval(statusCheckInterval);
            
            // Обновляем список задач
            loadTasksList();
        }
        
    } catch (error) {
        console.error('Ошибка при проверке статуса задачи:', error);
    }
}

/**
 * Обновляет интерфейс с информацией о статусе задачи
 */
function updateTaskStatusUI(taskData) {
    const statusContainer = document.getElementById('taskStatus');
    if (!statusContainer) return;
    
    // Очищаем контейнер
    statusContainer.innerHTML = '';
    
    // Создаем карточку статуса
    const card = document.createElement('div');
    card.className = 'card';
    
    // Определяем цвет заголовка в зависимости от статуса
    let headerClass = 'bg-info';
    if (taskData.status === 'completed') {
        headerClass = 'bg-success';
    } else if (taskData.status === 'failed') {
        headerClass = 'bg-danger';
    }
    
    // Создаем заголовок карточки
    const cardHeader = document.createElement('div');
    cardHeader.className = `card-header ${headerClass} text-white`;
    cardHeader.textContent = `Задача #${taskData.task_id.substring(0, 8)}`;
    
    // Создаем тело карточки
    const cardBody = document.createElement('div');
    cardBody.className = 'card-body';
    
    // Добавляем статус
    const statusText = document.createElement('p');
    statusText.className = 'status-message';
    statusText.textContent = `Статус: ${getStatusText(taskData.status)}`;
    cardBody.appendChild(statusText);
    
    // Добавляем сообщение
    const messageText = document.createElement('p');
    messageText.className = 'status-message';
    messageText.textContent = taskData.message;
    cardBody.appendChild(messageText);
    
    // Добавляем прогресс-бар
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress mb-3';
    
    const progressBar = document.createElement('div');
    progressBar.className = `progress-bar ${getProgressBarClass(taskData.status)}`;
    progressBar.style.width = `${taskData.progress * 100}%`;
    progressBar.setAttribute('aria-valuenow', taskData.progress * 100);
    progressBar.setAttribute('aria-valuemin', 0);
    progressBar.setAttribute('aria-valuemax', 100);
    progressBar.textContent = `${Math.round(taskData.progress * 100)}%`;
    
    progressContainer.appendChild(progressBar);
    cardBody.appendChild(progressContainer);
    
    // Если задача завершена успешно, добавляем ссылки для скачивания
    if (taskData.status === 'completed' && taskData.result) {
        const downloadLinks = document.createElement('div');
        downloadLinks.className = 'mt-3';
        
        // Ссылка на Markdown
        const mdLink = document.createElement('a');
        mdLink.href = `/api/download/${taskData.task_id}/markdown`;
        mdLink.className = 'btn btn-primary me-2';
        mdLink.textContent = 'Скачать Markdown';
        mdLink.target = '_blank';
        downloadLinks.appendChild(mdLink);
        
        // Ссылка на JSON
        const jsonLink = document.createElement('a');
        jsonLink.href = `/api/download/${taskData.task_id}/json`;
        jsonLink.className = 'btn btn-secondary';
        jsonLink.textContent = 'Скачать JSON';
        jsonLink.target = '_blank';
        downloadLinks.appendChild(jsonLink);
        
        cardBody.appendChild(downloadLinks);
    }
    
    // Собираем карточку
    card.appendChild(cardHeader);
    card.appendChild(cardBody);
    
    // Добавляем карточку в контейнер
    statusContainer.appendChild(card);
}

/**
 * Загружает список задач
 */
async function loadTasksList() {
    const tasksListContainer = document.getElementById('tasksList');
    if (!tasksListContainer) return;
    
    try {
        const response = await fetch('/api/tasks');
        
        if (!response.ok) {
            throw new Error('Не удалось загрузить список задач');
        }
        
        const tasks = await response.json();
        
        // Очищаем контейнер
        tasksListContainer.innerHTML = '';
        
        // Если задач нет, показываем сообщение
        if (tasks.length === 0) {
            tasksListContainer.innerHTML = '<div class="alert alert-info">Нет задач для отображения</div>';
            return;
        }
        
        // Создаем список задач
        const list = document.createElement('div');
        list.className = 'list-group';
        
        // Добавляем задачи в список
        tasks.forEach(task => {
            const listItem = document.createElement('a');
            listItem.href = '#';
            listItem.className = `list-group-item list-group-item-action ${getStatusClass(task.status)}`;
            listItem.onclick = (e) => {
                e.preventDefault();
                currentTaskId = task.task_id;
                checkTaskStatus(task.task_id);
            };
            
            // Добавляем информацию о задаче
            const taskInfo = document.createElement('div');
            taskInfo.className = 'd-flex w-100 justify-content-between';
            
            const taskTitle = document.createElement('h5');
            taskTitle.className = 'mb-1';
            taskTitle.textContent = task.result && task.result.title 
                ? task.result.title 
                : `Задача #${task.task_id.substring(0, 8)}`;
            
            const taskDate = document.createElement('small');
            taskDate.textContent = formatDate(task.created_at);
            
            taskInfo.appendChild(taskTitle);
            taskInfo.appendChild(taskDate);
            
            const taskStatus = document.createElement('p');
            taskStatus.className = 'mb-1';
            taskStatus.textContent = `Статус: ${getStatusText(task.status)}`;
            
            const taskMessage = document.createElement('small');
            taskMessage.textContent = task.message;
            
            listItem.appendChild(taskInfo);
            listItem.appendChild(taskStatus);
            listItem.appendChild(taskMessage);
            
            list.appendChild(listItem);
        });
        
        tasksListContainer.appendChild(list);
        
    } catch (error) {
        console.error('Ошибка при загрузке списка задач:', error);
        tasksListContainer.innerHTML = `<div class="alert alert-danger">Ошибка при загрузке списка задач: ${error.message}</div>`;
    }
}

/**
 * Показывает сообщение пользователю
 */
function showAlert(message, type = 'info') {
    const alertsContainer = document.getElementById('alerts');
    if (!alertsContainer) return;
    
    // Создаем элемент оповещения
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.role = 'alert';
    
    // Добавляем сообщение
    alert.textContent = message;
    
    // Добавляем кнопку закрытия
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'btn-close';
    closeButton.setAttribute('data-bs-dismiss', 'alert');
    closeButton.setAttribute('aria-label', 'Close');
    
    alert.appendChild(closeButton);
    
    // Добавляем оповещение в контейнер
    alertsContainer.appendChild(alert);
    
    // Автоматически скрываем через 5 секунд
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => {
            alertsContainer.removeChild(alert);
        }, 150);
    }, 5000);
}

/**
 * Возвращает текстовое представление статуса
 */
function getStatusText(status) {
    switch (status) {
        case 'pending':
            return 'Ожидание';
        case 'processing':
            return 'Обработка';
        case 'completed':
            return 'Завершено';
        case 'failed':
            return 'Ошибка';
        default:
            return status;
    }
}

/**
 * Возвращает класс для прогресс-бара в зависимости от статуса
 */
function getProgressBarClass(status) {
    switch (status) {
        case 'pending':
            return 'progress-bar-striped progress-bar-animated bg-info';
        case 'processing':
            return 'progress-bar-striped progress-bar-animated';
        case 'completed':
            return 'bg-success';
        case 'failed':
            return 'bg-danger';
        default:
            return '';
    }
}

/**
 * Возвращает класс для элемента списка в зависимости от статуса
 */
function getStatusClass(status) {
    switch (status) {
        case 'pending':
            return 'list-group-item-info';
        case 'processing':
            return 'list-group-item-primary';
        case 'completed':
            return 'list-group-item-success';
        case 'failed':
            return 'list-group-item-danger';
        default:
            return '';
    }
}

/**
 * Форматирует дату в удобочитаемый вид
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}
