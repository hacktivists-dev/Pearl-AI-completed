// Initialize Lucide icons
lucide.createIcons();

let chatHistory = [];
let currentChatId = Date.now().toString();
const chatContainer = document.querySelector('#chat-container > div');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const recentChatsList = document.getElementById('recent-chats-list');
const newChatBtn = document.getElementById('new-chat-btn');
const clearChatBtn = document.getElementById('clear-chat-btn');
const profileBtn = document.getElementById('profile-btn');
const userNameInput = document.getElementById('user-name-input');
const userAvatar = document.getElementById('user-avatar');
const micBtn = document.getElementById('mic-btn');
const attachFilesBtn = document.getElementById('attach-files-btn');
const attachFolderBtn = document.getElementById('attach-folder-btn');
const attachMediaBtn = document.getElementById('attach-media-btn');
const fileInput = document.getElementById('file-input');
const mediaInput = document.getElementById('media-input');
const folderInput = document.getElementById('folder-input');
const attachmentTray = document.getElementById('attachment-tray');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const chatScrollContainer = document.getElementById('chat-container');
const agentModeBtn = document.getElementById('agent-mode-btn');
const agentModeLabel = document.getElementById('agent-mode-label');
const agentPanel = document.getElementById('agent-panel');
const connectWorkspaceBtn = document.getElementById('connect-workspace-btn');
const agentWorkspaceStatus = document.getElementById('agent-workspace-status');
const agentCapabilityNote = document.getElementById('agent-capability-note');
const agentWorkspaceControls = document.getElementById('agent-workspace-controls');
const agentDeviceControls = document.getElementById('agent-device-controls');
const agentDeviceSelect = document.getElementById('agent-device-select');
const downloadAgentBtn = document.getElementById('download-agent-btn');
const pairDeviceBtn = document.getElementById('pair-device-btn');
const refreshDevicesBtn = document.getElementById('refresh-devices-btn');
const agentChangesDialog = document.getElementById('agent-changes-dialog');
const agentChangesList = document.getElementById('agent-changes-list');
const approveAgentChangesBtn = document.getElementById('approve-agent-changes-btn');
const cancelAgentChangesBtn = document.getElementById('cancel-agent-changes-btn');
const agentDownloadDialog = document.getElementById('agent-download-dialog');
const agentDownloadPlatformNote = document.getElementById('agent-download-platform-note');
const agentLimitedAccessBtn = document.getElementById('agent-limited-access-btn');
const agentDownloadConfirmBtn = document.getElementById('agent-download-confirm-btn');
const desktopAgentControls = document.getElementById('desktop-agent-controls');
const desktopAgentStatus = document.getElementById('desktop-agent-status');
const desktopAgentStopBtn = document.getElementById('desktop-agent-stop-btn');
const desktopAgentResumeBtn = document.getElementById('desktop-agent-resume-btn');
const brandTitle = document.getElementById('brand-title');

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_CONTEXT_CHARS = 48000;
const MAX_HISTORY_REQUEST_CHARS = 18000;
const MAX_STORED_MESSAGE_CHARS = 12000;
const MAX_STORED_SESSIONS = 25;
const MAX_STORED_MESSAGES_PER_SESSION = 50;
const MAX_FOLDER_PATHS_IN_SUMMARY = 120;
const TEXT_FILE_EXTENSIONS = new Set([
    'txt', 'md', 'csv', 'tsv', 'json', 'jsonl', 'xml', 'yaml', 'yml',
    'html', 'htm', 'css', 'js', 'jsx', 'ts', 'tsx', 'py', 'java', 'c',
    'cpp', 'h', 'hpp', 'cs', 'go', 'rs', 'php', 'rb', 'swift', 'kt',
    'kts', 'sql', 'sh', 'bash', 'ps1', 'bat', 'ini', 'cfg', 'conf',
    'toml', 'env', 'log', 'rtf'
]);
let selectedAttachments = [];
const isAgentMode = window.location.pathname === '/agent';
const CHAT_STORAGE_KEY = isAgentMode ? 'pearl_agent_chats' : 'pearl_chats';
let agentPermission = localStorage.getItem('pearl_agent_permission') === 'full' ? 'full' : 'default';
let agentTarget = localStorage.getItem('pearl_agent_target') === 'device' ? 'device' : 'workspace';
let agentWorkspaceHandle = null;
let pairedDevices = [];
const DESKTOP_AGENT_APP_KEY = 'pearl_desktop_agent_app';
let isDesktopAgentApp = localStorage.getItem(DESKTOP_AGENT_APP_KEY) === 'true';
const isAndroidAgentApp = /PearlAI-Agent-Android/i.test(navigator.userAgent || '');
let desktopAgentStatusTimer = null;
let pendingAgentOperations = [];
let pendingAgentResolve = null;
let androidAgentActivationPromise = null;

let recognition; // Declare recognition globally
let activeRequestController = null;
let activeTypingTimer = null;
let activeTypingResolve = null;
let generationSequence = 0;
let activeGenerationId = 0;
const cancelledGenerations = new Set();
let pendingChatScrollFrame = 0;

function scrollChatToBottom(behavior = 'auto') {
    if (pendingChatScrollFrame) cancelAnimationFrame(pendingChatScrollFrame);
    pendingChatScrollFrame = requestAnimationFrame(() => {
        pendingChatScrollFrame = 0;
        chatScrollContainer.scrollTo({
            top: chatScrollContainer.scrollHeight,
            behavior
        });
    });
}

function scrollChatToBottomAfterRender(root = chatContainer, behavior = 'auto') {
    scrollChatToBottom(behavior);
    requestAnimationFrame(() => scrollChatToBottom(behavior));

    root.querySelectorAll('img').forEach((image) => {
        if (!image.complete) {
            image.addEventListener('load', () => scrollChatToBottom(), { once: true });
            image.addEventListener('error', () => scrollChatToBottom(), { once: true });
        }
    });
}

function setGeneratingState(isGenerating) {
    sendBtn.dataset.generating = isGenerating ? 'true' : 'false';
    sendBtn.title = isGenerating ? 'Stop generating' : 'Send message';
    sendBtn.setAttribute('aria-label', sendBtn.title);
    sendBtn.classList.toggle('bg-red-600', isGenerating);
    sendBtn.classList.toggle('hover:bg-red-700', isGenerating);
    sendBtn.classList.toggle('bg-slate-900', !isGenerating);
    sendBtn.classList.toggle('hover:bg-slate-800', !isGenerating);
    sendBtn.innerHTML = isGenerating
        ? '<i data-lucide="square" class="h-4 w-4 fill-current"></i>'
        : '<i data-lucide="arrow-up" class="h-5 w-5"></i>';
    lucide.createIcons();
}

function stopGeneration() {
    if (activeGenerationId) cancelledGenerations.add(activeGenerationId);
    if (activeRequestController) {
        activeRequestController.abort();
        activeRequestController = null;
    }
    if (activeTypingTimer) {
        clearTimeout(activeTypingTimer);
        activeTypingTimer = null;
    }
    if (activeTypingResolve) {
        activeTypingResolve(false);
        activeTypingResolve = null;
    }
    document.getElementById('typing-indicator')?.remove();
    if (pendingAgentResolve) closeAgentApproval(false);
    activeGenerationId = 0;
    setGeneratingState(false);
}

function syncViewportHeight() {
    const viewportHeight = window.visualViewport?.height || window.innerHeight;
    document.documentElement.style.setProperty('--app-height', `${Math.round(viewportHeight)}px`);

    if (document.activeElement === userInput) {
        scrollChatToBottom();
    }
}

function isMobileLayout() {
    return window.matchMedia('(max-width: 767px)').matches;
}

function openMobileSidebar() {
    if (!isMobileLayout()) return;
    sidebar.classList.remove('-translate-x-full');
    sidebarOverlay.classList.remove('hidden');
    document.body.classList.add('sidebar-open');
    mobileMenuBtn.setAttribute('aria-expanded', 'true');
}

function closeMobileSidebar() {
    if (!isMobileLayout()) return;
    sidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
    document.body.classList.remove('sidebar-open');
    mobileMenuBtn.setAttribute('aria-expanded', 'false');
}

