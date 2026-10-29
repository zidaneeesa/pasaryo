(function () {
  'use strict';

  const loadingEl = document.getElementById('account-loading');
  const guestWorkspaceEl = document.getElementById('guest-workspace');
  const memberWorkspaceEl = document.getElementById('member-workspace');
  const logoutWrapEl = document.getElementById('account-logout-wrap');
  const logoutBtn = document.getElementById('logout-btn');

  const tabLoginBtn = document.getElementById('tab-btn-login');
  const tabRegisterBtn = document.getElementById('tab-btn-register');
  const panelLoginEl = document.getElementById('panel-login');
  const panelRegisterEl = document.getElementById('panel-register');
  const loginForm = document.getElementById('login-form');
  const loginSubmitBtn = document.getElementById('login-submit-btn');
  const registerForm = document.getElementById('register-form');
  const registerSubmitBtn = document.getElementById('register-submit-btn');

  const profileAvatarEl = document.getElementById('profile-avatar');
  const profileEmailEl = document.getElementById('profile-email-display');
  const profileForm = document.getElementById('profile-form');
  const profileSubmitBtn = document.getElementById('profile-submit-btn');

  const passwordForm = document.getElementById('password-form');
  const passwordSubmitBtn = document.getElementById('password-submit-btn');

  const addressNewToggleBtn = document.getElementById('address-new-toggle-btn');
  const addressEmptyAddBtn = document.getElementById('addresses-empty-add-btn');
  const addressForm = document.getElementById('address-form');
  const addressFormTitle = document.getElementById('address-form-title');
  const addressEditIdInput = document.getElementById('address-edit-id');
  const addressSaveBtn = document.getElementById('address-save-btn');
  const addressCancelBtn = document.getElementById('address-cancel-btn');

  const addressesLoadingEl = document.getElementById('addresses-loading');
  const addressesErrorEl = document.getElementById('addresses-error');
  const addressesErrorMsgEl = document.getElementById('addresses-error-msg');
  const addressesRetryBtn = document.getElementById('addresses-retry-btn');
  const addressesEmptyEl = document.getElementById('addresses-empty');
  const addressesListEl = document.getElementById('addresses-list');

  function switchAuthTab(mode) {
    const isLogin = mode === 'login';
    tabLoginBtn.setAttribute('aria-selected', isLogin ? 'true' : 'false');
    tabRegisterBtn.setAttribute('aria-selected', isLogin ? 'false' : 'true');
    panelLoginEl.hidden = !isLogin;
    panelRegisterEl.hidden = isLogin;
  }

  function populateProfileForm(user) {
    profileAvatarEl.textContent = window.Pasaryo.computeInitials(user.full_name);
    profileEmailEl.textContent = user.email || '';
    profileForm.elements.full_name.value = user.full_name || '';
    profileForm.elements.phone.value = user.phone || '';
    profileForm.elements.date_of_birth.value = user.date_of_birth || '';
  }

  function openAddressFormForCreate() {
    window.Pasaryo.clearFormErrors(addressForm);
    addressForm.reset();
    addressEditIdInput.value = '';
    addressFormTitle.textContent = 'Tambah Alamat Pengiriman Baru';
    addressSaveBtn.textContent = 'Simpan Alamat Pengiriman';
    addressSaveBtn.dataset.originalLabel = 'Simpan Alamat Pengiriman';
    addressForm.hidden = false;
    addressForm.elements.label.focus();
  }

  async function openAddressFormForEdit(addressId, triggerBtn) {
    window.Pasaryo.setButtonBusy(triggerBtn, true, 'Memuat...');
    const res = await window.Pasaryo.apiRequest(
      '/accounts/addresses/' + encodeURIComponent(addressId) + '/'
    );
    window.Pasaryo.setButtonBusy(triggerBtn, false);

    if (!res.ok || !res.data || !res.data.address) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal memuat rincian alamat.',
        'error'
      );
      return;
    }

    const addr = res.data.address;
    window.Pasaryo.clearFormErrors(addressForm);
    addressEditIdInput.value = String(addr.id);
    addressForm.elements.label.value = addr.label || '';
    addressForm.elements.recipient_name.value = addr.recipient_name || '';
    addressForm.elements.recipient_phone.value = addr.recipient_phone || '';
    addressForm.elements.street_address.value = addr.street_address || '';
    addressForm.elements.subdistrict.value = addr.subdistrict || '';
    addressForm.elements.city.value = addr.city || '';
    addressForm.elements.province.value = addr.province || '';
    addressForm.elements.postal_code.value = addr.postal_code || '';

    addressFormTitle.textContent = 'Ubah Alamat: ' + addr.label;
    addressSaveBtn.textContent = 'Simpan Perubahan Alamat';
    addressSaveBtn.dataset.originalLabel = 'Simpan Perubahan Alamat';
    addressForm.hidden = false;
    addressForm.elements.label.focus();
  }

  function renderAddressCard(addr) {
    const card = document.createElement('article');
    card.className = 'record-item';
    const mainBadge = addr.is_main
      ? '<span class="badge badge-success">Alamat Utama</span>'
      : '';

    const setMainBtnHtml = addr.is_main
      ? ''
      : '<button type="button" class="btn btn-subtle btn-sm" data-addr-main="' +
        addr.id +
        '">Jadikan Utama</button>';

    card.innerHTML =
      '<div class="record-info">' +
      '<div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px;">' +
      '<strong>' +
      window.Pasaryo.escapeHtml(addr.label) +
      '</strong>' +
      mainBadge +
      '</div>' +
      '<p style="margin-bottom: 4px;">' +
      window.Pasaryo.escapeHtml(addr.recipient_name) +
      ' &middot; <span class="mono-num">' +
      window.Pasaryo.escapeHtml(addr.recipient_phone) +
      '</span></p>' +
      '<p class="text-secondary" style="margin-bottom: 0;">' +
      window.Pasaryo.escapeHtml(addr.street_address) +
      ', ' +
      window.Pasaryo.escapeHtml(addr.subdistrict) +
      ', ' +
      window.Pasaryo.escapeHtml(addr.city) +
      ', ' +
      window.Pasaryo.escapeHtml(addr.province) +
      ' <span class="mono-num">' +
      window.Pasaryo.escapeHtml(addr.postal_code) +
      '</span></p>' +
      '</div>' +
      '<div class="record-controls">' +
      setMainBtnHtml +
      '<button type="button" class="btn btn-secondary btn-sm" data-addr-edit="' +
      addr.id +
      '">Ubah</button>' +
      '<button type="button" class="btn btn-danger btn-sm" data-addr-delete="' +
      addr.id +
      '">Hapus</button>' +
      '</div>';

    const mainBtn = card.querySelector('[data-addr-main]');
    if (mainBtn) {
      mainBtn.addEventListener('click', function () {
        handleSetMainAddress(addr.id, mainBtn);
      });
    }

    const editBtn = card.querySelector('[data-addr-edit]');
    if (editBtn) {
      editBtn.addEventListener('click', function () {
        openAddressFormForEdit(addr.id, editBtn);
      });
    }

    const deleteBtn = card.querySelector('[data-addr-delete]');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', function () {
        handleDeleteAddress(addr.id, addr.label, deleteBtn);
      });
    }

    return card;
  }

  async function loadAddresses() {
    addressesLoadingEl.hidden = false;
    addressesErrorEl.hidden = true;
    addressesEmptyEl.hidden = true;
    addressesListEl.hidden = true;

    const res = await window.Pasaryo.apiRequest('/accounts/addresses/');
    addressesLoadingEl.hidden = true;

    if (!res.ok || !res.data) {
      addressesErrorMsgEl.textContent =
        (res.data && res.data.message) || 'Gagal memuat daftar alamat.';
      addressesErrorEl.hidden = false;
      return;
    }

    const list = Array.isArray(res.data.results) ? res.data.results : [];
    if (list.length === 0) {
      addressesEmptyEl.hidden = false;
      return;
    }

    addressesListEl.innerHTML = '';
    list.forEach(function (addr) {
      addressesListEl.appendChild(renderAddressCard(addr));
    });
    addressesListEl.hidden = false;
  }

  async function handleSetMainAddress(addressId, buttonEl) {
    window.Pasaryo.setButtonBusy(buttonEl, true, 'Menyimpan...');
    const res = await window.Pasaryo.apiRequest(
      '/accounts/addresses/' + encodeURIComponent(addressId) + '/main/',
      { method: 'POST' }
    );
    window.Pasaryo.setButtonBusy(buttonEl, false);

    if (!res.ok) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal mengubah alamat utama.',
        'error'
      );
      return;
    }

    window.Pasaryo.showToast('Alamat utama berhasil diperbarui.', 'success');
    await loadAddresses();
  }

  async function handleDeleteAddress(addressId, labelName, buttonEl) {
    const confirmed = await window.Pasaryo.confirmAction({
      title: 'Hapus Alamat Pengiriman',
      description:
        'Apakah Anda yakin ingin menghapus alamat "' +
        (labelName || 'ini') +
        '" dari buku alamat Anda?',
      confirmLabel: 'Ya, Hapus Alamat',
      cancelLabel: 'Batal',
    });
    if (!confirmed) {
      return;
    }

    window.Pasaryo.setButtonBusy(buttonEl, true, 'Menghapus...');
    const res = await window.Pasaryo.apiRequest(
      '/accounts/addresses/' + encodeURIComponent(addressId) + '/',
      { method: 'DELETE' }
    );
    window.Pasaryo.setButtonBusy(buttonEl, false);

    if (!res.ok) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal menghapus alamat.',
        'error'
      );
      return;
    }

    window.Pasaryo.showToast('Alamat berhasil dihapus.', 'success');
    await loadAddresses();
  }

  async function checkAccountSession() {
    loadingEl.hidden = false;
    guestWorkspaceEl.hidden = true;
    memberWorkspaceEl.hidden = true;
    logoutWrapEl.hidden = true;

    const user = await window.Pasaryo.syncHeaderState();
    loadingEl.hidden = true;

    if (!user) {
      guestWorkspaceEl.hidden = false;
      return;
    }

    logoutWrapEl.hidden = false;
    memberWorkspaceEl.hidden = false;
    populateProfileForm(user);
    await loadAddresses();
  }

  if (tabLoginBtn && tabRegisterBtn) {
    tabLoginBtn.addEventListener('click', function () {
      switchAuthTab('login');
    });
    tabRegisterBtn.addEventListener('click', function () {
      switchAuthTab('register');
    });
  }

  if (loginForm) {
    window.Pasaryo.bindLiveErrorClear(loginForm);
    loginForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(loginForm);

      const email = String(loginForm.elements.email.value || '').trim();
      const password = String(loginForm.elements.password.value || '');

      if (!email) {
        window.Pasaryo.setFieldError(loginForm, 'email', 'Masukkan alamat email Anda.');
        return;
      }
      if (!password) {
        window.Pasaryo.setFieldError(loginForm, 'password', 'Masukkan kata sandi Anda.');
        return;
      }

      window.Pasaryo.setButtonBusy(loginSubmitBtn, true, 'Memverifikasi...');
      const res = await window.Pasaryo.apiRequest('/accounts/login/', {
        method: 'POST',
        body: { email: email, password: password },
      });
      window.Pasaryo.setButtonBusy(loginSubmitBtn, false);

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          loginForm,
          res.data,
          (res.data && res.data.message) || 'Email atau kata sandi tidak sesuai.'
        );
        return;
      }

      loginForm.reset();
      window.Pasaryo.showToast('Berhasil masuk ke akun Anda.', 'success');
      await checkAccountSession();
    });
  }

  if (registerForm) {
    window.Pasaryo.bindLiveErrorClear(registerForm);
    registerForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(registerForm);

      const fullName = String(registerForm.elements.full_name.value || '').trim();
      const email = String(registerForm.elements.email.value || '').trim();
      const password1 = String(registerForm.elements.password1.value || '');
      const password2 = String(registerForm.elements.password2.value || '');

      if (!fullName) {
        window.Pasaryo.setFieldError(registerForm, 'full_name', 'Nama lengkap wajib diisi.');
        return;
      }
      if (!email) {
        window.Pasaryo.setFieldError(registerForm, 'email', 'Alamat email wajib diisi.');
        return;
      }
      if (!password1) {
        window.Pasaryo.setFieldError(registerForm, 'password1', 'Kata sandi wajib diisi.');
        return;
      }
      if (password1 !== password2) {
        window.Pasaryo.setFieldError(
          registerForm,
          'password2',
          'Konfirmasi kata sandi tidak sama.'
        );
        return;
      }

      window.Pasaryo.setButtonBusy(registerSubmitBtn, true, 'Mendaftarkan Akun...');
      const res = await window.Pasaryo.apiRequest('/accounts/register/', {
        method: 'POST',
        body: {
          full_name: fullName,
          email: email,
          password1: password1,
          password2: password2,
        },
      });
      window.Pasaryo.setButtonBusy(registerSubmitBtn, false);

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          registerForm,
          res.data,
          (res.data && res.data.message) || 'Pendaftaran akun belum berhasil.'
        );
        return;
      }

      registerForm.reset();
      window.Pasaryo.showToast(
        'Registrasi berhasil! Silakan masuk dengan email dan kata sandi baru Anda.',
        'success'
      );
      switchAuthTab('login');
      loginForm.elements.email.value = email;
      loginForm.elements.password.focus();
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener('click', async function () {
      window.Pasaryo.setButtonBusy(logoutBtn, true, 'Keluar...');
      const res = await window.Pasaryo.apiRequest('/accounts/logout/', {
        method: 'POST',
      });
      window.Pasaryo.setButtonBusy(logoutBtn, false);
      if (res.ok) {
        await window.Pasaryo.ensureCsrfToken(true);
        window.Pasaryo.showToast('Anda telah keluar dari akun.', 'success');
        await checkAccountSession();
      }
    });
  }

  if (profileForm) {
    window.Pasaryo.bindLiveErrorClear(profileForm);
    profileForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(profileForm);

      const fullName = String(profileForm.elements.full_name.value || '').trim();
      const phone = String(profileForm.elements.phone.value || '').trim();
      const dob = String(profileForm.elements.date_of_birth.value || '').trim();

      if (!fullName) {
        window.Pasaryo.setFieldError(profileForm, 'full_name', 'Nama lengkap tidak boleh kosong.');
        return;
      }

      window.Pasaryo.setButtonBusy(profileSubmitBtn, true, 'Menyimpan Profil...');
      const res = await window.Pasaryo.apiRequest('/accounts/profile/', {
        method: 'POST',
        body: {
          full_name: fullName,
          phone: phone,
          date_of_birth: dob || null,
        },
      });
      window.Pasaryo.setButtonBusy(profileSubmitBtn, false);

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          profileForm,
          res.data,
          (res.data && res.data.message) || 'Gagal memperbarui profil.'
        );
        return;
      }

      if (res.data && res.data.user) {
        populateProfileForm(res.data.user);
      }
      await window.Pasaryo.syncHeaderState();
      window.Pasaryo.showToast('Profil berhasil diperbarui.', 'success');
    });
  }

  if (passwordForm) {
    window.Pasaryo.bindLiveErrorClear(passwordForm);
    passwordForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(passwordForm);

      const oldPassword = String(passwordForm.elements.old_password.value || '');
      const newPassword1 = String(passwordForm.elements.new_password1.value || '');
      const newPassword2 = String(passwordForm.elements.new_password2.value || '');

      if (!oldPassword) {
        window.Pasaryo.setFieldError(
          passwordForm,
          'old_password',
          'Masukkan kata sandi saat ini.'
        );
        return;
      }
      if (!newPassword1) {
        window.Pasaryo.setFieldError(passwordForm, 'new_password1', 'Masukkan kata sandi baru.');
        return;
      }
      if (newPassword1 !== newPassword2) {
        window.Pasaryo.setFieldError(
          passwordForm,
          'new_password2',
          'Konfirmasi kata sandi baru tidak cocok.'
        );
        return;
      }

      window.Pasaryo.setButtonBusy(passwordSubmitBtn, true, 'Memperbarui Sandi...');
      const res = await window.Pasaryo.apiRequest('/accounts/change-password/', {
        method: 'POST',
        body: {
          old_password: oldPassword,
          new_password1: newPassword1,
          new_password2: newPassword2,
        },
      });
      window.Pasaryo.setButtonBusy(passwordSubmitBtn, false);

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          passwordForm,
          res.data,
          (res.data && res.data.message) || 'Gagal mengubah kata sandi.'
        );
        return;
      }

      passwordForm.reset();
      window.Pasaryo.showToast('Kata sandi akun berhasil diperbarui.', 'success');
    });
  }

  if (addressNewToggleBtn) {
    addressNewToggleBtn.addEventListener('click', openAddressFormForCreate);
  }
  if (addressEmptyAddBtn) {
    addressEmptyAddBtn.addEventListener('click', openAddressFormForCreate);
  }
  if (addressCancelBtn) {
    addressCancelBtn.addEventListener('click', function () {
      addressForm.hidden = true;
      window.Pasaryo.clearFormErrors(addressForm);
    });
  }
  if (addressesRetryBtn) {
    addressesRetryBtn.addEventListener('click', loadAddresses);
  }

  if (addressForm) {
    window.Pasaryo.bindLiveErrorClear(addressForm);
    addressForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(addressForm);

      const editId = String(addressEditIdInput.value || '').trim();
      const payload = {
        label: String(addressForm.elements.label.value || '').trim(),
        recipient_name: String(addressForm.elements.recipient_name.value || '').trim(),
        recipient_phone: String(addressForm.elements.recipient_phone.value || '').trim(),
        street_address: String(addressForm.elements.street_address.value || '').trim(),
        subdistrict: String(addressForm.elements.subdistrict.value || '').trim(),
        city: String(addressForm.elements.city.value || '').trim(),
        province: String(addressForm.elements.province.value || '').trim(),
        postal_code: String(addressForm.elements.postal_code.value || '').trim(),
      };

      let hasLocalErr = false;
      Object.keys(payload).forEach(function (fieldKey) {
        if (!payload[fieldKey]) {
          window.Pasaryo.setFieldError(addressForm, fieldKey, 'Kolom ini wajib diisi.');
          hasLocalErr = true;
        }
      });
      if (hasLocalErr) {
        return;
      }

      const url = editId
        ? '/accounts/addresses/' + encodeURIComponent(editId) + '/'
        : '/accounts/addresses/';
      const method = editId ? 'PATCH' : 'POST';

      window.Pasaryo.setButtonBusy(addressSaveBtn, true, 'Menyimpan Alamat...');
      const res = await window.Pasaryo.apiRequest(url, {
        method: method,
        body: payload,
      });
      window.Pasaryo.setButtonBusy(addressSaveBtn, false);

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          addressForm,
          res.data,
          (res.data && res.data.message) || 'Gagal menyimpan alamat pengiriman.'
        );
        return;
      }

      addressForm.hidden = true;
      addressForm.reset();
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Alamat berhasil disimpan.',
        'success'
      );
      await loadAddresses();
    });
  }

  document.addEventListener('DOMContentLoaded', checkAccountSession);
})();

