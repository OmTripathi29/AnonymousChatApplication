// Dynamically resolve backend endpoint for Vercel/Render hosting
// Replace the Render URL with your actual live Render Web Service URL when deploying
export const BACKEND_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? window.location.origin
    : "https://vortexchat-backend.onrender.com";

const API_BASE = BACKEND_URL;

export const auth = {
    isAuthenticated() {
        return !!localStorage.getItem('guest_token');
    },
    
    getToken() {
        return localStorage.getItem('guest_token');
    },
    
    getUsername() {
        return localStorage.getItem('guest_username');
    },
    
    getUserId() {
        return localStorage.getItem('guest_user_id');
    },

    getAvatarHash() {
        return localStorage.getItem('guest_avatar_hash');
    },

    async enterAsGuest() {
        try {
            const response = await fetch(`${API_BASE}/api/v1/auth/guest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) {
                throw new Error('Failed to register anonymous guest session');
            }
            
            const data = await response.json();
            
            // Cache credentials in local storage
            localStorage.setItem('guest_token', data.token);
            localStorage.setItem('guest_username', data.username);
            localStorage.setItem('guest_user_id', data.userId);
            localStorage.setItem('guest_avatar_hash', data.avatarHash);
            
            return data;
        } catch (error) {
            console.error('Guest Auth Error:', error);
            throw error;
        }
    },

    logout() {
        localStorage.clear();
        document.cookie = "guest_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        window.location.reload();
    }
};

export const chatAPI = {
    async fetchRooms() {
        try {
            const response = await fetch(`${API_BASE}/api/v1/rooms`);
            if (!response.ok) throw new Error('Failed to fetch rooms');
            return await response.json();
        } catch (error) {
            console.error('Fetch Rooms Error:', error);
            return [];
        }
    },

    async fetchRoomHistory(roomId) {
        try {
            const response = await fetch(`${API_BASE}/api/v1/rooms/${roomId}/history`);
            if (!response.ok) throw new Error('Failed to fetch room history');
            return await response.json();
        } catch (error) {
            console.error('Fetch History Error:', error);
            return [];
        }
    },

    async createPrivateRoom() {
        try {
            const response = await fetch(`${API_BASE}/api/v1/rooms/private`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (!response.ok) throw new Error('Failed to generate private room');
            return await response.json();
        } catch (error) {
            console.error('Create Private Room Error:', error);
            throw error;
        }
    }
};
