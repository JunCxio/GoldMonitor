if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

function downloadText(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType || 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function syncEllipsisTitle(eventOrElement) {
  let target = eventOrElement && eventOrElement.target ? eventOrElement.target : eventOrElement;
  while (target && target.nodeType === 1 && target !== document.body) {
    const style = window.getComputedStyle(target);
    const isEllipsis = style.textOverflow === 'ellipsis' && style.overflow !== 'visible';
    const text = (target.textContent || '').trim();
    if (isEllipsis && text) {
      const isTruncated = target.scrollWidth > target.clientWidth || target.scrollHeight > target.clientHeight;
      if (isTruncated) {
        if (!target.getAttribute('title') || target.dataset.ellipsisTitle === 'true') {
          target.setAttribute('title', text);
          target.dataset.ellipsisTitle = 'true';
        }
      } else if (target.dataset.ellipsisTitle === 'true') {
        target.removeAttribute('title');
        delete target.dataset.ellipsisTitle;
      }
      return;
    }
    target = target.parentElement;
  }
}

function setupEllipsisTooltips() {
  document.addEventListener('mouseover', syncEllipsisTitle, true);
  document.addEventListener('focusin', syncEllipsisTitle, true);
}

setupEllipsisTooltips();
