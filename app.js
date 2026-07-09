document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const reelUrlInput = document.getElementById('reel-url');
    const pasteBtn = document.getElementById('paste-btn');
    
    const previewArea = document.getElementById('preview-area');
    const previewThumb = document.getElementById('preview-thumb');
    const previewDuration = document.getElementById('preview-duration');
    const previewCreator = document.getElementById('preview-creator');
    const previewTitle = document.getElementById('preview-title');
    const downloadBtn = document.getElementById('download-btn');
    const cancelPreviewBtn = document.getElementById('cancel-preview-btn');
    
    const fetchingLoader = document.getElementById('fetching-loader');
    const successActions = document.getElementById('success-actions');
    const downloadAgainBtn = document.getElementById('download-again-btn');
    
    const historyList = document.getElementById('history-list');
    const historyEmpty = document.getElementById('history-empty');
    const historyCount = document.getElementById('history-count');
    
    const toastContainer = document.getElementById('toast-container');
    
    let currentReelInfo = null;

    // --- Helper: Toast Messages ---
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const iconSvg = type === 'success' 
            ? `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`
            : `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
            
        toast.innerHTML = `
            ${iconSvg}
            <span class="toast-message">${message}</span>
        `;
        
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    // --- Helper: Reset UI ---
    function resetUIState() {
        previewArea.classList.add('hidden');
        fetchingLoader.classList.add('hidden');
        successActions.classList.add('hidden');
        
        reelUrlInput.disabled = false;
        currentReelInfo = null;
    }

    // --- Paste Clipboard Link ---
    pasteBtn.addEventListener('click', async () => {
        try {
            const text = await navigator.clipboard.readText();
            const url = text.trim();
            if (url.includes('instagram.com')) {
                reelUrlInput.value = url;
                showToast('URL pasted from clipboard!', 'success');
                fetchReelMetadata(url);
            } else {
                showToast('Clipboard does not contain an Instagram link', 'error');
            }
        } catch (err) {
            showToast('Unable to access clipboard. Please paste manually.', 'error');
        }
    });

    // --- Auto-Fetch / Analyze Link Function ---
    async function fetchReelMetadata(url) {
        if (!url) return;
        
        resetUIState();
        
        // Disable input while loading
        reelUrlInput.disabled = true;
        
        // Show Fetching Loader
        fetchingLoader.classList.remove('hidden');
        
        try {
            const response = await fetch('/api/info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: url,
                    cookies: 'none'
                })
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch Reel metadata');
            }

            // Display Metadata
            currentReelInfo = data;
            
            // Proxy thumbnail to bypass Instagram's CORS policies
            previewThumb.src = `/api/proxy-image?url=${encodeURIComponent(data.thumbnail)}`;
            previewDuration.textContent = data.duration;
            previewCreator.textContent = `@${data.uploader}`;
            previewTitle.textContent = data.title || 'Instagram Reel (No Description)';
            
            // Show preview, scroll to it
            previewArea.classList.remove('hidden');
            previewArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            showToast('Reel info loaded successfully!', 'success');

        } catch (err) {
            showToast(err.message, 'error');
            resetUIState();
        } finally {
            fetchingLoader.classList.add('hidden');
            reelUrlInput.disabled = false;
        }
    }

    // --- Auto-Fetch Input Events ---
    function isValidInstagramUrl(url) {
        return url.includes('instagram.com/reel/') || 
               url.includes('instagram.com/p/') || 
               url.includes('instagram.com/tv/') ||
               url.includes('instagram.com/share/');
    }

    let fetchTimeout = null;
    reelUrlInput.addEventListener('input', () => {
        const url = reelUrlInput.value.trim();
        if (isValidInstagramUrl(url)) {
            clearTimeout(fetchTimeout);
            fetchTimeout = setTimeout(() => {
                fetchReelMetadata(url);
            }, 500);
        }
    });

    cancelPreviewBtn.addEventListener('click', resetUIState);

    // --- Start Download ---
    downloadBtn.addEventListener('click', async () => {
        if (!currentReelInfo || !currentReelInfo.video_url) {
            showToast('Invalid video URL. Please try again.', 'error');
            return;
        }

        // Hide preview and show success panel
        previewArea.classList.add('hidden');
        successActions.classList.remove('hidden');
        reelUrlInput.disabled = true;

        try {
            // Trigger direct stream download in browser
            const downloadUrl = `/api/download-stream?url=${encodeURIComponent(currentReelInfo.video_url)}&filename=${encodeURIComponent(currentReelInfo.title || 'instagram_reel')}`;
            
            // Bind fallback download link
            downloadAgainBtn.href = downloadUrl;
            downloadAgainBtn.download = (currentReelInfo.title || 'instagram_reel') + '.mp4';
            
            // Programmatically start download
            const tempLink = document.createElement('a');
            tempLink.href = downloadUrl;
            tempLink.download = (currentReelInfo.title || 'instagram_reel') + '.mp4';
            document.body.appendChild(tempLink);
            tempLink.click();
            document.body.removeChild(tempLink);

            showToast('Download started in browser!', 'success');

            // Log download to history
            await fetch('/api/history/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: currentReelInfo.title,
                    thumbnail: currentReelInfo.thumbnail,
                    duration: currentReelInfo.duration,
                    uploader: currentReelInfo.uploader,
                    url: currentReelInfo.url
                })
            });

            // Reset input after small timeout
            setTimeout(() => {
                reelUrlInput.value = '';
                reelUrlInput.disabled = false;
                loadHistory();
            }, 1000);

        } catch (err) {
            showToast('Failed to trigger download: ' + err.message, 'error');
            resetUIState();
        }
    });

    // --- Load History List ---
    async function loadHistory() {
        try {
            const response = await fetch('/api/history');
            const history = await response.json();
            
            historyCount.textContent = history.length;
            
            if (history.length === 0) {
                historyList.innerHTML = '';
                historyList.appendChild(historyEmpty);
                return;
            }

            // Clear empty layout
            historyList.innerHTML = '';
            
            history.forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'history-item';
                
                const thumbUrl = `/api/proxy-image?url=${encodeURIComponent(item.thumbnail)}`;
                
                itemDiv.innerHTML = `
                    <div class="history-thumb">
                        <img src="${thumbUrl}" alt="Thumbnail">
                        <span class="duration-tag">${item.duration}</span>
                    </div>
                    <div class="history-info">
                        <div class="history-title-row">
                            <h4 class="history-title" title="${item.title}">${item.title}</h4>
                            <span class="history-meta">By @${item.uploader} • ${item.date}</span>
                        </div>
                        <div class="history-actions">
                            <button type="button" class="btn secondary-btn load-btn" data-url="${item.url}">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                                </svg>
                                <span>Load Reel</span>
                            </button>
                        </div>
                    </div>
                `;
                
                // Event listener on "Load Reel"
                itemDiv.querySelector('.load-btn').addEventListener('click', (e) => {
                    const url = e.currentTarget.getAttribute('data-url');
                    reelUrlInput.value = url;
                    fetchReelMetadata(url);
                });
                
                historyList.appendChild(itemDiv);
            });
            
        } catch (err) {
            console.error('Failed to load history list:', err);
        }
    }

    // --- Accordion component (Privacy Policy) ---
    const accordionHeaders = document.querySelectorAll('.accordion-header');
    accordionHeaders.forEach(header => {
        header.addEventListener('click', () => {
            const item = header.parentElement;
            const content = item.querySelector('.accordion-content');
            
            // Toggle active state
            item.classList.toggle('active');
            
            if (item.classList.contains('active')) {
                content.style.maxHeight = content.scrollHeight + 'px';
            } else {
                content.style.maxHeight = '0';
            }
        });
    });

    // --- Tab Navigation Switcher ---
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            
            // Toggle active state on buttons
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Toggle visibility of panels
            tabPanels.forEach(panel => {
                if (panel.id === targetTab) {
                    panel.classList.remove('hidden');
                } else {
                    panel.classList.add('hidden');
                }
            });
        });
    });

    // --- Initialize ---
    loadHistory();
});
