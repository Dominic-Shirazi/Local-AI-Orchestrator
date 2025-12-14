const API_BASE = window.location.origin;

document.addEventListener('DOMContentLoaded', () => {
    // Tab Switching
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

            btn.classList.add('active');
            const tabId = btn.dataset.tab;
            document.getElementById(`tab-${tabId}`).classList.add('active');
            document.getElementById('page-title').textContent = btn.textContent;

            if (tabId === 'routes' || tabId === 'providers') {
                loadConfig();
            }
        });
    });

    // Initial Load
    refreshStats();
    setInterval(refreshStats, 5000);
});

async function refreshStats() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();

        document.getElementById('stat-active-model').textContent = data.active_model || 'Idle';
        document.getElementById('stat-active-provider').textContent = data.active_provider || 'None';

        // Also load config for provider count if needed, or get it from health if we updated health
        // For now just basic stats
    } catch (e) {
        console.error("Failed to fetch stats", e);
    }
}

async function refreshRegistry() {
    await fetch(`${API_BASE}/refresh`, { method: 'POST' });
    alert('Registry refreshed!');
    loadConfig();
}

let currentRoutes = {};

async function loadConfig() {
    try {
        const res = await fetch(`${API_BASE}/health/config`);
        const data = await res.json();

        // Providers
        const provList = document.getElementById('providers-list');
        provList.innerHTML = '';
        document.getElementById('stat-providers-count').textContent = data.providers.length;

        data.providers.forEach(p => {
            const div = document.createElement('div');
            div.className = 'list-item provider-item';

            // Format models as a bullet list
            let modelsHtml = '<em class="text-secondary">None</em>';
            if (p.models && p.models.length > 0) {
                modelsHtml = '<ul class="model-list">' +
                    p.models.map(m => `<li>${m}</li>`).join('') +
                    '</ul>';
            }

            div.innerHTML = `
                <div class="item-header">
                    <strong>${p.id}</strong>
                    <span class="badge ${p.status}">${p.status}</span>
                </div>
                <div class="item-details">
                    <div style="margin-bottom: 8px;">
                        Type: <span class="text-accent">${p.type}</span> | 
                        Managed: <span class="text-accent">${p.managed}</span>
                    </div>
                    <div class="models-container">
                        <strong>Models:</strong>
                        ${modelsHtml}
                    </div>
                    <div class="actions" style="margin-top: 10px;">
                        <button class="btn secondary small" onclick="editProvider('${p.id}')">Edit Config</button>
                    </div>
                </div>
            `;
            provList.appendChild(div);
        });

        // Add "Add Provider" button at the bottom of the list
        const addBtnDiv = document.createElement('div');
        addBtnDiv.className = 'list-item center-content';
        addBtnDiv.style.textAlign = 'center';
        addBtnDiv.style.borderBottom = 'none';
        addBtnDiv.innerHTML = `<button class="btn primary" onclick="addNewProvider()">+ Add New Provider</button>`;
        provList.appendChild(addBtnDiv);


        // Routes
        currentRoutes = data.routes;
        renderRoutes();
    } catch (e) {
        console.error("Error loading config", e);
    }
}

function renderRoutes() {
    const container = document.getElementById('routes-container');
    container.innerHTML = '';

    // Convert object to editable JSON text for now (simplest for v1 UI)
    // Or render form inputs. Let's do a text area for raw editing of the object to be safe.
    // Ideally we want forms, but a JSON editor is robust.

    const textarea = document.createElement('textarea');
    textarea.id = 'routes-editor';
    textarea.className = 'code-editor';
    textarea.value = JSON.stringify(currentRoutes, null, 2);
    container.appendChild(textarea);
}

