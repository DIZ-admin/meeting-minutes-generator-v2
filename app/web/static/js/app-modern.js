/**
 * Modern Meeting Protocol Generator - Main Application
 * Component-based architecture with real-time updates
 */

// Application state management
class AppState {
    constructor() {
        this.tasks = new Map();
        this.currentUser = null;
        this.listeners = new Map();
    }

    subscribe(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => callback(data));
        }
    }

    updateTask(taskId, taskData) {
        this.tasks.set(taskId, taskData);
        this.emit('taskUpdated', { taskId, taskData });
    }

    getTasks() {
        return Array.from(this.tasks.values());
    }
}

// Global app instance
const app = {
    state: new AppState(),
    components: {},
    services: {},
    init() {
        this.initServices();
        this.initComponents();
        this.attachEventListeners();
        this.loadInitialData();
    }
};
// Service initialization
app.initServices = function() {
    this.services.api = window.apiService;
    
    this.services.ws = {
        connections: new Map(),
        connect(endpoint, onMessage) {
            const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${endpoint}`;
            const ws = new WebSocket(wsUrl);
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                onMessage(data);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            return ws;
        }
    };
};

// Component initialization
app.initComponents = function() {
    // File uploader component
    if (document.getElementById('fileUploader')) {
        this.components.fileUploader = new FileUploader('fileUploader', {
            maxSize: 100 * 1024 * 1024,
            onUpload: this.handleFileUpload.bind(this)
        });
    }
    
    // Task monitor component  
    if (document.getElementById('taskMonitor')) {
        this.components.taskMonitor = new TaskMonitor('taskMonitor');
        this.state.subscribe('taskUpdated', (data) => {
            this.components.taskMonitor.updateTask(data.taskId, data.taskData);
        });
    }
};

// Event listeners
app.attachEventListeners = function() {
    // Real-time task updates via WebSocket
    if (this.services.ws) {
        this.services.ws.connect('/ws/system', (data) => {
            if (data.type === 'task_update') {
                this.state.updateTask(data.task_id, data.task);
            }
        });
    }
    
    // Handle page visibility change for efficient polling
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            this.pausePolling();
        } else {
            this.resumePolling();
        }
    });
};
// File upload handler
app.handleFileUpload = async function(files, metadata) {
    try {
        const uploadPromises = files.map(file => {
            return this.services.api.uploadFile('/api/upload', file, metadata, (progress) => {
                console.log(`Upload progress: ${progress}%`);
            });
        });
        
        const results = await Promise.all(uploadPromises);
        results.forEach(result => {
            if (result.task_id) {
                this.state.updateTask(result.task_id, result);
            }
        });
        
        this.showNotification('Files uploaded successfully!', 'success');
        
    } catch (error) {
        console.error('Upload failed:', error);
        this.showNotification('Upload failed: ' + error.message, 'error');
    }
};

// Load initial data
app.loadInitialData = async function() {
    try {
        const tasks = await this.services.api.get('/api/tasks');
        tasks.forEach(task => {
            this.state.updateTask(task.id, task);
        });
    } catch (error) {
        console.error('Failed to load initial data:', error);
    }
};

// Utility methods
app.showNotification = function(message, type = 'info') {
    if (window.utils && window.utils.showNotification) {
        window.utils.showNotification(message, type);
    }
};

app.pausePolling = function() {
    // Stop any active polling when page is hidden
    console.log('Pausing background updates');
};

app.resumePolling = function() {
    // Resume polling when page becomes visible
    console.log('Resuming background updates');
    this.loadInitialData();
};

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    app.init();
});

// Export for global use
window.MeetingApp = app;
