import { auth } from './api.js';
import { ui } from './ui.js';
import { ChatSocket } from './websocket.js';

let activeSocket = null;

// 1. Initialize Application
async function init() {
    initTheme();
    setupEventListeners();
    ui.setupZoomModal();
    
    if (auth.isAuthenticated()) {
        ui.showView('app');
        connectSocket();
    } else {
        ui.showView('auth');
    }
}

// Initialize Theme Button State
function initTheme() {
    const isDark = document.documentElement.classList.contains('dark');
    if (ui.themeToggle) {
        ui.themeToggle.textContent = isDark ? '☀️' : '🌙';
    }
}

// 2. Setup Event Listeners
function setupEventListeners() {
    // Guest Entry Trigger
    ui.btnEnterGuest.addEventListener('click', async () => {
        try {
            ui.btnEnterGuest.disabled = true;
            ui.btnEnterGuest.innerHTML = '<span>Entering Vortex Matching...</span>';
            await auth.enterAsGuest();
            ui.showView('app');
            connectSocket();
        } catch (error) {
            alert('Failed to enter anonymous matching session. Make sure the backend server is running.');
            ui.btnEnterGuest.disabled = false;
            ui.btnEnterGuest.innerHTML = '<span>Enter 1v1 Anonymous Match</span>';
        }
    });

    // Chat Message Form Submission
    ui.chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = ui.chatInput.value.trim();
        if (!text) return;
        
        if (activeSocket) {
            // Append message locally for instant UI update
            const selfMsg = {
                userId: auth.getUserId(),
                username: auth.getUsername(),
                message: text,
                timestamp: Date.now() / 1000
            };
            ui.appendMessage(selfMsg, true);
            
            // Transmit over WebSocket
            const success = activeSocket.sendMessage(text);
            if (success) {
                ui.chatInput.value = '';
            }
        }
    });

    // Image Input Selection Change
    ui.imageInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleImageUpload(file);
            ui.imageInput.value = ''; // Reset input to allow selecting same file again
        }
    });

    // Skip Active Chat Partner
    ui.btnSkipChat.addEventListener('click', () => {
        if (activeSocket) {
            activeSocket.skip();
            ui.setSelfSkippedState();
        }
    });

    // Next Random Chat Matchmaker Re-Entry (Count-down monetization trigger!)
    ui.btnNextChat.addEventListener('click', () => {
        ui.triggerInterstitialAd(() => {
            ui.clearChatStream();
            ui.setSearchingState();
            if (activeSocket) {
                activeSocket.findMatch();
            }
        });
    });

    // Theme Toggle supporting dark/light switching
    if (ui.themeToggle) {
        ui.themeToggle.addEventListener('click', () => {
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            ui.themeToggle.textContent = isDark ? '☀️' : '🌙';
        });
    }

    // Drag-and-Drop File Upload onto the messages panel
    const p = ui.messagesPanel;
    
    ['dragenter', 'dragover'].forEach(eventName => {
        p.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            p.classList.add('bg-primary-950/10', 'border-2', 'border-dashed', 'border-primary-500/20');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        p.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            p.classList.remove('bg-primary-950/10', 'border-2', 'border-dashed', 'border-primary-500/20');
        }, false);
    });

    p.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const file = dt.files[0];
        if (file && file.type.startsWith('image/')) {
            handleImageUpload(file);
        }
    });
}

// 3. Establish Resilient WebSocket Connection & Map State Events
function connectSocket() {
    if (activeSocket) {
        activeSocket.disconnect();
    }
    
    ui.setSearchingState();
    
    activeSocket = new ChatSocket({
        onConnect: () => {
            console.log('Matchmaker WebSocket connection open.');
        },
        onDisconnect: () => {
            ui.appendSystemNotice(`⚠️ <i>Disconnected from matchmaking server. Reconnecting...</i>`);
        },
        onSearching: () => {
            ui.clearChatStream();
            ui.setSearchingState();
        },
        onMatched: (data) => {
            ui.setMatchedState(data.partnerName, data.avatarHash);
        },
        onPartnerSkipped: () => {
            ui.setPartnerSkippedState();
        },
        onSkipped: () => {
            ui.setSelfSkippedState();
        },
        onMessage: (msg) => {
            // Messages from partner are sent with matches to true
            ui.appendMessage(msg, false);
        },
        onRateLimitError: (err) => {
            ui.triggerRateLimitAlert();
            ui.appendSystemNotice(`⚠️ <span class="text-rose-500 font-bold font-mono">${err.message}</span>`);
        }
    });
    
    activeSocket.connect();
}

// 4. Client-side Image Processing, Scale-down & JPEG Compression
function handleImageUpload(file) {
    if (!file || !file.type.startsWith('image/')) return;
    
    // Check file size (optional client-side warning, e.g., if extremely large)
    const reader = new FileReader();
    reader.onload = function(event) {
        const img = new Image();
        img.onload = function() {
            // Compress and scale to max 800px width for fast WebSocket buffer transfer
            const maxW = 800;
            let w = img.width;
            let h = img.height;
            
            if (w > maxW) {
                h = Math.round((h * maxW) / w);
                w = maxW;
            }
            
            const canvas = document.createElement('canvas');
            canvas.width = w;
            canvas.height = h;
            
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, w, h);
            
            // High quality JPEG compression (70% maintains stunning details at 10-20x compression factor)
            const compressedBase64 = canvas.toDataURL('image/jpeg', 0.7);
            
            // Display immediately in user's UI
            const selfMsg = {
                userId: auth.getUserId(),
                username: auth.getUsername(),
                message: "",
                image: compressedBase64,
                timestamp: Date.now() / 1000
            };
            ui.appendMessage(selfMsg, true);
            
            // Forward base64 binary block over WebSocket channel
            if (activeSocket) {
                activeSocket.sendMessage("", compressedBase64);
            }
        };
        img.src = event.target.result;
    };
    reader.readAsDataURL(file);
}

// Boot application
if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