async function saveRoutes() {
    try {
        const textarea = document.getElementById('routes-editor');
        const newRoutes = JSON.parse(textarea.value);

        const res = await fetch(`${API_BASE}/health/config/routes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newRoutes)
        });

        if (res.ok) {
            alert('Routes saved successfully!');
            currentRoutes = newRoutes;
        } else {
            alert('Failed to save routes.');
        }
    } catch (e) {
        alert('Invalid JSON: ' + e.message);
    }
}

// --- Provider Management ---

function editProvider(providerId) {
    // Ideally fetch raw yaml content for this provider
    // For now we'll mock an alert or simple prompt, or build a modal.
    // Let's assume we fetch the raw yaml
    fetch(`${API_BASE}/admin/providers/${providerId}`)
        .then(res => res.text())
        .then(yaml => {
            showModal('Edit Provider', yaml, (newYaml) => saveProvider(providerId, newYaml));
        })
        .catch(e => {
            // If endpoint missing, default template
            alert("Edit feature requires backend implementation for reading raw provider configs. Coming soon!");
        });
}

function addNewProvider() {
    const template = `provider_id: "new_provider"
provider_type: "openai_compat"
api:
  base_url: "http://127.0.0.1:1234"
  health:
    method: "GET"
    path: "/v1/models"
    success_codes: [200]`;

    showModal('Add New Provider', template, (yaml) => {
        // Extract ID from yaml simplisticly or let backend handle filename
        const match = yaml.match(/provider_id:\s*"([^"]+)"/);
        const id = match ? match[1] : 'unknown';
        saveProvider(id, yaml);
    });
}

function saveProvider(id, yamlContent) {
    fetch(`${API_BASE}/admin/providers/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'text/yaml' },
        body: yamlContent
    }).then(res => {
        if (res.ok) {
            alert('Saved!');
            closeModal();
            refreshRegistry();
        } else {
            res.text().then(t => alert('Error: ' + t));
        }
    });
}

// Simple Modal Logic
function showModal(title, content, onSave) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <h2>${title}</h2>
            <textarea id="modal-editor" class="code-editor" style="height: 400px">${content}</textarea>
            <div class="actions" style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                <button class="btn secondary" onclick="closeModal()">Cancel</button>
                <button class="btn primary" id="modal-save">Save</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById('modal-save').onclick = () => {
        const val = document.getElementById('modal-editor').value;
        onSave(val);
    };
}


function closeModal() {
    const overlay = document.querySelector('.modal-overlay');
    if (overlay) overlay.remove();
}

// --- Logs ---
async function loadLogs() {
    try {
        const res = await fetch(`${API_BASE}/admin/logs?limit=50`);
        const data = await res.json();

        const container = document.querySelector('.log-viewer');
        container.innerHTML = '';

        if (data.logs && data.logs.length > 0) {
            data.logs.reverse().forEach(line => {
                try {
                    const entry = JSON.parse(line);
                    const div = document.createElement('div');
                    div.style.marginBottom = '8px';
                    div.style.fontFamily = 'monospace';
                    div.style.fontSize = '0.85rem';

                    const time = new Date(entry.timestamp * 1000).toLocaleTimeString();
                    const levelColor = entry.level === 'ERROR' ? 'var(--error)' : (entry.level === 'WARNING' ? '#e3b341' : 'var(--success)');

                    div.innerHTML = `
                        <span style="color: #666">[${time}]</span>
                        <span style="color: ${levelColor}; font-weight: bold">[${entry.level}]</span>
                        <span style="color: var(--text-primary)">${entry.message}</span>
                    `;
                    container.appendChild(div);
                } catch (e) {
                    // Fallback for non-json lines
                    const div = document.createElement('div');
                    div.textContent = line;
                    container.appendChild(div);
                }
            });
        } else {
            container.innerHTML = '<p style="color: var(--text-secondary)">No logs found.</p>';
        }
    } catch (e) {
        console.error("Failed to load logs", e);
    }
}

// Hook up log tab
document.querySelectorAll('.nav-item[data-tab="logs"]').forEach(btn => {
    btn.addEventListener('click', loadLogs);
});
