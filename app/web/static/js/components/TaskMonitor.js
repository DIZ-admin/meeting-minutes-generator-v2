/**
 * Task Monitor Component - Real-time task tracking
 */
class TaskMonitor {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.tasks = new Map();
        this.refreshInterval = null;
        this.init();
    }

    init() {
        this.render();
        this.startAutoRefresh();
    }

    render() {
        this.container.innerHTML = `
            <div class="task-monitor-dashboard">
                <div class="dashboard-header">
                    <h4><i class="fas fa-tasks"></i> Active Tasks</h4>
                    <div class="dashboard-controls">
                        <button class="btn btn-sm btn-outline-primary" onclick="this.refresh()">
                            <i class="fas fa-sync-alt"></i> Refresh
                        </button>
                    </div>
                </div>
                <div class="tasks-container" id="tasksContainer">
                    <div class="loading-state">
                        <div class="spinner-border spinner-border-sm" role="status"></div>
                        <span class="ms-2">Loading tasks...</span>
                    </div>
                </div>
            </div>
        `;
    }

    async loadTasks() {
        try {
            const response = await fetch('/api/tasks');
            const tasks = await response.json();
            this.displayTasks(tasks);
        } catch (error) {
            console.error('Failed to load tasks:', error);
            this.showError('Failed to load tasks');
        }
    }

    displayTasks(tasks) {
        const container = this.container.querySelector('#tasksContainer');
        
        if (!tasks || tasks.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-inbox fa-3x text-muted"></i>
                    <h5 class="mt-3 text-muted">No Active Tasks</h5>
                </div>
            `;
            return;
        }

        const tasksHTML = tasks.map(task => this.renderTaskCard(task)).join('');
        container.innerHTML = tasksHTML;
    }