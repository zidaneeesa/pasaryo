(function () {
  'use strict';

  let cachedCsrfToken = null;

  function getCookie(name) {
    const cookieStr = document.cookie || '';
    const parts = cookieStr.split(';');
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i].trim();
      if (part.startsWith(name + '=')) {
        return decodeURIComponent(part.substring(name.length + 1));
      }
    }
    return null;
  }

  async function ensureCsrfToken(forceRefresh) {
    if (!forceRefresh) {
      const fromCookie = getCookie('csrftoken');
      if (fromCookie) {
        cachedCsrfToken = fromCookie;
        return cachedCsrfToken;
      }
      if (cachedCsrfToken) {
        return cachedCsrfToken;
      }
    }
    try {
      const resp = await fetch('/accounts/csrf/', {
        method: 'GET',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (resp.ok) {
        const json = await resp.json();
        if (json && json.csrf_token) {
          cachedCsrfToken = json.csrf_token;
          return cachedCsrfToken;
        }
      }
    } catch (_err) {
      // Fallback to cookie if network call fails
    }
    return getCookie('csrftoken') || '';
  }

  async function apiRequest(url, options) {
    const opts = Object.assign({ method: 'GET' }, options || {});
    const method = (opts.method || 'GET').toUpperCase();
    const headers = Object.assign({ Accept: 'application/json' }, opts.headers || {});

    if (method !== 'GET' && method !== 'HEAD') {
      const token = await ensureCsrfToken(false);
      if (token) {
        headers['X-CSRFToken'] = token;
      }
      if (opts.body !== undefined && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
      }
    }

    const fetchConfig = {
      method: method,
      credentials: 'same-origin',
      headers: headers,
    };

    if (opts.body !== undefined) {
      fetchConfig.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    }

    try {
      const response = await fetch(url, fetchConfig);
      let data = null;
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        const rawText = await response.text();
        data = { message: rawText || 'Terjadi kesalahan pada server.' };
      }
      if (data && data.csrf_token) {
        cachedCsrfToken = data.csrf_token;
      }
      return {
        ok: response.ok,
        status: response.status,
        data: data,
      };
    } catch (_networkError) {
      return {
        ok: false,
        status: 0,
        data: {
          message: 'Gagal terhubung ke server. Periksa koneksi jaringan Anda lalu coba lagi.',
        },
      };
    }
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatRupiah(amount) {
    const num = Number(amount);
    if (Number.isNaN(num)) {
      return 'Rp 0';
    }
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  }

  function formatDateTime(isoString) {
    if (!isoString) {
      return 'Belum tercatat';
    }
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return String(isoString);
    }
    return new Intl.DateTimeFormat('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  }

  function formatDateOnly(isoString) {
    if (!isoString) {
      return 'Belum ditentukan';
    }
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return String(isoString);
    }
    return new Intl.DateTimeFormat('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(date);
  }

  function computeInitials(fullName) {
    const clean = String(fullName || '').trim();
    if (!clean) {
      return 'AK';
    }
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function showToast(message, variant) {
    const region = document.getElementById('toast-region');
    if (!region || !message) {
      return;
    }
    const toast = document.createElement('div');
    const typeClass =
      variant === 'success'
        ? 'toast-success'
        : variant === 'error'
          ? 'toast-error'
          : '';
    toast.className = ('toast-banner ' + typeClass).trim();
    toast.setAttribute('role', variant === 'error' ? 'alert' : 'status');

    const textSpan = document.createElement('span');
    textSpan.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn btn-sm btn-subtle';
    closeBtn.textContent = 'Tutup';
    closeBtn.addEventListener('click', function () {
      toast.remove();
    });

    toast.appendChild(textSpan);
    toast.appendChild(closeBtn);
    region.appendChild(toast);

    window.setTimeout(function () {
      if (toast.parentNode) {
        toast.remove();
      }
    }, 5000);
  }

  function confirmAction(config) {
    const dialog = document.getElementById('confirm-dialog');
    const titleEl = document.getElementById('confirm-dialog-title');
    const descEl = document.getElementById('confirm-dialog-desc');
    const okBtn = document.getElementById('confirm-dialog-ok');
    const cancelBtn = document.getElementById('confirm-dialog-cancel');
    const triggerEl = document.activeElement;

    if (!dialog || typeof dialog.showModal !== 'function') {
      return Promise.resolve(window.confirm(config.description || 'Lanjutkan tindakan ini?'));
    }

    titleEl.textContent = config.title || 'Konfirmasi Tindakan';
    descEl.textContent = config.description || 'Apakah Anda yakin ingin melanjutkan?';
    okBtn.textContent = config.confirmLabel || 'Ya, Lanjutkan';
    cancelBtn.textContent = config.cancelLabel || 'Batal';

    return new Promise(function (resolve) {
      function cleanup(result) {
        okBtn.removeEventListener('click', onConfirm);
        cancelBtn.removeEventListener('click', onCancel);
        dialog.removeEventListener('close', onClose);
        if (dialog.open) {
          dialog.close();
        }
        if (triggerEl && typeof triggerEl.focus === 'function') {
          triggerEl.focus();
        }
        resolve(result);
      }

      function onConfirm() {
        cleanup(true);
      }

      function onCancel() {
        cleanup(false);
      }

      function onClose() {
        cleanup(false);
      }

      okBtn.addEventListener('click', onConfirm);
      cancelBtn.addEventListener('click', onCancel);
      dialog.addEventListener('close', onClose);

      dialog.showModal();
      cancelBtn.focus();
    });
  }

  function setButtonBusy(button, isBusy, busyLabel) {
    if (!button) {
      return;
    }
    if (isBusy) {
      if (!button.dataset.originalLabel) {
        button.dataset.originalLabel = button.textContent.trim();
      }
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      if (busyLabel) {
        button.textContent = busyLabel;
      }
    } else {
      button.disabled = false;
      button.setAttribute('aria-busy', 'false');
      if (button.dataset.originalLabel) {
        button.textContent = button.dataset.originalLabel;
      }
    }
  }

  function clearFormErrors(form) {
    if (!form) {
      return;
    }
    const invalidInputs = form.querySelectorAll('[aria-invalid="true"]');
    invalidInputs.forEach(function (el) {
      el.removeAttribute('aria-invalid');
    });
    const errorBoxes = form.querySelectorAll('[data-error-for]');
    errorBoxes.forEach(function (box) {
      box.textContent = '';
      box.hidden = true;
    });
    const formAlert = form.querySelector('[data-form-alert]');
    if (formAlert) {
      formAlert.textContent = '';
      formAlert.hidden = true;
    }
  }

  function setFieldError(form, fieldName, message) {
    if (!form) {
      return;
    }
    const input = form.querySelector('[name="' + fieldName + '"]');
    if (input) {
      input.setAttribute('aria-invalid', 'true');
    }
    const errorBox = form.querySelector('[data-error-for="' + fieldName + '"]');
    if (errorBox) {
      errorBox.textContent = message;
      errorBox.hidden = false;
    }
  }

  function applyFormErrors(form, responseData, fallbackMessage) {
    if (!form) {
      return;
    }
    const formAlert = form.querySelector('[data-form-alert]');
    let hasFieldErrors = false;

    if (responseData && responseData.errors && typeof responseData.errors === 'object') {
      Object.keys(responseData.errors).forEach(function (fieldKey) {
        const items = responseData.errors[fieldKey];
        if (Array.isArray(items) && items.length > 0) {
          const msg = items.map(function (it) { return it.message || it; }).join(' ');
          if (fieldKey === '__all__') {
            if (formAlert) {
              formAlert.textContent = msg;
              formAlert.hidden = false;
            }
          } else {
            setFieldError(form, fieldKey, msg);
            hasFieldErrors = true;
          }
        }
      });
    }

    if (!hasFieldErrors && formAlert) {
      const msg = (responseData && responseData.message) || fallbackMessage || 'Periksa kembali isian formulir Anda.';
      formAlert.textContent = msg;
      formAlert.hidden = false;
    }
  }

  function bindLiveErrorClear(form) {
    if (!form) {
      return;
    }
    form.addEventListener('input', function (event) {
      const target = event.target;
      if (!target || !target.name) {
        return;
      }
      target.removeAttribute('aria-invalid');
      const errorBox = form.querySelector('[data-error-for="' + target.name + '"]');
      if (errorBox) {
        errorBox.textContent = '';
        errorBox.hidden = true;
      }
    });
  }

  async function refreshCartBadge() {
    const badgeEl = document.getElementById('nav-cart-count');
    if (!badgeEl) {
      return;
    }
    const res = await apiRequest('/api/cart/');
    if (res.ok && res.data && res.data.data) {
      badgeEl.textContent = String(res.data.data.total_quantity || 0);
    } else {
      badgeEl.textContent = '0';
    }
  }

  async function syncHeaderState() {
    const initialsEl = document.getElementById('nav-user-initials');
    const labelEl = document.getElementById('nav-user-label');
    const res = await apiRequest('/accounts/me/');
    if (res.ok && res.data && res.data.user) {
      const user = res.data.user;
      document.body.dataset.authenticated = 'true';
      document.body.dataset.userName = user.full_name || '';
      if (initialsEl) {
        initialsEl.textContent = computeInitials(user.full_name);
      }
      if (labelEl) {
        labelEl.textContent = user.full_name || user.email;
      }
      await refreshCartBadge();
      return user;
    }
    document.body.dataset.authenticated = 'false';
    document.body.dataset.userName = '';
    if (initialsEl) {
      initialsEl.textContent = 'AK';
    }
    if (labelEl) {
      labelEl.textContent = 'Masuk / Daftar';
    }
    const badgeEl = document.getElementById('nav-cart-count');
    if (badgeEl) {
      badgeEl.textContent = '0';
    }
    return null;
  }

  function initMobileNav() {
    const toggleBtn = document.getElementById('mobile-menu-toggle');
    const navEl = document.getElementById('primary-navigation');
    if (!toggleBtn || !navEl) {
      return;
    }

    function closeMenu() {
      navEl.classList.remove('is-open');
      toggleBtn.setAttribute('aria-expanded', 'false');
    }

    toggleBtn.addEventListener('click', function () {
      const expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
      if (expanded) {
        closeMenu();
      } else {
        navEl.classList.add('is-open');
        toggleBtn.setAttribute('aria-expanded', 'true');
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && toggleBtn.getAttribute('aria-expanded') === 'true') {
        closeMenu();
        toggleBtn.focus();
      }
    });

    document.addEventListener('click', function (event) {
      if (
        toggleBtn.getAttribute('aria-expanded') === 'true' &&
        !navEl.contains(event.target) &&
        !toggleBtn.contains(event.target)
      ) {
        closeMenu();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initMobileNav();
    syncHeaderState();
  });

  window.Pasaryo = {
    apiRequest: apiRequest,
    ensureCsrfToken: ensureCsrfToken,
    escapeHtml: escapeHtml,
    formatRupiah: formatRupiah,
    formatDateTime: formatDateTime,
    formatDateOnly: formatDateOnly,
    computeInitials: computeInitials,
    showToast: showToast,
    confirmAction: confirmAction,
    setButtonBusy: setButtonBusy,
    clearFormErrors: clearFormErrors,
    setFieldError: setFieldError,
    applyFormErrors: applyFormErrors,
    bindLiveErrorClear: bindLiveErrorClear,
    refreshCartBadge: refreshCartBadge,
    syncHeaderState: syncHeaderState,
  };
})();

