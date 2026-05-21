import { auth, BACKEND_URL } from './api.js';

export class ChatSocket {
    constructor(callbacks = {}) {
        this.callbacks = {
            onSearching: callbacks.onSearching || (() => {}),
            onMatched: callbacks.onMatched || (() => {}),
            onPartnerSkipped: callbacks.onPartnerSkipped || (() => {}),
            onMessage: callbacks.onMessage || (() => {}),
            onRateLimitError: callbacks.onRateLimitError || (() => {}),
            onDisconnect: callbacks.onDisconnect || (() => {}),
            onConnect: callbacks.onConnect || (() => {}),
            onSkipped: callbacks.onSkipped || (() => {})
        };
        
        this.socket = null;
        this.pingInterval = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.isClosedPurposely = false;
    }

    connect() {
        if (!auth.isAuthenticated()) {
            console.error('WebSocket connection failed: User is unauthenticated.');
            return;
        }

        this.isClosedPurposely = false;
        const token = auth.getToken();
        const wsUrlObj = new URL(BACKEND_URL);
        const wsProtocol = wsUrlObj.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${wsUrlObj.host}/ws/match?token=${token}`;
        
        console.log(`Connecting to Matchmaker WebSocket: ${wsUrl}`);
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('WebSocket successfully established.');
            this.reconnectAttempts = 0;
            this.reconnectDelay = 2000;
            this.callbacks.onConnect();
            
            // Start 15s Heartbeat Ping interval
            this.startHeartbeat();
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleServerEvent(data);
            } catch (error) {
                console.error('Failed to parse WebSocket JSON event:', error);
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket Error encountered:', error);
        };

        this.socket.onclose = (event) => {
            console.warn(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason}`);
            this.stopHeartbeat();
            this.callbacks.onDisconnect();
            
            if (!this.isClosedPurposely && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.warn(`Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${this.reconnectDelay}ms...`);
                setTimeout(() => {
                    this.reconnectDelay *= 1.5; // Exponential backoff
                    this.connect();
                }, this.reconnectDelay);
            }
        };
    }

    sendMessage(message, imageData = null) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'chat_message',
                message: message,
                image: imageData
            }));
            return true;
        }
        console.error('Cannot send message. WebSocket is not open.');
        return false;
    }

    skip() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'skip'
            }));
            return true;
        }
        return false;
    }

    findMatch() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'find_match'
            }));
            return true;
        }
        return false;
    }

    startHeartbeat() {
        this.stopHeartbeat();
        this.pingInterval = setInterval(() => {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({ type: 'ping' }));
            }
        }, 15000); // 15 seconds
    }

    stopHeartbeat() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    disconnect() {
        this.isClosedPurposely = true;
        this.stopHeartbeat();
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }

    _handleServerEvent(data) {
        switch (data.type) {
            case 'searching':
                this.callbacks.onSearching(data);
                break;
            case 'matched':
                this.callbacks.onMatched(data);
                break;
            case 'partner_skipped':
                this.callbacks.onPartnerSkipped(data);
                break;
            case 'chat_message':
                this.callbacks.onMessage(data);
                break;
            case 'skipped':
                this.callbacks.onSkipped(data);
                break;
            case 'rate_limit_error':
                this.callbacks.onRateLimitError(data);
                break;
            case 'pong':
                break;
            default:
                console.warn('Unhandled WebSocket payload type:', data.type, data);
        }
    }
}
