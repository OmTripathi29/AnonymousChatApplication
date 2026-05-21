import { auth } from './api.js';

export const ui = {
    // Views
    authView: document.getElementById('auth-view'),
    appView: document.getElementById('app-view'),
    
    // Auth elements
    btnEnterGuest: document.getElementById('btn-enter-guest'),
    userPill: document.getElementById('user-pill'),
    myAvatar: document.getElementById('my-avatar'),
    myUsername: document.getElementById('my-username'),
    
    // Header theme toggle
    themeToggle: document.getElementById('theme-toggle'),

    // 1v1 Matching elements
    partnerAvatar: document.getElementById('partner-avatar'),
    partnerDisplayName: document.getElementById('partner-display-name'),
    partnerStatusText: document.getElementById('partner-status-text'),
    partnerStatusDot: document.getElementById('partner-status-dot'),
    btnSkipChat: document.getElementById('btn-skip-chat'),
    btnNextChat: document.getElementById('btn-next-chat'),
    searchingShimmer: document.getElementById('searching-shimmer'),
    
    // Chat interface elements
    messagesPanel: document.getElementById('messages-panel'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    btnSendMessage: document.getElementById('btn-send-message'),
    imageInput: document.getElementById('image-input'),
    rateLimitToast: document.getElementById('rate-limit-toast'),
    
    // Zoom Modal
    imageZoomModal: document.getElementById('image-zoom-modal'),
    imageZoomImg: document.getElementById('image-zoom-img'),

    // Ad / Interstitial elements
    interstitialModal: document.getElementById('interstitial-modal'),
    countdownVal: document.getElementById('countdown-val'),
    btnCloseInterstitial: document.getElementById('btn-close-interstitial'),

    showView(viewName) {
        if (viewName === 'auth') {
            this.authView.classList.remove('hidden');
            this.appView.classList.add('hidden');
        } else {
            this.authView.classList.add('hidden');
            this.appView.classList.remove('hidden');
            this._setupUserPill();
        }
    },

    _setupUserPill() {
        if (auth.isAuthenticated()) {
            this.userPill.classList.remove('hidden');
            const username = auth.getUsername();
            const avatarHash = auth.getAvatarHash();
            this.myUsername.textContent = username;
            // Fetch stunning avatar representations
            this.myAvatar.src = `https://robohash.org/${avatarHash}.png?set=set4&size=80x80`;
        }
    },

    setSearchingState() {
        // Display shimmer inside messages stream
        this.searchingShimmer.classList.remove('hidden');
        
        // Match header states
        this.partnerAvatar.classList.add('hidden');
        this.partnerDisplayName.textContent = "Matching Pool...";
        this.partnerStatusText.textContent = "Looking for an active partner...";
        this.partnerStatusDot.className = "w-2.5 h-2.5 rounded-full bg-amber-500 animate-ping";
        
        // Enable Skip during searching (allows exiting queue)
        this.btnSkipChat.classList.remove('hidden');
        this.btnNextChat.classList.add('hidden');

        // Disable composer
        this.chatInput.disabled = true;
        this.btnSendMessage.disabled = true;
        this.chatInput.placeholder = "Searching for a partner... please wait";
        this.chatInput.value = "";
    },

    setMatchedState(partnerName, avatarHash) {
        // Hide shimmer
        this.searchingShimmer.classList.add('hidden');
        
        // Match header states
        this.partnerAvatar.classList.remove('hidden');
        this.partnerAvatar.src = `https://robohash.org/${avatarHash}.png?set=set4&size=80x80`;
        this.partnerDisplayName.textContent = partnerName;
        this.partnerStatusText.textContent = "Connected & Active";
        this.partnerStatusDot.className = "w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse";
        
        // Skip vs Next Chat Button states
        this.btnSkipChat.classList.remove('hidden');
        this.btnNextChat.classList.add('hidden');

        // Enable composer
        this.chatInput.disabled = false;
        this.btnSendMessage.disabled = false;
        this.chatInput.placeholder = "Type a message anonymously...";
        this.chatInput.focus();

        this.appendSystemNotice(`✨ Connected to <b>${partnerName}</b>! Say hello.`);
    },

    setPartnerSkippedState() {
        this.searchingShimmer.classList.add('hidden');
        
        // Match header states
        this.partnerAvatar.classList.add('hidden');
        this.partnerDisplayName.textContent = "Connection Closed";
        this.partnerStatusText.textContent = "Partner disconnected.";
        this.partnerStatusDot.className = "w-2.5 h-2.5 rounded-full bg-rose-600";
        
        // Button states: Hide Skip, Show Next Chat
        this.btnSkipChat.classList.add('hidden');
        this.btnNextChat.classList.remove('hidden');

        // Disable composer
        this.chatInput.disabled = true;
        this.btnSendMessage.disabled = true;
        this.chatInput.placeholder = "Chat finished. Click 'Next Chat' to start matching.";
        this.chatInput.value = "";

        this.appendSystemNotice("❌ Your partner skipped the chat.");
    },

    setSelfSkippedState() {
        this.searchingShimmer.classList.add('hidden');
        
        // Match header states
        this.partnerAvatar.classList.add('hidden');
        this.partnerDisplayName.textContent = "Disconnected";
        this.partnerStatusText.textContent = "You left the chat.";
        this.partnerStatusDot.className = "w-2.5 h-2.5 rounded-full bg-slate-600";
        
        // Button states: Hide Skip, Show Next Chat
        this.btnSkipChat.classList.add('hidden');
        this.btnNextChat.classList.remove('hidden');

        // Disable composer
        this.chatInput.disabled = true;
        this.btnSendMessage.disabled = true;
        this.chatInput.placeholder = "Chat skipped. Click 'Next Chat' to search again.";
        this.chatInput.value = "";

        this.appendSystemNotice("⚠️ You skipped the chat.");
    },

    appendMessage(msg, isSent) {
        const item = document.createElement('div');
        item.className = `flex flex-col ${isSent ? 'items-end' : 'items-start'} w-full max-w-full`;
        
        const timestamp = new Date((msg.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const avatarUrl = `https://robohash.org/${msg.userId}.png?set=set4&size=40x40`;

        let mediaContent = '';
        if (msg.image) {
            mediaContent = `<img src="${msg.image}" class="chat-shared-image max-w-[240px] md:max-w-[320px] rounded-xl border border-white/10 my-2 cursor-pointer hover:opacity-90 hover:scale-[1.01] active:scale-[0.99] transition-all duration-200 block">`;
        }

        let bubbleContent = '';
        if (msg.message) {
            bubbleContent = `<span class="text-sm font-medium leading-relaxed block">${msg.message}</span>`;
        }

        if (isSent) {
            item.innerHTML = `
                <div class="flex flex-col items-end w-full max-w-[85%]">
                    ${mediaContent}
                    ${msg.message ? `
                    <div class="w-full flex justify-end">
                        <div class="message-bubble message-sent shadow-md shadow-primary-500/10">
                            ${bubbleContent}
                        </div>
                    </div>` : ''}
                    <span class="text-[9px] text-slate-500 font-mono mt-1 mr-1">${timestamp}</span>
                </div>
            `;
        } else {
            item.innerHTML = `
                <div class="flex items-start gap-2.5 w-full max-w-[85%]">
                    <img class="w-8 h-8 rounded-full bg-slate-800 shrink-0 mt-0.5 border border-white/10" src="${avatarUrl}" alt="avatar">
                    <div class="flex flex-col items-start w-full">
                        <span class="text-[10px] font-bold text-slate-500 mb-1 flex items-center gap-1.5">
                            ${msg.username}
                        </span>
                        ${mediaContent}
                        ${msg.message ? `
                        <div class="w-full flex justify-start">
                            <div class="message-bubble message-received shadow-sm">
                                ${bubbleContent}
                            </div>
                        </div>` : ''}
                        <span class="text-[9px] text-slate-500 font-mono mt-1 ml-1">${timestamp}</span>
                    </div>
                </div>
            `;
        }
        
        this.messagesPanel.appendChild(item);

        // Bind image zoom click listeners
        const imageElement = item.querySelector('.chat-shared-image');
        if (imageElement) {
            imageElement.addEventListener('click', () => {
                this.imageZoomImg.src = imageElement.src;
                this.imageZoomModal.classList.remove('hidden');
            });
        }

        this.scrollToBottom();
    },

    appendSystemNotice(text) {
        const item = document.createElement('div');
        item.className = 'system-notice font-mono';
        item.innerHTML = text;
        this.messagesPanel.appendChild(item);
        this.scrollToBottom();
    },

    clearChatStream() {
        // Keep the searching shimmer div intact
        const shimmer = this.searchingShimmer.cloneNode(true);
        this.messagesPanel.innerHTML = '';
        this.messagesPanel.appendChild(shimmer);
        this.searchingShimmer = document.getElementById('searching-shimmer');
    },

    scrollToBottom() {
        this.messagesPanel.scrollTop = this.messagesPanel.scrollHeight;
    },

    triggerRateLimitAlert() {
        this.rateLimitToast.classList.remove('hidden');
        setTimeout(() => {
            this.rateLimitToast.classList.add('hidden');
        }, 3000);
    },

    triggerInterstitialAd(callback) {
        this.interstitialModal.classList.remove('hidden');
        let counter = 3;
        this.countdownVal.textContent = counter;
        
        const interval = setInterval(() => {
            counter--;
            this.countdownVal.textContent = counter;
            if (counter <= 0) {
                clearInterval(interval);
                this.interstitialModal.classList.add('hidden');
                callback(); // Execute callback to start matching re-entry
            }
        }, 1000);
    },

    setupZoomModal() {
        this.imageZoomModal.addEventListener('click', () => {
            this.imageZoomModal.classList.add('hidden');
            this.imageZoomImg.src = '';
        });
    }
};
