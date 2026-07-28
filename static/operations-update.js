function openUpdate() {
  document.getElementById('updateBackdrop').classList.add('show');
  if (!pendingUpdateInfo) {
    checkUpdate();
  }
}

function closeUpdate() {
  document.getElementById('updateBackdrop').classList.remove('show');
}

function onUpdateBackdrop(event) {
  if (event.target.id === 'updateBackdrop') closeUpdate();
}

function renderOpsUpdateStatus(data) {
  opsUpdateStatus = data || opsUpdateStatus || null;
  const statusEl = document.getElementById('opsUpdateStatus');
  const metaEl = document.getElementById('opsUpdateMeta');
  if (!statusEl || !metaEl) return;
  const state = opsUpdateStatus && opsUpdateStatus.state ? opsUpdateStatus.state : '';
  const message = opsUpdateStatus && opsUpdateStatus.message ? opsUpdateStatus.message : '尚未检查更新。';
  const current = opsUpdateStatus && opsUpdateStatus.current_version ? '当前版本 ' + opsUpdateStatus.current_version : '';
  const latest = opsUpdateStatus && opsUpdateStatus.latest_version ? '最新版本 ' + opsUpdateStatus.latest_version : '';
  const checked = opsUpdateStatus && opsUpdateStatus.checked_at ? '检查时间 ' + String(opsUpdateStatus.checked_at).replace('T', ' ') : '';
  statusEl.textContent = message;
  statusEl.dataset.state = state || 'unknown';
  const meta = [current, latest, checked].filter(Boolean).join(' · ');
  if (meta) metaEl.textContent = meta;
}

function checkUpdateFromOps() {
  renderOpsUpdateStatus({ state: 'checking', message: '正在检查更新...' });
  requestUpdateCheck(true);
  setOpsStatus('正在检查更新...', true);
}

function openUpdateFromOps() {
  openUpdate();
}

function checkUpdate() {
  requestUpdateCheck(false);
}

function requestUpdateCheck(silent) {
  pendingUpdateInfo = null;
  document.getElementById('updateButton').classList.remove('update-ready');
  document.getElementById('installUpdateButton').disabled = true;
  renderOpsUpdateStatus({ state: 'checking', message: '正在检查更新...' });
  if (!silent) {
    document.getElementById('updateStatus').textContent = '正在检查更新...';
    document.getElementById('updateMeta').textContent = '';
    document.getElementById('updateNotes').style.display = 'none';
  }
  lastAutoUpdateCheckAt = Date.now();
  socket.emit('check_update');
}

function scheduleAutoUpdateCheck() {
  if (autoUpdateTimer) {
    clearTimeout(autoUpdateTimer);
    autoUpdateTimer = null;
  }
  const elapsed = Date.now() - lastAutoUpdateCheckAt;
  const delay = lastAutoUpdateCheckAt ? Math.max(autoUpdateIntervalMs() - elapsed, 60 * 1000) : 2000;
  autoUpdateTimer = setTimeout(() => {
    requestUpdateCheck(true);
    scheduleAutoUpdateCheck();
  }, delay);
}

function applyUpdateStatus(data) {
  renderOpsUpdateStatus(data);
  const statusEl = document.getElementById('updateStatus');
  const metaEl = document.getElementById('updateMeta');
  const notesEl = document.getElementById('updateNotes');
  const installBtn = document.getElementById('installUpdateButton');
  const updateBtn = document.getElementById('updateButton');
  const progressEl = document.getElementById('updateProgress');
  const progressBar = progressEl ? progressEl.querySelector('span') : null;

  const current = data.current_version ? '当前版本 ' + data.current_version : '';
  const latest = data.latest_version ? '最新版本 ' + data.latest_version : '';
  const checked = data.checked_at ? '检查时间 ' + String(data.checked_at).replace('T', ' ') : '';
  metaEl.textContent = [current, latest, checked].filter(Boolean).join(' · ');
  statusEl.textContent = data.message || '更新状态未知。';
  notesEl.textContent = data.notes || '';
  notesEl.style.display = data.notes ? 'block' : 'none';
  if (progressEl && progressBar) {
    const percent = data.progress_percent == null ? null : Math.max(0, Math.min(100, Number(data.progress_percent)));
    progressEl.classList.toggle('show', data.state === 'downloading' || data.state === 'installing');
    progressBar.style.width = Number.isFinite(percent) ? percent + '%' : '35%';
  }

  if (data.state === 'available') {
    pendingUpdateInfo = {
      version: data.latest_version,
      notes: data.notes || '',
    };
    installBtn.disabled = false;
    updateBtn.classList.add('update-ready');
    return;
  }

  if (data.state === 'downloading' || data.state === 'installing') {
    installBtn.disabled = true;
    updateBtn.classList.add('update-ready');
    return;
  }

  pendingUpdateInfo = null;
  installBtn.disabled = true;
  updateBtn.classList.remove('update-ready');
}

function installUpdate() {
  if (!pendingUpdateInfo) return;
  document.getElementById('installUpdateButton').disabled = true;
  document.getElementById('updateStatus').textContent = '正在准备更新...';
  socket.emit('install_update');
}
