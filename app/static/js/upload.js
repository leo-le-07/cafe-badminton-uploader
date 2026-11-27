// "+ Thêm" and drag & drop in the left column: copies videos the user picks
// into INPUT_DIR (PUT /api/sources/<name>, app/server.py). The picked files
// stay where they are. Files are sent one at a time, with a progress bar; the
// server never overwrites a file already in input/.

import { EDITOR_HEADER } from './api.js';

const EXTENSIONS = ['.mov', '.mp4'];

const extension = (name) => {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(dot).toLowerCase() : '';
};

// Splits the picked files into those to send and those refused up front,
// each with the reason shown to the user. `existing`: names in input/.
export function planUploads(files, existing) {
  const taken = new Set(existing);
  const accepted = [];
  const skipped = [];
  for (const file of files) {
    const name = file.name;
    let reason = null;
    if (name.startsWith('.') || !EXTENSIONS.includes(extension(name))) reason = 'chỉ nhận .mov hoặc .mp4';
    else if (taken.has(name)) reason = 'đã có file cùng tên trong input/';
    if (reason) {
      skipped.push({ name, reason });
    } else {
      taken.add(name);
      accepted.push(file);
    }
  }
  return { accepted, skipped };
}

export const formatSize = (bytes) => {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  return `${Math.max(1, Math.round(bytes / 1e6))} MB`;
};

// XHR, not fetch: fetch reports no upload progress.
function send(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const mtime = file.lastModified ? `?mtime=${file.lastModified / 1000}` : '';
    xhr.open('PUT', `/api/sources/${encodeURIComponent(file.name)}${mtime}`);
    for (const [k, v] of Object.entries(EDITOR_HEADER)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve();
      let message = `Lỗi máy chủ (${xhr.status})`;
      try {
        const data = JSON.parse(xhr.responseText);
        if (Array.isArray(data?.errors) && data.errors.length) message = data.errors[0];
      } catch {
        // keep the generic message
      }
      reject(new Error(message));
    };
    xhr.onerror = () => reject(new Error('Không kết nối được với máy chủ'));
    xhr.send(file);
  });
}

// `els`: {button, input, panel, status, error}. `deps`: {getSourceNames(),
// onAdded()} — onAdded runs after each file lands, to refresh the list.
export function createUploader(els, deps) {
  const { button, input, panel, status, error } = els;
  const text = status.querySelector('.adding-text');
  const fill = status.querySelector('.bar div');
  let busy = false;

  function showErrors(lines) {
    error.hidden = lines.length === 0;
    error.textContent = lines.join('\n');
    error.style.whiteSpace = 'pre-line';
  }

  async function add(files) {
    if (busy || files.length === 0) return;
    const { accepted, skipped } = planUploads(files, deps.getSourceNames());
    const problems = skipped.map((s) => `${s.name}: ${s.reason}`);
    showErrors(problems);
    if (accepted.length === 0) return;
    busy = true;
    button.disabled = true;
    status.hidden = false;
    for (const [i, file] of accepted.entries()) {
      const label = `Đang chép ${file.name} (${formatSize(file.size)})`;
      const count = accepted.length > 1 ? ` · ${i + 1}/${accepted.length}` : '';
      const show = (ratio) => {
        text.textContent = `${label} · ${Math.floor(ratio * 100)}%${count}`;
        fill.style.width = `${ratio * 100}%`;
      };
      show(0);
      try {
        await send(file, show);
        await deps.onAdded();
      } catch (err) {
        problems.push(`${file.name}: ${err.message}`);
        showErrors(problems);
      }
    }
    status.hidden = true;
    button.disabled = false;
    busy = false;
  }

  button.addEventListener('click', () => {
    button.blur();
    if (!busy) input.click();
  });
  input.addEventListener('change', () => {
    const files = [...input.files];
    input.value = ''; // picking the same file again fires change again
    add(files);
  });

  // Drag & drop of files from Finder onto the left column.
  let depth = 0;
  const hasFiles = (e) => [...(e.dataTransfer?.types ?? [])].includes('Files');
  panel.addEventListener('dragenter', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth += 1;
    panel.classList.add('dragging');
  });
  panel.addEventListener('dragover', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = busy ? 'none' : 'copy';
  });
  panel.addEventListener('dragleave', (e) => {
    if (!hasFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) panel.classList.remove('dragging');
  });
  panel.addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    panel.classList.remove('dragging');
    add([...e.dataTransfer.files]);
  });

  // Closing the tab cuts the copy short (the server then throws it away).
  window.addEventListener('beforeunload', (e) => {
    if (busy) e.preventDefault();
  });

  return { busy: () => busy };
}
