/**
 * API client for the RFP Response Tool
 */
const API = {
    baseUrl: '/api',

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || data.message || 'API request failed');
        }

        return data;
    },

    async uploadFile(endpoint, file, additionalData = {}) {
        const formData = new FormData();
        formData.append('file', file);

        Object.entries(additionalData).forEach(([key, value]) => {
            formData.append(key, value);
        });

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || data.message || 'Upload failed');
        }

        return data;
    },

    async uploadFiles(endpoint, files, additionalData = {}) {
        const formData = new FormData();

        files.forEach((file, index) => {
            formData.append('files', file);
        });

        Object.entries(additionalData).forEach(([key, value]) => {
            formData.append(key, value);
        });

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || data.message || 'Upload failed');
        }

        return data;
    },

    // Session endpoints
    async createSession() {
        return this.request('/session/create', { method: 'POST' });
    },

    async getSession(sessionId) {
        return this.request(`/session/${sessionId}`);
    },

    async deleteSession(sessionId) {
        return this.request(`/session/${sessionId}`, { method: 'DELETE' });
    },

    // RFP endpoints
    async uploadRFP(file, sessionId = null) {
        const data = sessionId ? { session_id: sessionId } : {};
        return this.uploadFile('/rfp/upload', file, data);
    },

    async getRequests(sessionId) {
        return this.request(`/rfp/${sessionId}/requests`);
    },

    async updateRequest(sessionId, requestId, updates) {
        return this.request(`/rfp/${sessionId}/requests/${requestId}`, {
            method: 'PUT',
            body: JSON.stringify(updates)
        });
    },

    async bulkUpdateRequests(sessionId, updates) {
        return this.request(`/rfp/${sessionId}/requests/bulk`, {
            method: 'PUT',
            body: JSON.stringify({ updates })
        });
    },

    // Document endpoints
    async uploadDocuments(sessionId, files) {
        return this.uploadFiles('/documents/upload', files, { session_id: sessionId });
    },

    async getDocuments(sessionId) {
        return this.request(`/documents/${sessionId}`);
    },

    async updateDocument(sessionId, docId, updates) {
        return this.request(`/documents/${sessionId}/${docId}`, {
            method: 'PUT',
            body: JSON.stringify(updates)
        });
    },

    async deleteDocument(sessionId, docId) {
        return this.request(`/documents/${sessionId}/${docId}`, { method: 'DELETE' });
    },

    // Objections endpoints
    async getObjectionPresets() {
        return this.request('/objections/presets');
    },

    // Analysis endpoints
    async runAnalysis(sessionId) {
        return this.request(`/analyze/${sessionId}`, { method: 'POST' });
    },

    // Generate endpoints
    async generateResponse(sessionId, includeReasoning = false) {
        const response = await fetch(`${this.baseUrl}/generate/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ include_reasoning: includeReasoning })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Generation failed');
        }

        // Extract filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'rfp_response.docx';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)["']?/i);
            if (match) {
                filename = decodeURIComponent(match[1]);
            }
        }

        // Return blob and filename for download
        const blob = await response.blob();
        return { blob, filename };
    }
};