function syncResponsiveLayout() {
    syncViewportHeight();
    if (!isMobileLayout()) {
        sidebar.classList.remove('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
        document.body.classList.remove('sidebar-open');
        mobileMenuBtn.setAttribute('aria-expanded', 'false');
    } else if (!document.body.classList.contains('sidebar-open')) {
        sidebar.classList.add('-translate-x-full');
    }
}

function resizeComposerInput() {
    userInput.style.height = 'auto';
    const maximumHeight = Number.parseFloat(getComputedStyle(userInput).maxHeight) || 224;
    userInput.style.height = `${Math.min(userInput.scrollHeight, maximumHeight)}px`;
    userInput.style.overflowY = userInput.scrollHeight > maximumHeight ? 'auto' : 'hidden';
}

mobileMenuBtn.setAttribute('aria-label', 'Open navigation menu');
mobileMenuBtn.setAttribute('aria-expanded', 'false');
mobileMenuBtn.addEventListener('click', () => {
    if (sidebar.classList.contains('-translate-x-full')) {
        openMobileSidebar();
    } else {
        closeMobileSidebar();
    }
});
sidebarOverlay.addEventListener('click', closeMobileSidebar);

window.addEventListener('resize', syncResponsiveLayout);
window.addEventListener('orientationchange', syncResponsiveLayout);
window.visualViewport?.addEventListener('resize', syncViewportHeight);
window.visualViewport?.addEventListener('scroll', syncViewportHeight);

function safeAgentPath(path) {
    const rawPath = String(path || '').replaceAll('\\', '/').trim();
    if (rawPath.startsWith('/') || /^[a-zA-Z]:/.test(rawPath)) {
        throw new Error(`Unsafe workspace path: ${path}`);
    }
    const normalized = rawPath.replace(/^\/+|\/+$/g, '');
    const parts = normalized.split('/').filter(Boolean);
    if (!parts.length || parts.some((part) => part === '.' || part === '..') || parts[0].includes(':')) {
        throw new Error(`Unsafe workspace path: ${path}`);
    }
    return parts;
}

async function getAgentParentDirectory(pathParts, create = true) {
    let directory = agentWorkspaceHandle;
    for (const part of pathParts.slice(0, -1)) {
        directory = await directory.getDirectoryHandle(part, { create });
    }
    return directory;
}

async function applyAgentOperation(operation) {
    const pathParts = safeAgentPath(operation.path);
    const name = pathParts[pathParts.length - 1];

    if (operation.type === 'create_folder') {
        let directory = agentWorkspaceHandle;
        for (const part of pathParts) {
            directory = await directory.getDirectoryHandle(part, { create: true });
        }
        return;
    }

    const parent = await getAgentParentDirectory(pathParts, operation.type === 'write_file');
    if (operation.type === 'write_file') {
        const fileHandle = await parent.getFileHandle(name, { create: true });
        const writable = await fileHandle.createWritable();
        await writable.write(String(operation.content || ''));
        await writable.close();
        return;
    }

    if (operation.type === 'delete_file') {
        await parent.removeEntry(name);
        return;
    }

    if (operation.type === 'delete_folder') {
        await parent.removeEntry(name, { recursive: true });
    }
}

async function downloadAgentOperations(operations) {
    const payload = {
        generatedAt: new Date().toISOString(),
        note: 'Connect a folder in Pearl Agent to apply these changes automatically.',
        operations: operations.map((operation) => ({
            type: operation.type,
            path: operation.path,
            content: operation.type === 'write_file' ? String(operation.content || '') : undefined
        }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `pearl-agent-changes-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

async function applyAgentOperations(operations) {
    if (!operations.length) return 'No file changes were requested.';

    if (!agentWorkspaceHandle) {
        await downloadAgentOperations(operations);
        return 'Direct folder access is unavailable or no folder is connected, so a JSON change file was downloaded instead.';
    }

    const permission = typeof agentWorkspaceHandle.queryPermission === 'function'
        ? await agentWorkspaceHandle.queryPermission({ mode: 'readwrite' })
        : 'granted';
    const granted = permission === 'granted'
        || (
            typeof agentWorkspaceHandle.requestPermission === 'function'
            && await agentWorkspaceHandle.requestPermission({ mode: 'readwrite' }) === 'granted'
        );
    if (!granted) throw new Error('Write permission for the connected folder was not granted.');

    for (const operation of operations) {
        await applyAgentOperation(operation);
    }
    return `${operations.length} workspace change(s) applied successfully.`;
}

function operationLabel(operation) {
    const labels = {
        create_folder: 'Create folder',
        write_file: 'Create or update file',
        delete_file: 'Delete file',
        delete_folder: 'Delete folder'
    };
    return labels[operation.type] || operation.type;
}

function requestAgentApproval(operations) {
    pendingAgentOperations = operations;
    agentChangesList.innerHTML = '';
    operations.forEach((operation) => {
        const item = document.createElement('div');
        item.className = 'rounded-xl border border-slate-200 bg-slate-50 px-4 py-3';
        const title = document.createElement('div');
        title.className = 'text-sm font-semibold text-slate-800';
        title.textContent = operationLabel(operation);
        const path = document.createElement('div');
        path.className = 'mt-1 break-all font-mono text-xs text-slate-500';
        path.textContent = operation.path;
        item.append(title, path);
        agentChangesList.appendChild(item);
    });
    agentChangesDialog.classList.remove('hidden');
    agentChangesDialog.classList.add('flex');

    return new Promise((resolve) => {
        pendingAgentResolve = resolve;
    });
}

function closeAgentApproval(approved) {
    agentChangesDialog.classList.add('hidden');
    agentChangesDialog.classList.remove('flex');
    const resolve = pendingAgentResolve;
    pendingAgentResolve = null;
    if (resolve) resolve(approved ? pendingAgentOperations : []);
    pendingAgentOperations = [];
}

approveAgentChangesBtn.addEventListener('click', () => closeAgentApproval(true));
cancelAgentChangesBtn.addEventListener('click', () => closeAgentApproval(false));
agentChangesDialog.addEventListener('click', (event) => {
    if (event.target === agentChangesDialog) closeAgentApproval(false);
});

async function buildAgentWorkspaceSnapshot() {
    if (!agentWorkspaceHandle) {
        return 'No client folder is connected. Generate new files when appropriate; they will be delivered as a downloadable ZIP.';
    }

    const lines = [`Workspace: ${agentWorkspaceHandle.name}`];
    let contentBudget = 36000;
    let pathCount = 0;

    async function walk(directoryHandle, prefix = '') {
        for await (const [name, handle] of directoryHandle.entries()) {
            if (pathCount >= 1500 || contentBudget <= 0) return;
            const path = prefix ? `${prefix}/${name}` : name;
            const lowerName = name.toLowerCase();
            if (handle.kind === 'directory') {
                lines.push(`[folder] ${path}`);
                pathCount += 1;
                if (!['node_modules', '.git', '.venv', 'venv', '__pycache__', 'dist', 'build', '.next'].includes(lowerName)) {
                    await walk(handle, path);
                }
                continue;
            }

            lines.push(`[file] ${path}`);
            pathCount += 1;
            const extension = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
            if (!TEXT_FILE_EXTENSIONS.has(extension) || contentBudget < 300) continue;

            try {
                const file = await handle.getFile();
                if (file.size > 500000) continue;
                const content = (await file.text()).slice(0, Math.min(8000, contentBudget));
                lines.push(`--- ${path} ---\n${content}\n--- end ${path} ---`);
                contentBudget -= content.length;
            } catch (error) {
                lines.push(`[unreadable] ${path}: ${error.message}`);
            }
        }
    }

    await walk(agentWorkspaceHandle);
    if (pathCount >= 1500 || contentBudget <= 0) {
        lines.push('[snapshot truncated to fit the AI context]');
    }
    return lines.join('\n').slice(0, 50000);
}

async function connectAgentWorkspace() {
    if (!window.showDirectoryPicker) {
        agentWorkspaceStatus.textContent = 'Download mode';
        agentCapabilityNote.textContent =
            'This browser cannot write directly to folders. Agent changes will be provided as a downloadable ZIP.';
        return;
    }

    try {
        agentWorkspaceHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
        agentWorkspaceStatus.textContent = agentWorkspaceHandle.name;
        agentWorkspaceStatus.title = agentWorkspaceHandle.name;
        connectWorkspaceBtn.innerHTML =
            '<i data-lucide="folder-check" class="h-4 w-4"></i>Change Folder';
        lucide.createIcons();
    } catch (error) {
        if (error.name !== 'AbortError') {
            alert(`Could not connect the folder: ${error.message}`);
        }
    }
}

connectWorkspaceBtn.addEventListener('click', connectAgentWorkspace);

document.querySelectorAll('input[name="agent-permission"]').forEach((input) => {
    input.checked = input.value === agentPermission;
    input.addEventListener('change', () => {
        if (!input.checked) return;
        agentPermission = input.value;
        localStorage.setItem('pearl_agent_permission', agentPermission);
        if (isAndroidAgentApp && window.PearlAndroidAgent?.setFullAccess) {
            window.PearlAndroidAgent.setFullAccess(agentPermission === 'full');
        }
        if (agentPermission === 'full') {
            alert(
                isAndroidAgentApp
                    ? 'Full Access can automatically run ordinary Android Agent actions. Deletes, typing, navigation, and clipboard changes still require approval on the device.'
                    : 'Full Access automatically applies changes only inside the folder you explicitly connect. It cannot control the rest of your device.'
            );
        }
    });
});

function selectedDevice() {
    return pairedDevices.find((device) => device.id === agentDeviceSelect.value) || null;
}

function renderPairedDevices() {
    const previousValue = agentDeviceSelect.value;
    agentDeviceSelect.innerHTML = '';
    if (!pairedDevices.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No paired device';
        agentDeviceSelect.appendChild(option);
        return;
    }

    pairedDevices.forEach((device) => {
        const option = document.createElement('option');
        option.value = device.id;
        option.textContent = `${device.online ? 'Online' : 'Offline'} — ${device.name}`;
        agentDeviceSelect.appendChild(option);
    });
    if (pairedDevices.some((device) => device.id === previousValue)) {
        agentDeviceSelect.value = previousValue;
    }
}

async function loadPairedDevices() {
    try {
        const response = await fetch('/api/devices');
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Could not load paired devices.');
        pairedDevices = data.devices || [];
        renderPairedDevices();
    } catch (error) {
        pairedDevices = [];
        renderPairedDevices();
        console.error(error);
    }
}

async function pairDeviceWithCode(rawCode, quiet = false) {
    const pairingCode = String(rawCode || '').replace(/\D/g, '');
    if (pairingCode.length !== 8) {
        if (!quiet) alert('Enter the 8-digit pairing code shown by Pearl AI Agent.');
        return false;
    }

    const response = await fetch('/api/device/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pairing_code: pairingCode })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (!quiet) alert(data.detail || 'Could not pair this device.');
        return false;
    }

    window.PearlAndroidAgent?.markPaired?.();
    agentTarget = 'device';
    localStorage.setItem('pearl_agent_target', agentTarget);
    document.querySelectorAll('input[name="agent-target"]').forEach((input) => {
        input.checked = input.value === 'device';
    });
    syncAgentTargetControls();
    await loadPairedDevices();
    if (data.device?.id) agentDeviceSelect.value = data.device.id;
    return true;
}

pairDeviceBtn.addEventListener('click', async () => {
    const pairingCode = prompt('Enter the 8-digit code shown in Pearl AI Agent:');
    if (pairingCode) await pairDeviceWithCode(pairingCode);
});

function devicePlatform() {
    const userAgent = navigator.userAgent || '';
    if (/windows/i.test(userAgent)) return 'windows';
    if (/android/i.test(userAgent)) return 'android';
    if (/iphone|ipad|ipod/i.test(userAgent)) return 'ios';
    if (/macintosh|mac os x/i.test(userAgent)) return 'macos';
    if (/linux/i.test(userAgent)) return 'linux';
    return 'unknown';
}

function openAgentDownloadDialog() {
    const platform = devicePlatform();
    const supportsAgentDownload = platform === 'windows' || platform === 'android';
    agentDownloadPlatformNote.textContent = platform === 'windows'
        ? 'Windows detected. The standalone Pearl AI Agent will download as an EXE.'
        : (
            platform === 'android'
                ? 'Android detected. Pearl AI Device Agent v2.1 supports Android 5 and newer. If an older Pearl APK is installed, you can remove it after installing this compatibility release.'
                : platform === 'ios'
                    ? 'iPhone/iPad detected. iOS does not permit unrestricted full-device agents.'
                    : 'Pearl AI Agent downloads are currently available for Windows and Android.'
        );
    agentDownloadConfirmBtn.textContent = supportsAgentDownload
        ? 'Download Pearl AI Agent'
        : 'Continue with Limited Access';
    agentDownloadConfirmBtn.dataset.platform = platform;
    agentDownloadDialog.classList.remove('hidden');
    agentDownloadDialog.classList.add('flex');
    lucide.createIcons();
}

function closeAgentDownloadDialog() {
    agentDownloadDialog.classList.add('hidden');
    agentDownloadDialog.classList.remove('flex');
}

function continueLimitedAgent() {
    localStorage.setItem('pearl_agent_target', 'workspace');
    closeAgentDownloadDialog();
    if (!isAgentMode) window.location.href = '/agent';
}

function downloadAgentForPlatform() {
    const platform = agentDownloadConfirmBtn.dataset.platform;
    if (!['windows', 'android'].includes(platform)) {
        continueLimitedAgent();
        return;
    }
    localStorage.setItem('pearl_agent_target', 'device');
    closeAgentDownloadDialog();

    const downloadUrl = `/api/device/download?platform_name=${encodeURIComponent(platform)}`;
    if (platform === 'android') {
        window.location.assign(downloadUrl);
    } else {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = '';
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    if (platform === 'windows' && !isAgentMode) {
        setTimeout(() => {
            window.location.href = '/agent';
        }, 1500);
    }
}

function syncAgentTargetControls() {
    const useDevice = agentTarget === 'device';
    agentWorkspaceControls.classList.toggle('hidden', useDevice);
    agentWorkspaceControls.classList.toggle('flex', !useDevice);
    agentDeviceControls.classList.toggle('hidden', !useDevice);
    agentDeviceControls.classList.toggle('flex', useDevice);
    agentCapabilityNote.textContent = useDevice
        ? 'Install and open the downloaded Pearl AI Agent. It connects automatically to this signed-in account.'
        : 'Connect a folder to let Pearl Agent create and update files inside it.';
    if (useDevice) loadPairedDevices();
}

document.querySelectorAll('input[name="agent-target"]').forEach((input) => {
    input.checked = input.value === agentTarget;
    input.addEventListener('change', () => {
        if (!input.checked) return;
        agentTarget = input.value;
        localStorage.setItem('pearl_agent_target', agentTarget);
        syncAgentTargetControls();
    });
});
downloadAgentBtn.addEventListener('click', openAgentDownloadDialog);
refreshDevicesBtn.addEventListener('click', loadPairedDevices);
agentLimitedAccessBtn.addEventListener('click', continueLimitedAgent);
agentDownloadConfirmBtn.addEventListener('click', downloadAgentForPlatform);
agentDownloadDialog.addEventListener('click', (event) => {
    if (event.target === agentDownloadDialog) closeAgentDownloadDialog();
});

async function refreshLocalAgentStatus() {
    if (isAndroidAgentApp && window.PearlAndroidAgent?.getStatus) {
        try {
            const status = JSON.parse(window.PearlAndroidAgent.getStatus());
            const accessibility = status.accessibility
                ? 'Device control enabled'
                : 'Enable Accessibility for typing and screenshots';
            desktopAgentStatus.textContent = `${status.status || 'Android Agent'} — ${accessibility}`;
            desktopAgentStopBtn.classList.toggle('hidden', Boolean(status.stopped));
            desktopAgentResumeBtn.classList.toggle('hidden', !status.stopped);
        } catch (error) {
            desktopAgentStatus.textContent = 'Android Agent status unavailable';
        }
        return;
    }
    if (!window.pywebview?.api?.status) return;
    try {
        const status = await window.pywebview.api.status();
        desktopAgentStatus.textContent = `${status.status}${status.account_email ? ` — ${status.account_email}` : ''}`;
        const stopped = /stop|error|disconnect/i.test(status.status || '');
        desktopAgentStopBtn.classList.toggle('hidden', stopped);
        desktopAgentResumeBtn.classList.toggle('hidden', !stopped);
    } catch (error) {
        desktopAgentStatus.textContent = 'Local Agent status unavailable';
    }
}

async function activateDesktopAgentApp() {
    isDesktopAgentApp = true;
    localStorage.setItem(DESKTOP_AGENT_APP_KEY, 'true');
    agentTarget = 'device';
    localStorage.setItem('pearl_agent_target', 'device');
    document.querySelectorAll('input[name="agent-target"]').forEach((input) => {
        input.checked = input.value === 'device';
    });
    desktopAgentControls.classList.remove('hidden');
    desktopAgentControls.classList.add('flex');
    downloadAgentBtn.classList.add('hidden');
    syncAgentTargetControls();
    await loadPairedDevices();
    await refreshLocalAgentStatus();
    if (!desktopAgentStatusTimer) {
        desktopAgentStatusTimer = setInterval(refreshLocalAgentStatus, 3000);
    }
}

async function activateAndroidAgentApp() {
    if (!isAndroidAgentApp) return;
    if (androidAgentActivationPromise) return androidAgentActivationPromise;

    androidAgentActivationPromise = (async () => {
        agentTarget = 'device';
        localStorage.setItem('pearl_agent_target', 'device');
        document.querySelectorAll('input[name="agent-target"]').forEach((input) => {
            input.checked = input.value === 'device';
        });
        downloadAgentBtn.classList.add('hidden');
        pairDeviceBtn.classList.add('hidden');
        desktopAgentControls.classList.remove('hidden');
        desktopAgentControls.classList.add('flex');
        syncAgentTargetControls();

        const pairingCode = window.PearlAndroidAgent?.getPairingCode?.() || '';
        if (pairingCode) await pairDeviceWithCode(pairingCode, true);
        window.PearlAndroidAgent?.setFullAccess?.(agentPermission === 'full');
        window.PearlAndroidAgent?.startAgent?.();
        await loadPairedDevices();
        const deviceId = window.PearlAndroidAgent?.getDeviceId?.() || '';
        if (deviceId && pairedDevices.some((device) => device.id === deviceId)) {
            agentDeviceSelect.value = deviceId;
        }
        await refreshLocalAgentStatus();
        if (!desktopAgentStatusTimer) {
            desktopAgentStatusTimer = setInterval(refreshLocalAgentStatus, 3000);
        }
    })().finally(() => {
        androidAgentActivationPromise = null;
    });
    return androidAgentActivationPromise;
}

window.addEventListener('pywebviewready', activateDesktopAgentApp);
window.addEventListener('pearlandroidready', activateAndroidAgentApp);

if (isDesktopAgentApp) {
    activateDesktopAgentApp();
}

if (!isDesktopAgentApp && window.pywebview?.api) {
    activateDesktopAgentApp();
}

desktopAgentStopBtn.addEventListener('click', async () => {
    if (isAndroidAgentApp && window.PearlAndroidAgent?.emergencyStop) {
        window.PearlAndroidAgent.emergencyStop();
    } else if (window.pywebview?.api?.emergency_stop) {
        await window.pywebview.api.emergency_stop();
    }
    await refreshLocalAgentStatus();
});

desktopAgentResumeBtn.addEventListener('click', async () => {
    if (isAndroidAgentApp && window.PearlAndroidAgent?.startAgent) {
        window.PearlAndroidAgent.startAgent();
    } else if (window.pywebview?.api?.resume) {
        await window.pywebview.api.resume();
    }
    await refreshLocalAgentStatus();
    await loadPairedDevices();
});

async function queueDeviceOperations(operations) {
    const device = selectedDevice();
    if (!device) throw new Error('Pair and select an online device first.');

    const response = await fetch('/api/device/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            device_id: device.id,
            permission: agentPermission,
            operations
        })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Could not queue the device job.');
    return data.job_id;
}

async function waitForDeviceJob(jobId, generationId) {
    const deadline = Date.now() + 10 * 60 * 1000;
    while (Date.now() < deadline) {
        if (cancelledGenerations.has(generationId)) return { status: 'cancelled', results: [] };
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const response = await fetch(`/api/device/jobs/${encodeURIComponent(jobId)}`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'Could not read the device job result.');
        if (['completed', 'failed', 'cancelled'].includes(data.status)) return data;
    }
    throw new Error('The device job did not finish within ten minutes.');
}

function formatDeviceJobResult(job) {
    const lines = [`Device job status: ${job.status}`];
    (job.results || []).forEach((result) => {
        lines.push(`- ${result.status}: ${result.operation}`);
        if (result.output) lines.push(String(result.output).slice(0, 4000));
        if (result.error) lines.push(`Error: ${result.error}`);
    });
    if (job.error) lines.push(`Error: ${job.error}`);
    return lines.join('\n');
}

function initializeAgentMode() {
    agentModeBtn.addEventListener('click', () => {
        if (isAgentMode) {
            window.location.href = '/';
        } else if (isDesktopAgentApp || isAndroidAgentApp || window.pywebview?.api) {
            window.location.href = '/agent';
        } else {
            openAgentDownloadDialog();
        }
    });

    if (!isAgentMode) return;
    document.body.classList.add('agent-mode');
    agentPanel.classList.remove('hidden');
    brandTitle.textContent = 'Pearl Agent';
    document.getElementById('system-status-label').textContent = 'Agent Ready';
    document.title = 'Pearl Agent | Workspace Automation';
    agentModeLabel.textContent = 'Back to Chat';
    userInput.placeholder = 'Describe a task for Pearl Agent...';

    if (isAndroidAgentApp) {
        activateAndroidAgentApp();
    }

    syncAgentTargetControls();
    const welcomeMessage = chatContainer.querySelector('.prose');
    if (welcomeMessage) {
        welcomeMessage.textContent =
            'Pearl Agent can inspect a connected workspace, plan changes, and create or update files within the access level you choose.';
    }

    if (!window.showDirectoryPicker) {
        agentWorkspaceStatus.textContent = 'Download mode';
        connectWorkspaceBtn.innerHTML =
            '<i data-lucide="package-down" class="h-4 w-4"></i>Download Mode';
        agentCapabilityNote.textContent =
            'Direct folder writing is unavailable on this browser. Generated files will download as a ZIP.';
        lucide.createIcons();
    }
}

if (window.pdfjsLib) {
    window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function attachmentKey(file) {
    return `${file.webkitRelativePath || file.name}:${file.size}:${file.lastModified}`;
}

function attachmentName(file) {
    return file.webkitRelativePath || file.name;
}

function folderName(file) {
    const relativePath = file.webkitRelativePath || '';
    return relativePath ? relativePath.split('/')[0] : '';
}

function attachmentGroupKey(file) {
    const folder = folderName(file);
    return folder ? `folder:${folder}` : `file:${attachmentKey(file)}`;
}

function getAttachmentGroups(files) {
    const groups = new Map();

    files.forEach((file) => {
        const folder = folderName(file);
        const key = attachmentGroupKey(file);
        if (!groups.has(key)) {
            groups.set(key, {
                key,
                type: folder ? 'folder' : 'file',
                name: folder || file.name,
                files: [],
                totalSize: 0
            });
        }
        const group = groups.get(key);
        group.files.push(file);
        group.totalSize += file.size;
    });

    return [...groups.values()];
}

function fileExtension(file) {
    return file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : '';
}

function attachmentIcon(file) {
    if (file.type.startsWith('image/')) return 'image';
    if (file.type.startsWith('video/')) return 'video';
    if (file.webkitRelativePath) return 'folder';
    return 'file-text';
}

function renderAttachmentTray() {
    attachmentTray.innerHTML = '';
    attachmentTray.classList.toggle('hidden', selectedAttachments.length === 0);

    getAttachmentGroups(selectedAttachments).forEach((group) => {
        const safeName = escapeHtml(group.name);
        const safeKey = escapeHtml(group.key);
        const isFolder = group.type === 'folder';
        const chip = document.createElement('div');
        chip.className = 'flex max-w-full items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600';
        chip.innerHTML = `
            <i data-lucide="${isFolder ? 'folder' : attachmentIcon(group.files[0])}" class="h-4 w-4 shrink-0 text-indigo-500"></i>
            <span class="max-w-[220px] truncate" title="${safeName}">${safeName}</span>
            <span class="shrink-0 text-slate-400">${isFolder ? 'Folder' : formatFileSize(group.totalSize)}</span>
            <button type="button" class="remove-attachment rounded-md p-0.5 hover:bg-slate-200" data-key="${safeKey}" title="Remove attachment">
                <i data-lucide="x" class="h-3.5 w-3.5"></i>
            </button>
        `;
        attachmentTray.appendChild(chip);
    });
    lucide.createIcons();
}

function addAttachments(files) {
    const existingKeys = new Set(selectedAttachments.map(attachmentKey));
    const rejected = [];

    for (const file of files) {
        if (file.size > MAX_FILE_BYTES) {
            rejected.push(`${attachmentName(file)} is larger than 50 MB.`);
            continue;
        }
        const key = attachmentKey(file);
        if (!existingKeys.has(key)) {
            selectedAttachments.push(file);
            existingKeys.add(key);
        }
    }

    renderAttachmentTray();
    if (rejected.length) alert(rejected.join('\n'));
}

function readFileAsText(file, maxChars = MAX_CONTEXT_CHARS) {
    return file.slice(0, Math.max(4096, maxChars * 4)).text();
}

function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error(`Could not read ${file.name}`));
        reader.readAsDataURL(file);
    });
}

function loadImage(source) {
    return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error('Could not load the selected image.'));
        image.src = source;
    });
}

async function imageToOptimizedDataURL(file) {
    const source = await readFileAsDataURL(file);
    const image = await loadImage(source);
    const maxDimension = 1600;
    const scale = Math.min(1, maxDimension / Math.max(image.width, image.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
}

function videoToFrameDataURL(file) {
    return new Promise((resolve, reject) => {
        const video = document.createElement('video');
        const objectUrl = URL.createObjectURL(file);
        video.muted = true;
        video.preload = 'metadata';

        const cleanup = () => URL.revokeObjectURL(objectUrl);
        video.onerror = () => {
            cleanup();
            reject(new Error(`Could not read video ${file.name}.`));
        };
        video.onloadedmetadata = () => {
            video.currentTime = Math.min(1, Math.max(0, video.duration / 10 || 0));
        };
        video.onseeked = () => {
            const maxDimension = 1600;
            const scale = Math.min(1, maxDimension / Math.max(video.videoWidth, video.videoHeight));
            const canvas = document.createElement('canvas');
            canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
            canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
            canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
            const frame = canvas.toDataURL('image/jpeg', 0.82);
            cleanup();
            resolve({ frame, duration: video.duration });
        };
        video.src = objectUrl;
    });
}

async function extractPdfText(file) {
    if (!window.pdfjsLib) return '';
    const documentData = await file.arrayBuffer();
    const pdf = await window.pdfjsLib.getDocument({ data: documentData }).promise;
    const pages = [];
    for (let pageNumber = 1; pageNumber <= Math.min(pdf.numPages, 25); pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const textContent = await page.getTextContent();
        pages.push(textContent.items.map((item) => item.str).join(' '));
        if (pages.join('\n').length >= MAX_CONTEXT_CHARS) break;
    }
    return pages.join('\n\n');
}

async function extractDocxText(file) {
    if (!window.mammoth) return '';
    const result = await window.mammoth.extractRawText({ arrayBuffer: await file.arrayBuffer() });
    return result.value || '';
}

function isReadableTextFile(file) {
    return file.type.startsWith('text/') || TEXT_FILE_EXTENSIONS.has(fileExtension(file));
}

function isNoisyFolderFile(file) {
    const pathParts = (file.webkitRelativePath || file.name).toLowerCase().split('/');
    return pathParts.some((part) => [
        'node_modules', '.git', '.venv', 'venv', '__pycache__',
        'dist', 'build', '.next', '.cache', 'coverage'
    ].includes(part));
}

function fileProcessingScore(file) {
    const name = file.name.toLowerCase();
    if (/^(readme|license|changelog|package|requirements|pyproject|cargo|go\.mod)/.test(name)) return 0;
    if (isReadableTextFile(file)) return 1;
    if (fileExtension(file) === 'pdf' || fileExtension(file) === 'docx') return 2;
    if (file.type.startsWith('image/') || file.type.startsWith('video/')) return 3;
    return 4;
}

async function buildAttachmentContext(files) {
    const contextParts = [];
    let visualDataUrl = null;
    let remainingChars = MAX_CONTEXT_CHARS;
    let includedFiles = 0;
    let skippedFiles = 0;

    const appendContext = (value) => {
        if (!value || remainingChars <= 0) return false;
        const separatorLength = contextParts.length ? 2 : 0;
        const available = Math.max(0, remainingChars - separatorLength);
        if (!available) return false;
        const excerpt = value.slice(0, available);
        contextParts.push(excerpt);
        remainingChars -= excerpt.length + separatorLength;
        return excerpt.length === value.length;
    };

    const groups = getAttachmentGroups(files);
    for (const group of groups) {
        const extensionCounts = {};
        group.files.forEach((file) => {
            const extension = fileExtension(file) || file.type || 'unknown';
            extensionCounts[extension] = (extensionCounts[extension] || 0) + 1;
        });

        if (group.type === 'folder') {
            const pathPreview = group.files
                .slice(0, MAX_FOLDER_PATHS_IN_SUMMARY)
                .map((file) => attachmentName(file))
                .join('\n');
            const omittedPaths = Math.max(0, group.files.length - MAX_FOLDER_PATHS_IN_SUMMARY);
            appendContext(
                `Folder: ${group.name}\n` +
                `Files selected: ${group.files.length}\n` +
                `Total size: ${formatFileSize(group.totalSize)}\n` +
                `File types: ${Object.entries(extensionCounts).map(([type, count]) => `${type}: ${count}`).join(', ')}\n` +
                `Path sample:\n${pathPreview}` +
                (omittedPaths ? `\n... ${omittedPaths} additional paths omitted from the prompt.` : '')
            );
        }

        const filesToProcess = [...group.files]
            .filter((file) => group.type !== 'folder' || !isNoisyFolderFile(file))
            .sort((a, b) => fileProcessingScore(a) - fileProcessingScore(b) || a.size - b.size);
        skippedFiles += group.files.length - filesToProcess.length;

        for (const file of filesToProcess) {
            if (remainingChars < 500) {
                skippedFiles += 1;
                continue;
            }

            const name = attachmentName(file);
            const metadata = `Attachment: ${name} (${file.type || 'unknown type'}, ${formatFileSize(file.size)})`;

            try {
                if (file.type.startsWith('image/')) {
                    appendContext(metadata);
                    if (!visualDataUrl) visualDataUrl = await imageToOptimizedDataURL(file);
                    includedFiles += 1;
                    continue;
                }

                if (file.type.startsWith('video/')) {
                    if (!visualDataUrl) {
                        const videoData = await videoToFrameDataURL(file);
                        visualDataUrl = videoData.frame;
                        appendContext(`${metadata}; duration: ${videoData.duration.toFixed(1)} seconds. A representative frame is attached.`);
                    } else {
                        appendContext(metadata);
                    }
                    includedFiles += 1;
                    continue;
                }

                let extractedText = '';
                if (isReadableTextFile(file)) {
                    extractedText = await readFileAsText(file, remainingChars);
                } else if (file.type === 'application/pdf' || fileExtension(file) === 'pdf') {
                    extractedText = await extractPdfText(file);
                } else if (
                    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
                    fileExtension(file) === 'docx'
                ) {
                    extractedText = await extractDocxText(file);
                }

                if (extractedText) {
                    appendContext(`${metadata}\n--- File content excerpt ---\n${extractedText}\n--- End excerpt ---`);
                    includedFiles += 1;
                } else if (group.type !== 'folder') {
                    appendContext(`${metadata}. No readable text could be extracted in the browser.`);
                    includedFiles += 1;
                } else {
                    skippedFiles += 1;
                }
            } catch (error) {
                appendContext(`${metadata}. Processing failed: ${error.message}`);
                skippedFiles += 1;
            }
        }
    }

    if (skippedFiles > 0) {
        appendContext(
            `Context limit notice: ${includedFiles} file(s) were represented with metadata or excerpts; ` +
            `${skippedFiles} additional file(s) could not be included in this single AI request.`
        );
    }

    return {
        context: contextParts.length
            ? `\n\n[User attachments — bounded to fit the model context]\n${contextParts.join('\n\n')}`
            : '',
        visualDataUrl
    };
}

function historyForRequest() {
    const result = [];
    let remainingChars = MAX_HISTORY_REQUEST_CHARS;

    for (let index = chatHistory.length - 1; index >= 0 && remainingChars > 0; index -= 1) {
        const message = chatHistory[index];
        const content = String(message.content || message.displayContent || '').slice(-remainingChars);
        if (!content) continue;
        result.unshift({ role: message.role, content });
        remainingChars -= content.length;
    }
    return result;
}

function compactMessageForStorage(message) {
    const visibleContent = String(message.displayContent || message.content || '').slice(0, MAX_STORED_MESSAGE_CHARS);
    return {
        role: message.role,
        content: visibleContent,
        ...(message.displayContent ? { displayContent: visibleContent } : {}),
        ...(Array.isArray(message.images) && message.images.length
            ? { images: sanitizeGeneratedImages(message.images) }
            : {})
    };
}

function compactStoredChats() {
    try {
        const allChats = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '{}');
        const compactedEntries = Object.values(allChats)
            .sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))
            .slice(0, MAX_STORED_SESSIONS)
            .map((chat) => [
                chat.id,
                {
                    ...chat,
                    history: (chat.history || [])
                        .slice(-MAX_STORED_MESSAGES_PER_SESSION)
                        .map(compactMessageForStorage)
                }
            ]);
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(Object.fromEntries(compactedEntries)));
    } catch (error) {
        console.warn('Could not compact saved chats:', error);
        localStorage.removeItem(CHAT_STORAGE_KEY);
    }
}

function renderMarkdown(container, content) {
    container.innerHTML = DOMPurify.sanitize(marked.parse(content));
}

function sanitizeGeneratedImages(images) {
    if (!Array.isArray(images)) return [];
    return images
        .filter((image) => image && typeof image.url === 'string')
        .map((image) => ({
            url: image.url,
            filename: String(image.filename || '').slice(0, 180),
            alt: String(image.alt || 'Generated image').slice(0, 240),
            model: String(image.model || '').slice(0, 80),
            quality: String(image.quality || '').slice(0, 40),
            size: String(image.size || '').slice(0, 40),
            format: String(image.format || '').slice(0, 20)
        }))
        .filter((image) => image.url.startsWith('/static/generated/') || image.url.startsWith('https://'));
}

function renderGeneratedImages(container, images) {
    const safeImages = sanitizeGeneratedImages(images);
    if (!safeImages.length) return;

    const gallery = document.createElement('div');
    gallery.className = 'not-prose mt-4 grid gap-4';

    safeImages.forEach((image) => {
        const card = document.createElement('figure');
        card.className = 'overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm';

        const img = document.createElement('img');
        img.src = image.url;
        img.alt = image.alt || 'Generated image';
        img.loading = 'lazy';
        img.className = 'block w-full bg-slate-100 object-contain';

        const caption = document.createElement('figcaption');
        caption.className = 'flex flex-col gap-3 border-t border-slate-100 p-3 sm:flex-row sm:items-center sm:justify-between';

        const meta = document.createElement('div');
        meta.className = 'text-xs text-slate-500';
        const details = [image.size, image.quality ? `${image.quality} quality` : '', image.model]
            .filter(Boolean)
            .join(' • ');
        meta.textContent = details || 'Generated image';

        const actions = document.createElement('div');
        actions.className = 'flex gap-2';

        const openLink = document.createElement('a');
        openLink.href = image.url;
        openLink.target = '_blank';
        openLink.rel = 'noopener';
        openLink.className = 'rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50';
        openLink.textContent = 'Open';

        const downloadLink = document.createElement('a');
        downloadLink.href = image.url;
        downloadLink.download = image.filename || 'pearl-ai-generated-image.png';
        downloadLink.className = 'rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700';
        downloadLink.textContent = 'Download';

        actions.append(openLink, downloadLink);
        caption.append(meta, actions);
        card.append(img, caption);
        gallery.appendChild(card);
    });

    container.appendChild(gallery);
}

function decorateCodeBlocks(container) {
    container.querySelectorAll('pre').forEach((pre) => {
        if (pre.querySelector('.code-copy-btn')) return;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'code-copy-btn flex items-center gap-1 rounded-lg bg-slate-700 px-2 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-600';
        button.title = 'Copy code';
        button.innerHTML = '<i data-lucide="copy" class="h-3.5 w-3.5"></i><span>Copy</span>';
        pre.appendChild(button);
    });
    lucide.createIcons();
}

async function loadAuthenticatedUser() {
    const response = await fetch('/api/me');
    if (!response.ok) {
        localStorage.removeItem('pearl_session_active');
        window.location.href = '/login';
        return;
    }

    const user = await response.json();
    localStorage.setItem('pearl_session_active', 'true');
    localStorage.setItem('pearl_user_name', user.name);
    localStorage.setItem('pearl_user_email', user.email);
    userNameInput.value = user.name;
    userAvatar.textContent = user.name.charAt(0).toUpperCase();
    if (isAndroidAgentApp) {
        await activateAndroidAgentApp();
        if (!isAgentMode) window.location.href = '/agent';
    }
}

loadAuthenticatedUser().catch(() => {
    window.location.href = '/login';
});

async function appendMessage(role, content, generationId = 0, images = []) {
    const wrapper = document.createElement('div');
    wrapper.className = `flex gap-6 animate-fade-in ${role === 'user' ? 'flex-row-reverse' : ''}`;
    
    const iconHTML = role === 'assistant' 
        ? `<div class="w-8 h-8 rounded-full border border-slate-200 flex items-center justify-center bg-white shrink-0 shadow-sm"><i data-lucide="sparkles" class="w-4 h-4 text-indigo-600"></i></div>`
        : `<div class="w-8 h-8 rounded-full border border-slate-200 flex items-center justify-center bg-white shrink-0 shadow-sm"><i data-lucide="user" class="w-4 h-4 text-slate-600"></i></div>`;

    wrapper.innerHTML = `
        ${iconHTML}
        <div class="space-y-4 ${role === 'user' ? 'message-user p-4 rounded-2xl max-w-[80%]' : 'flex-1 relative group/msg'}">
            <div class="prose prose-slate text-[15px] leading-relaxed text-slate-700">
            </div>
            ${role === 'assistant' ? `
            <button class="copy-btn absolute -top-2 right-0 p-1.5 opacity-0 group-hover/msg:opacity-100 hover:bg-slate-100 rounded-lg transition-all text-slate-400 hover:text-indigo-600" title="Copy response">
                <i data-lucide="copy" class="w-4 h-4"></i>
            </button>` : ''}
        </div>
    `;
    
    chatContainer.appendChild(wrapper);
    lucide.createIcons(); // Refresh icons for new messages

    const proseDiv = wrapper.querySelector('.prose');
    if (role === 'assistant') {
        let i = 0;
        return new Promise((resolve) => {
            activeTypingResolve = resolve;
            function type() {
                if (generationId && cancelledGenerations.has(generationId)) {
                    decorateCodeBlocks(proseDiv);
                    activeTypingTimer = null;
                    activeTypingResolve = null;
                    resolve(false);
                    return;
                }
                if (i <= content.length) {
                    renderMarkdown(proseDiv, content.substring(0, i));
                    i += 3; // Typing 3 chars at a time for better flow
                    scrollChatToBottom();
                    activeTypingTimer = setTimeout(type, 15);
                } else {
                    renderMarkdown(proseDiv, content);
                    renderGeneratedImages(proseDiv, images);
                    decorateCodeBlocks(proseDiv);
                    scrollChatToBottomAfterRender(wrapper);
                    activeTypingTimer = null;
                    activeTypingResolve = null;
                    resolve(true);
                }
            }
            type();
        });
    } else {
        renderMarkdown(proseDiv, content);
        renderGeneratedImages(proseDiv, images);
        decorateCodeBlocks(proseDiv);
        scrollChatToBottomAfterRender(wrapper, 'smooth');
    }
}

async function sendMessage() {
    if (sendBtn.dataset.generating === 'true') {
        stopGeneration();
        return;
    }

    const text = userInput.value.trim();
    if (!text && selectedAttachments.length === 0) return;

    const generationId = ++generationSequence;
    const requestController = new AbortController();
    activeGenerationId = generationId;
    activeRequestController = requestController;
    setGeneratingState(true);

    const attachmentsForMessage = [...selectedAttachments];
    const attachmentGroups = getAttachmentGroups(attachmentsForMessage);
    const attachmentSummary = attachmentGroups.length
        ? `\n\n📎 ${attachmentGroups.map((group) =>
            group.type === 'folder' ? `Folder: ${group.name}` : group.name
        ).join(', ')}`
        : '';
    const visibleAttachmentSummary = attachmentGroups.length
        ? `\n\nAttachments: ${attachmentGroups.map((group) =>
            group.type === 'folder' ? `Folder: ${group.name}` : group.name
        ).join(', ')}`
        : '';
    const visibleMessage = `${text || 'Please analyze the attached item(s).'}${visibleAttachmentSummary}`;

    appendMessage('user', visibleMessage);
    userInput.value = '';
    userInput.style.height = 'auto';
    selectedAttachments = [];
    renderAttachmentTray();

    // Add typing indicator
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'flex gap-6 animate-pulse';
    typingIndicator.id = 'typing-indicator';
    typingIndicator.innerHTML = `
        <div class="w-8 h-8 rounded-full border border-slate-200 flex items-center justify-center bg-white shrink-0 shadow-sm">
            <i data-lucide="sparkles" class="w-4 h-4 text-indigo-600"></i>
        </div>
        <div class="flex items-center">
            <span class="text-sm text-slate-400 italic">PearlAI is typing...</span>
        </div>
    `;
    chatContainer.appendChild(typingIndicator);
    lucide.createIcons();
    scrollChatToBottom('smooth');

    try {
        const attachmentData = await buildAttachmentContext(attachmentsForMessage);
        const requestText = `${text || 'Please analyze the attached item(s).'}${attachmentData.context}`;
        const selectedAgentDevice = isAgentMode && agentTarget === 'device' ? selectedDevice() : null;
        if (isAgentMode && agentTarget === 'device' && !selectedAgentDevice) {
            throw new Error('Pair and select a device before sending a device-control task.');
        }
        const workspaceSnapshot = isAgentMode
            ? (
                agentTarget === 'device'
                    ? `Paired device: ${selectedAgentDevice.name}\nPlatform: ${selectedAgentDevice.platform}\nCapabilities: ${(selectedAgentDevice.capabilities || []).join(', ')}`
                    : await buildAgentWorkspaceSnapshot()
            )
            : '';
        const response = await fetch(isAgentMode ? '/api/agent' : '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: requestController.signal,
            body: JSON.stringify({
                message: requestText,
                history: historyForRequest(),
                image: attachmentData.visualDataUrl,
                ...(isAgentMode ? {
                    workspace: workspaceSnapshot,
                    permission: agentPermission,
                    target: agentTarget,
                    device_id: selectedAgentDevice?.id || ''
                } : {})
            })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('pearl_session_active');
                window.location.href = '/login';
                return;
            }
            throw new Error(data.detail || data.message || `Server returned ${response.status}`);
        }
        const responseImages = sanitizeGeneratedImages(data.images);
        if (!data.reply && !responseImages.length) {
            throw new Error('Server returned an empty reply.');
        }

        let responseText = data.reply || '';
        if (isAgentMode && Array.isArray(data.operations) && data.operations.length) {
            if (agentTarget === 'device') {
                try {
                    const jobId = await queueDeviceOperations(data.operations);
                    responseText += '\n\n**Device Agent:** The task was sent to the paired device. Local approvals may appear there.';
                    const jobResult = await waitForDeviceJob(jobId, generationId);
                    if (cancelledGenerations.has(generationId)) return;
                    responseText += `\n\n**Device result:**\n\n${formatDeviceJobResult(jobResult)}`;
                } catch (error) {
                    responseText += `\n\n**Device Agent error:** ${error.message}`;
                }
            } else {
                const approvedOperations = agentPermission === 'full'
                    ? data.operations
                    : await requestAgentApproval(data.operations);
                if (cancelledGenerations.has(generationId)) return;

                if (approvedOperations.length) {
                    try {
                        const result = await applyAgentOperations(approvedOperations);
                        responseText += `\n\n**Agent result:** ${result}`;
                    } catch (error) {
                        responseText += `\n\n**Agent error:** ${error.message}`;
                    }
                } else {
                    responseText += '\n\n**Agent result:** Changes were not applied.';
                }
            }
        }

        typingIndicator.remove(); // Remove indicator before starting typewriter effect
        if (activeGenerationId === generationId) activeRequestController = null;
        const completed = await appendMessage('assistant', responseText, generationId, responseImages);
        if (!completed || cancelledGenerations.has(generationId)) return;
        
        chatHistory.push(
            { role: 'user', content: requestText, displayContent: visibleMessage },
            {
                role: 'assistant',
                content: responseText,
                ...(responseImages.length ? { images: responseImages } : {})
            }
        );
        saveChatSession();
        renderHistory();
    } catch (error) {
        typingIndicator.remove();
        if (error.name !== 'AbortError' && !cancelledGenerations.has(generationId)) {
            await appendMessage(
                'assistant',
                `Error: ${error.message || 'Could not reach Pearl AI. Please check if the server is running.'}`,
                generationId
            );
        }
    } finally {
        cancelledGenerations.delete(generationId);
        if (activeGenerationId === generationId) {
            activeGenerationId = 0;
            activeRequestController = null;
            activeTypingTimer = null;
            setGeneratingState(false);
        }
    }
}

function saveChatSession() {
    try {
        const allChats = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '{}');
        allChats[currentChatId] = {
            id: currentChatId,
            timestamp: new Date().toISOString(),
            history: chatHistory
                .slice(-MAX_STORED_MESSAGES_PER_SESSION)
                .map(compactMessageForStorage),
            preview: (chatHistory[0]?.displayContent || chatHistory[0]?.content || '').substring(0, 30) + '...'
        };

        const limitedChats = Object.values(allChats)
            .sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0))
            .slice(0, MAX_STORED_SESSIONS);
        localStorage.setItem(
            CHAT_STORAGE_KEY,
            JSON.stringify(Object.fromEntries(limitedChats.map((chat) => [chat.id, chat])))
        );
    } catch (error) {
        console.warn('Chat history storage was full; compacting saved chats.', error);
        compactStoredChats();
    }
}

function renderHistory() {
    const allChats = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '{}');
    recentChatsList.innerHTML = '';
    
    const sortedChats = Object.values(allChats).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    if (sortedChats.length === 0) {
        recentChatsList.innerHTML = '<div class="px-3 py-2 text-xs text-slate-400 italic">No history yet...</div>';
        return;
    }

    sortedChats.forEach(chat => {
        const item = document.createElement('div');
        item.className = `px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg cursor-pointer transition-colors truncate ${chat.id === currentChatId ? 'bg-slate-100 border-l-2 border-indigo-500' : ''}`;
        item.textContent = chat.preview || 'Empty Chat';
        item.onclick = () => loadChat(chat.id);
        recentChatsList.appendChild(item);
    });
}

function loadChat(id) {
    const allChats = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || '{}');
    const chat = allChats[id];
    if (!chat) return;

    currentChatId = id;
    chatHistory = chat.history;
    
    // Clear UI and reload messages
    chatContainer.innerHTML = '';
    chatHistory.forEach(msg => {
        const wrapper = document.createElement('div');
        wrapper.className = `flex gap-6 animate-fade-in ${msg.role === 'user' ? 'flex-row-reverse' : ''}`;
        const displayedContent = msg.displayContent || msg.content;
        wrapper.innerHTML = `
            <div class="w-8 h-8 rounded-full border border-slate-200 flex items-center justify-center bg-white shrink-0 shadow-sm">
                <i data-lucide="${msg.role === 'assistant' ? 'sparkles' : 'user'}" class="w-4 h-4 ${msg.role === 'assistant' ? 'text-indigo-600' : 'text-slate-600'}"></i>
            </div>
            <div class="space-y-4 ${msg.role === 'user' ? 'message-user p-4 rounded-2xl max-w-[80%]' : 'flex-1 relative group/msg'}">
                <div class="prose prose-slate text-[15px] leading-relaxed text-slate-700"></div>
                ${msg.role === 'assistant' ? `
                <button class="copy-btn absolute -top-2 right-0 p-1.5 opacity-0 group-hover/msg:opacity-100 hover:bg-slate-100 rounded-lg transition-all text-slate-400 hover:text-indigo-600" title="Copy response">
                    <i data-lucide="copy" class="w-4 h-4"></i>
                </button>` : ''}
            </div>`;
        const prose = wrapper.querySelector('.prose');
        renderMarkdown(prose, displayedContent);
        renderGeneratedImages(prose, msg.images);
        decorateCodeBlocks(prose);
        chatContainer.appendChild(wrapper);
    });
    lucide.createIcons();
    renderHistory();
    closeMobileSidebar();
    scrollChatToBottomAfterRender(chatContainer);
}

newChatBtn.onclick = () => {
    currentChatId = Date.now().toString();
    chatHistory = [];
    selectedAttachments = [];
    renderAttachmentTray();
    chatContainer.innerHTML = '';
    renderHistory();
    closeMobileSidebar();
    userInput.focus({ preventScroll: true });
};

clearChatBtn.onclick = () => {
    if (confirm('Are you sure you want to clear all chat history?')) {
        localStorage.removeItem(CHAT_STORAGE_KEY);
        newChatBtn.onclick();
    }
};

attachFilesBtn.addEventListener('click', () => fileInput.click());
attachMediaBtn.addEventListener('click', () => mediaInput.click());
attachFolderBtn.addEventListener('click', () => folderInput.click());

fileInput.addEventListener('change', () => {
    addAttachments(fileInput.files);
    fileInput.value = '';
});

mediaInput.addEventListener('change', () => {
    addAttachments(mediaInput.files);
    mediaInput.value = '';
});

folderInput.addEventListener('change', () => {
    addAttachments(folderInput.files);
    folderInput.value = '';
});

attachmentTray.addEventListener('click', (event) => {
    const removeButton = event.target.closest('.remove-attachment');
    if (!removeButton) return;
    selectedAttachments = selectedAttachments.filter(
        (file) => attachmentGroupKey(file) !== removeButton.dataset.key
    );
    renderAttachmentTray();
});

sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

userInput.addEventListener('input', function() {
    resizeComposerInput();
});

userInput.addEventListener('focus', () => {
    setTimeout(() => {
        syncViewportHeight();
        scrollChatToBottom();
    }, 150);
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
        closeMobileSidebar();
    }
});

// Add event listener for copying messages
chatContainer.addEventListener('click', async (e) => {
    const codeCopyBtn = e.target.closest('.code-copy-btn');
    if (codeCopyBtn) {
        const code = codeCopyBtn.closest('pre')?.querySelector('code')?.innerText || '';
        if (!code) return;

        try {
            await navigator.clipboard.writeText(code);
            codeCopyBtn.innerHTML = '<i data-lucide="check" class="h-3.5 w-3.5"></i><span>Copied</span>';
            codeCopyBtn.classList.add('text-emerald-300');
            lucide.createIcons();
            setTimeout(() => {
                codeCopyBtn.innerHTML = '<i data-lucide="copy" class="h-3.5 w-3.5"></i><span>Copy</span>';
                codeCopyBtn.classList.remove('text-emerald-300');
                lucide.createIcons();
            }, 2000);
        } catch (err) {
            console.error('Failed to copy code: ', err);
        }
        return;
    }

    const copyBtn = e.target.closest('.copy-btn');
    if (!copyBtn) return;

    const messageContainer = copyBtn.closest('.group\\/msg');
    if (!messageContainer) return;
    const textToCopy = messageContainer.querySelector('.prose').innerText;

    try {
        await navigator.clipboard.writeText(textToCopy);
        const icon = copyBtn.querySelector('i');
        icon.setAttribute('data-lucide', 'check');
        copyBtn.classList.add('text-emerald-500');
        copyBtn.classList.remove('text-slate-400');
        lucide.createIcons();

        setTimeout(() => {
            icon.setAttribute('data-lucide', 'copy');
            copyBtn.classList.remove('text-emerald-500');
            copyBtn.classList.add('text-slate-400');
            lucide.createIcons();
        }, 2000);
    } catch (err) {
        console.error('Failed to copy text: ', err);
    }
});

// Profile Persistence & Interaction
const savedName = localStorage.getItem('pearl_user_name');
if (savedName) {
    userNameInput.value = savedName;
    userAvatar.textContent = savedName.charAt(0).toUpperCase();
}

userNameInput.addEventListener('input', (e) => {
    const name = e.target.value.trim();
    localStorage.setItem('pearl_user_name', name);
    userAvatar.textContent = name ? name.charAt(0).toUpperCase() : 'U';
});

userNameInput.addEventListener('click', (e) => {
    e.stopPropagation();
    userNameInput.focus();
});

profileBtn.addEventListener('click', async (e) => {
    // Only trigger if not clicking the input itself
    if (e.target.id !== 'user-name-input') {
        if (confirm('Would you like to logout?')) {
            await fetch('/api/logout', { method: 'POST' }).catch(() => {});
            localStorage.removeItem('pearl_session_active');
            localStorage.removeItem('pearl_user_name');
            localStorage.removeItem('pearl_user_email');
            window.location.href = '/login';
        }
    }
});

// Voice Input Feature
if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
    recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.continuous = false; // Listen for a single utterance
    recognition.interimResults = true; // Get interim results
    recognition.lang = 'en-US'; // Set language

    let isListening = false;

    micBtn.addEventListener('click', () => {
        if (isListening) {
            recognition.stop();
        } else {
            recognition.start();
        }
    });

    recognition.onstart = () => {
        isListening = true;
        micBtn.innerHTML = '<i data-lucide="mic-off" class="w-5 h-5 text-red-500"></i>';
        micBtn.title = 'Stop Voice Input';
        lucide.createIcons();
        userInput.placeholder = 'Listening...';
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript;
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }
        userInput.value = finalTranscript || interimTranscript;
        resizeComposerInput();
    };

    recognition.onend = () => {
        isListening = false;
        micBtn.innerHTML = '<i data-lucide="mic" class="w-5 h-5"></i>';
        micBtn.title = 'Voice Input';
        lucide.createIcons();
        userInput.placeholder = 'Message PearlAI...';
    };

    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        alert('Voice input error: ' + event.error);
        isListening = false;
        micBtn.innerHTML = '<i data-lucide="mic" class="w-5 h-5"></i>';
        micBtn.title = 'Voice Input';
        lucide.createIcons();
        userInput.placeholder = 'Message PearlAI...';
    };
} else {
    micBtn.style.display = 'none'; // Hide mic button if not supported
    console.warn('Web Speech API not supported in this browser.');
}

// Initial Load
initializeAgentMode();
syncResponsiveLayout();
resizeComposerInput();
compactStoredChats();
renderHistory();
