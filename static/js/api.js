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
    async uploadRFP(file, sessionId = null, onProgress = null) {
        const data = sessionId ? { session_id: sessionId } : {};
        const startResponse = await this.uploadFile('/rfp/upload', file, data);

        // If processing in background, poll for completion
        if (startResponse.status === 'processing' && startResponse.job_id) {
            return this.pollUploadStatus(startResponse.job_id, onProgress);
        }

        // Legacy: if server returned results directly (shouldn't happen with new API)
        return startResponse;
    },

    async getUploadStatus(jobId) {
        return this.request(`/rfp/upload/status/${jobId}`);
    },

    async pollUploadStatus(jobId, onProgress = null, pollInterval = 1000, maxWait = 300000) {
        const startTime = Date.now();

        while (Date.now() - startTime < maxWait) {
            const status = await this.getUploadStatus(jobId);

            // Report progress if callback provided
            if (onProgress) {
                onProgress({
                    progress: status.progress || 0,
                    message: status.message || 'Processing...'
                });
            }

            // Check terminal states
            if (status.status === 'completed') {
                return status;  // Contains full results
            }

            if (status.status === 'failed') {
                throw new Error(status.error || status.message || 'Upload processing failed');
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        }

        throw new Error('Upload processing timed out');
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

    async syncRequests(sessionId, requests) {
        return this.request(`/rfp/${sessionId}/requests/sync`, {
            method: 'PUT',
            body: JSON.stringify({ requests })
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

    async getObjections() {
        return this.request('/objections');
    },

    async createObjection(objection) {
        return this.request('/objections', {
            method: 'POST',
            body: JSON.stringify(objection)
        });
    },

    async updateObjection(objectionId, updates) {
        return this.request(`/objections/${objectionId}`, {
            method: 'PUT',
            body: JSON.stringify(updates)
        });
    },

    async deleteObjection(objectionId) {
        return this.request(`/objections/${objectionId}`, {
            method: 'DELETE'
        });
    },

    async reorderObjections(order) {
        return this.request('/objections/reorder', {
            method: 'PUT',
            body: JSON.stringify({ order })
        });
    },

    // Analysis endpoints
    async runAnalysis(sessionId, onProgress = null) {
        // Start analysis (returns immediately with 202)
        const startResponse = await this.request(`/analyze/${sessionId}`, { method: 'POST' });

        // If already running, use existing job
        if (startResponse.status === 'running' || startResponse.status === 'started') {
            // Poll for completion
            return this.pollAnalysisStatus(sessionId, onProgress);
        }

        // If completed synchronously (shouldn't happen with new API, but handle it)
        if (startResponse.status === 'complete') {
            return startResponse;
        }

        throw new Error(startResponse.error || 'Unexpected response from analysis endpoint');
    },

    async getAnalysisStatus(sessionId) {
        return this.request(`/analyze/${sessionId}/status`);
    },

    async pollAnalysisStatus(sessionId, onProgress = null, pollInterval = 1500, maxWait = 600000) {
        const startTime = Date.now();

        while (Date.now() - startTime < maxWait) {
            const status = await this.getAnalysisStatus(sessionId);

            // Report progress if callback provided
            if (onProgress && status.progress !== undefined) {
                onProgress({
                    progress: status.progress,
                    completedChunks: status.completed_chunks,
                    totalChunks: status.total_chunks,
                    message: status.message
                });
            }

            // Check terminal states
            if (status.status === 'completed') {
                return {
                    status: 'complete',
                    suggestions: status.suggestions,
                    message: status.message
                };
            }

            if (status.status === 'failed') {
                throw new Error(status.analysis_error || status.message || 'Analysis failed');
            }

            // For idle status (no job found but analysis complete)
            if (status.status === 'idle' && status.analysis_complete) {
                return {
                    status: 'complete',
                    suggestions: {},
                    message: 'Analysis already completed'
                };
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));
        }

        throw new Error('Analysis timed out');
    },

    // Generate endpoints
    async generateResponse(sessionId, includeReasoning = false, associateInfo = {}) {
        const response = await fetch(`${this.baseUrl}/generate/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                include_reasoning: includeReasoning,
                associate_name: associateInfo.associate_name || '',
                associate_bar: associateInfo.associate_bar || '',
                associate_email: associateInfo.associate_email || ''
            })
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
    },

    // Document Generator endpoints (motion opposition)
    async createDocSession() {
        return this.request('/motion-opposition/create', { method: 'POST' });
    },

    async uploadMotion(file) {
        return this.uploadFile('/motion-opposition/upload', file);
    },

    async getMotionSession(sessionId) {
        return this.request(`/motion-opposition/${sessionId}`);
    },

    async updateMotionSession(sessionId, templateVars) {
        return this.request(`/motion-opposition/${sessionId}`, {
            method: 'PUT',
            body: JSON.stringify({ template_vars: templateVars })
        });
    },

    async suggestDocTitle(sessionId) {
        return this.request(`/motion-opposition/${sessionId}/suggest-title`);
    },

    async generateDocument(sessionId, documentTitle, associateInfo) {
        const response = await fetch(`${this.baseUrl}/motion-opposition/${sessionId}/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                document_title: documentTitle,
                ...associateInfo
            })
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Generation failed');
        }

        // Extract filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'document.docx';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)["']?/i);
            if (match) {
                filename = decodeURIComponent(match[1]);
            }
        }

        // Return blob and filename for download
        const blob = await response.blob();
        return { blob, filename };
    },

    async deleteMotionSession(sessionId) {
        return this.request(`/motion-opposition/${sessionId}`, {
            method: 'DELETE'
        });
    },

    // Users endpoints
    async getUsers() {
        return this.request('/users');
    },

    async getUser(userId) {
        return this.request(`/users/${userId}`);
    },

    async createUser(user) {
        return this.request('/users', {
            method: 'POST',
            body: JSON.stringify(user)
        });
    },

    async updateUser(userId, updates) {
        return this.request(`/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(updates)
        });
    },

    async deleteUser(userId) {
        return this.request(`/users/${userId}`, {
            method: 'DELETE'
        });
    },

    // Templates endpoints
    async getTemplates() {
        return this.request('/templates');
    },

    async getTemplateTypes() {
        return this.request('/templates/types');
    },

    async uploadTemplate(file, uploadedBy, type = 'rfp') {
        return this.uploadFile('/templates/upload', file, { uploaded_by: uploadedBy, type: type });
    },

    async deleteTemplate(templateId) {
        return this.request(`/templates/${templateId}`, {
            method: 'DELETE'
        });
    },

    async downloadTemplate(templateId) {
        const response = await fetch(`${this.baseUrl}/templates/${templateId}/download`);

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Download failed');
        }

        // Extract filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'template.docx';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';\n]+)["']?/i);
            if (match) {
                filename = decodeURIComponent(match[1]);
            }
        }

        const blob = await response.blob();
        return { blob, filename };
    }
};
