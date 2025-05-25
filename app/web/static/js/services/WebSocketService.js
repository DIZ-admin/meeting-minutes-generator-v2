/**
 * WebSocket Service для real-time коммуникации
 */
class WebSocketService {
    constructor() {
        this.connections = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.heartbeatInterval = 30000;
        this.messageHandlers = new Map();
    }

    connectToTask(taskId, onMessage, onError = null) {
        const wsUrl = `${this.getWebSocketUrl()}/ws/tasks/${taskId}`;
        return this._createConnection(wsUrl, {
            onMessage: (data) => {
                if (data.type === 'progress') {
                    onMessage(data);
                }
            },
            onError: onError || ((error) => {
                console.error(`WebSocket error for task ${taskId}:`, error);
            }),
            reconnect: true
        });
    }

    connectToSystem(onMessage, onError = null) {
        const wsUrl = `${this.getWebSocketUrl()}/ws/system`;
        return this._createConnection(wsUrl, {
            onMessage: onMessage,
            onError: onError || ((error) => {
                console.error('System WebSocket error:', error);
            }),
            reconnect: true
        });
    }

    _createConnection(url, options) {
        const connectionId = this._generateConnectionId();
        
        try {
            const ws = new WebSocket(url);
            
            const connection = {
                id: connectionId,
                ws: ws,
                url: url,
                options: options,
                reconnectAttempts: 0,
                lastHeartbeat: Date.now(),
                heartbeatTimer: null
            };

            this._setupConnectionHandlers(connection);
            this.connections.set(connectionId, connection);
            
            return connectionId;
            
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            if (options.onError) {
                options.onError(error);
            }
            return null;
        }
    }