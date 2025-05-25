/**
 * Application constants and configuration
 */
const APP_CONFIG = {
    API_BASE_URL: '',
    MAX_FILE_SIZE: 100 * 1024 * 1024, // 100MB
    SUPPORTED_TYPES: ['audio/mpeg', 'audio/wav', 'audio/m4a', 'application/json'],
    POLLING_INTERVAL: 2000,
    MAX_RETRIES: 3
};

/**
 * Utility functions for common operations
 */
const utils = {
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        document.body.appendChild(notification);
        setTimeout(() => notification.remove(), 5000);
    },

    validateFile(file) {
        if (file.size > APP_CONFIG.MAX_FILE_SIZE) {
            throw new Error(`File too large: ${utils.formatFileSize(file.size)}`);
        }
        if (!APP_CONFIG.SUPPORTED_TYPES.includes(file.type)) {
            throw new Error(`Unsupported file type: ${file.type}`);
        }
        return true;
    }
};

// Export for global use
if (typeof window !== 'undefined') {
    window.APP_CONFIG = APP_CONFIG;
    window.utils = utils;
}
