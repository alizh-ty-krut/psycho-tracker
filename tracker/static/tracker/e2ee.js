(() => {
  const prefix = 'point-support-e2ee-key-';
  const b64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes)));
  const unb64 = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));
  const keyName = id => prefix + id;
  const getKey = async id => {
    const raw = sessionStorage.getItem(keyName(id));
    return raw ? crypto.subtle.importKey('raw', unb64(raw), 'AES-GCM', false, ['encrypt', 'decrypt']) : null;
  };
  const encrypt = async (key, value) => {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({name: 'AES-GCM', iv}, key, new TextEncoder().encode(JSON.stringify(value)));
    const joined = new Uint8Array(iv.length + ciphertext.byteLength);
    joined.set(iv); joined.set(new Uint8Array(ciphertext), iv.length);
    return 'e2e1:' + b64(joined);
  };
  const decrypt = async (key, payload) => {
    const bytes = unb64(payload.slice(5));
    const clear = await crypto.subtle.decrypt({name: 'AES-GCM', iv: bytes.slice(0, 12)}, key, bytes.slice(12));
    return JSON.parse(new TextDecoder().decode(clear));
  };
  const download = (id, raw) => {
    const blob = new Blob([JSON.stringify({format: 'point-support-e2ee-v1', clientId: Number(id), key: raw})], {type: 'application/json'});
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `point-support-client-${id}-key.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  };
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  const ru = document.documentElement.lang === 'ru';
  const labels = {
    en: {content: 'Request', date: 'Date', feeling: 'Feeling', cause: 'Cause', intensity: 'Intensity', helpful_action: 'What could help', notes: 'Notes', bedtime: 'Bedtime', wake_time: 'Wake time', quality: 'Sleep quality', wellbeing: 'Wellbeing', last_coffee: 'Last coffee', comment: 'Psychologist comment'},
    ru: {content: 'Запрос', date: 'Дата', feeling: 'Чувство', cause: 'Причина', intensity: 'Интенсивность', helpful_action: 'Что может помочь', notes: 'Заметки', bedtime: 'Время отхода ко сну', wake_time: 'Время пробуждения', quality: 'Качество сна', wellbeing: 'Самочувствие', last_coffee: 'Последний кофе', comment: 'Комментарий психолога'}
  };
  const csrfForm = document.querySelector('[data-e2ee-csrf]');
  document.querySelectorAll('[data-create-key]').forEach(button => button.addEventListener('click', async () => {
    const id = button.dataset.clientId;
    let raw = sessionStorage.getItem(keyName(id));
    if (!raw) { const key = await crypto.subtle.generateKey({name: 'AES-GCM', length: 256}, true, ['encrypt', 'decrypt']); raw = b64(await crypto.subtle.exportKey('raw', key)); sessionStorage.setItem(keyName(id), raw); }
    download(id, raw);
    const status = document.querySelector('[data-key-status]'); if (status) status.textContent = ru ? 'Файл ключа скачан. Сохраните свою копию и безопасно передайте психологу отдельную.' : 'Key file downloaded. Keep one copy yourself and give the psychologist a separate copy securely.';
  }));
  document.querySelectorAll('[data-import-key]').forEach(input => input.addEventListener('change', async () => {
    try {
      const data = JSON.parse(await input.files[0].text());
      if (data.format !== 'point-support-e2ee-v1' || String(data.clientId) !== String(input.dataset.clientId)) throw new Error('wrong key file');
      const raw = unb64(data.key); await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
      sessionStorage.setItem(keyName(data.clientId), data.key); location.reload();
    } catch (_) { alert(ru ? 'Файл ключа неверный или относится к другому клиенту.' : 'The key file is invalid or belongs to a different client.'); }
  }));

  document.querySelectorAll('[data-e2ee-view]').forEach(async box => {
    const id = box.dataset.clientId, key = await getKey(id);
    try {
      let value;
      if (box.dataset.payload) value = await decrypt(key, box.dataset.payload);
      else if (box.dataset.legacy) {
        value = JSON.parse(box.dataset.legacy);
        if (key) {
          const encrypted = await encrypt(key, value);
          const response = await fetch(box.dataset.migrateUrl, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()}, body: JSON.stringify({payload: encrypted})});
          if (response.ok) box.dataset.payload = encrypted;
        }
      } else { box.textContent = box.dataset.lockedText || (ru ? 'Зашифровано. Импортируйте ключ.' : 'Encrypted. Import your key.'); return; }
      box.replaceChildren();
      const lang = ru ? 'ru' : 'en';
      const pairs = box.dataset.kind === 'request' ? [['content', value.content]] : box.dataset.kind === 'comment' ? [['comment', value.content]] : Object.entries(value);
      for (const [field, content] of pairs) {
        const row = document.createElement('p'); const label = labels[lang][field];
        if (label) { const strong = document.createElement('strong'); strong.textContent = label + ': '; row.appendChild(strong); }
        row.appendChild(document.createTextNode(content == null ? '' : String(content))); box.appendChild(row);
      }
    } catch (_) { box.textContent = box.dataset.lockedText || (ru ? 'Импортируйте правильный ключ, чтобы расшифровать запись.' : 'Import the correct key to decrypt this record.'); }
  });

  document.querySelectorAll('[data-e2ee-form]').forEach(form => {
    const id = form.dataset.clientId;
    const existing = form.dataset.editPayload;
    const legacy = form.dataset.legacy;
    const fill = async () => {
      const key = await getKey(id);
      if (!key) return;
      try {
        const data = existing ? await decrypt(key, existing) : legacy ? JSON.parse(legacy) : null;
        if (data) for (const [name, value] of Object.entries(data)) { const field = form.elements.namedItem(name); if (field) field.value = value ?? ''; }
      } catch (_) { const error = form.querySelector('[data-e2ee-error]'); if (error) error.textContent = ru ? 'Не удалось расшифровать запись этим ключом.' : 'Cannot decrypt this record with the current key.'; }
    };
    fill();
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const key = await getKey(id), error = form.querySelector('[data-e2ee-error]');
      if (!key) { if (error) error.textContent = ru ? 'Сначала создайте или импортируйте ключ шифрования.' : 'Create or import your encryption key first.'; return; }
      try {
        const data = {};
        for (const field of form.querySelectorAll('input[name],textarea[name],select[name]')) {
          if (!['csrfmiddlewaretoken', 'encrypted_payload', 'priority'].includes(field.name)) data[field.name] = field.value;
        }
        form.elements.namedItem('encrypted_payload').value = await encrypt(key, data);
        for (const field of form.querySelectorAll('input[name],textarea[name],select[name]')) if (!['csrfmiddlewaretoken', 'encrypted_payload', 'priority'].includes(field.name)) field.removeAttribute('name');
        form.submit();
      } catch (_) { if (error) error.textContent = ru ? 'Не удалось зашифровать запись. Текст не отправлен.' : 'Encryption failed. Your text was not sent.'; }
    });
  });
})();
