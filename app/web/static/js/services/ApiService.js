/**
 * Unified API Service для всех HTTP запросов
 * Provides consistent interface for backend communication
 */
class ApiService {
    constructor() {
        this.baseURL = '';
        this.defaultHeaders = {
            'Content-Type': 'application/json',
        };
        this.cache = new Map();
        this.pendingRequests = new Map();
        this.retryConfig = {
            maxRetries: 3,
            retryDelay: 1000,
            retryMultiplier: 2
        };
    }

    setAuthToken(token) {
        if (token) {
            this.defaultHeaders['Authorization'] = `Bearer ${token}`;
        } else {
            delete this.defaultHeaders['Authorization'];
        }
    }

    async request(method, endpoint, options = {}) {
        const url = this.baseURL + endpoint;
        const requestKey = `${method}:${url}:${JSON.stringify(options.body || {})}`;
        
        if (this.pendingRequests.has(requestKey)) {
            return this.pendingRequests.get(requestKey);
        }

        const requestPromise = this._executeRequest(method, url, options);
        this.pendingRequests.set(requestKey, requestPromise);
        
        try {
            const result = await requestPromise;
            return result;
        } finally {
            this.pendingRequests.delete(requestKey);
        }
    }
    async _executeRequest(method, url, options, attempt = 1) {
        const config = {
            method: method.toUpperCase(),
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };

        if (options.body && typeof options.body === 'object' && !options.body instanceof FormData) {
            config.body = JSON.stringify(options.body);
        }

        try {
            console.debug(`API Request [${method.toUpperCase()}] ${url}`, { attempt, config });
            
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const errorData = await this._parseErrorResponse(response);
                throw new ApiError(response.status, errorData.message || response.statusText, errorData);
            }

            const data = await this._parseResponse(response);
            console.debug(`API Response [${method.toUpperCase()}] ${url}`, { status: response.status, data });
            
            return data;
            
        } catch (error) {
            console.error(`API Error [${method.toUpperCase()}] ${url}`, { attempt, error });
            
            if (this._shouldRetry(error, attempt)) {
                const delay = this.retryConfig.retryDelay * Math.pow(this.retryConfig.retryMultiplier, attempt - 1);
                console.warn(`Retrying request in ${delay}ms (attempt ${attempt + 1}/${this.retryConfig.maxRetries + 1})`);
                
                await new Promise(resolve => setTimeout(resolve, delay));
                return this._executeRequest(method, url, options, attempt + 1);
            }
            
            throw error;
        }
    }

    async _parseResponse(response) {
        const contentType = response.headers.get('content-type');
        
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        } else if (contentType && contentType.includes('text/')) {
            return await response.text();
        } else {
            return await response.blob();
        }
    }

    async _parseErrorResponse(response) {
        try {
            return await response.json();
        } catch (e) {
            return { message: response.statusText };
        }
    }
    _shouldRetry(error, attempt) {
        if (attempt >= this.retryConfig.maxRetries) return false;
        
        if (error instanceof TypeError || 
            (error instanceof ApiError && error.status >= 500)) {
            return true;
        }
        
        return false;
    }

    // HTTP Method shortcuts
    async get(endpoint, options = {}) {
        return this.request('GET', endpoint, options);
    }

    async post(endpoint, data, options = {}) {
        return this.request('POST', endpoint, { body: data, ...options });
    }

    async put(endpoint, data, options = {}) {
        return this.request('PUT', endpoint, { body: data, ...options });
    }

    async delete(endpoint, options = {}) {
        return this.request('DELETE', endpoint, options);
    }

    // File upload with progress tracking
    async uploadFile(endpoint, file, metadata = {}, onProgress = null) {
        const formData = new FormData();
        formData.append('file', file);
        
        Object.entries(metadata).forEach(([key, value]) => {
            formData.append(key, value);
        });

        if (onProgress && typeof onProgress === 'function') {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                
                xhr.upload.addEventListener('progress', (event) => {
                    if (event.lengthComputable) {
                        const percentComplete = (event.loaded / event.total) * 100;
                        onProgress(percentComplete);
                    }
                });

                xhr.addEventListener('load', () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            resolve(JSON.parse(xhr.responseText));
                        } catch (e) {
                            resolve(xhr.responseText);
                        }
                    } else {
                        reject(new ApiError(xhr.status, xhr.statusText));
                    }
                });

                xhr.open('POST', this.baseURL + endpoint);
                xhr.send(formData);
            });
        }

        return this.post(endpoint, formData, { headers: {} });
    }
}
// Custom API Error class
class ApiError extends Error {
    constructor(status, message, data = null) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.data = data;
    }
}

// Create singleton instance
const apiService = new ApiService();

// Export for global use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ApiService, ApiError, apiService };
} else {
    window.ApiService = ApiService;
    window.ApiError = ApiError;
    window.apiService = apiService;
}
