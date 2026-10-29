(function () {
  'use strict';

  const loadingEl = document.getElementById('cart-loading');
  const authReqEl = document.getElementById('cart-auth-required');
  const errorEl = document.getElementById('cart-error');
  const errorMsgEl = document.getElementById('cart-error-msg');
  const retryBtn = document.getElementById('cart-retry-btn');
  const emptyEl = document.getElementById('cart-empty');
  const workspaceEl = document.getElementById('cart-workspace');

  const totalQtyBadge = document.getElementById('cart-total-qty-badge');
  const stockAlertEl = document.getElementById('cart-stock-alert');
  const itemsListEl = document.getElementById('cart-items-list');

  const promoForm = document.getElementById('promo-validate-form');
  const promoInput = document.getElementById('promo-code-input');
  const promoApplyBtn = document.getElementById('promo-apply-btn');
  const promoBannerEl = document.getElementById('promo-active-banner');
  const promoActiveTextEl = document.getElementById('promo-active-text');
  const promoClearBtn = document.getElementById('promo-clear-btn');

  const checkoutForm = document.getElementById('checkout-form');
  const addressSelect = document.getElementById('checkout-address-select');
  const addressPreview = document.getElementById('checkout-address-preview');
  const shippingListEl = document.getElementById('checkout-shipping-list');
  const paymentListEl = document.getElementById('checkout-payment-list');
  const checkoutSubmitBtn = document.getElementById('checkout-submit-btn');

  const summarySubtotalEl = document.getElementById('summary-subtotal');
  const summaryShippingEl = document.getElementById('summary-shipping');
  const summaryServiceEl = document.getElementById('summary-service');
  const summaryDiscountRow = document.getElementById('summary-discount-row');
  const summaryDiscountEl = document.getElementById('summary-discount');
  const summaryTotalEl = document.getElementById('summary-total');

  let cartState = { items: [], subtotal: 0, total_quantity: 0, has_stock_issue: false };
  let addresses = [];
  let shippingMethods = [];
  let paymentMethods = [];
  let activePromo = null;
  let checkoutKey = generateCheckoutKey();

  function generateCheckoutKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'chk-' + Date.now() + '-' + Math.random().toString(36).substring(2, 10);
  }

  function updateSummaryNumbers() {
    const subtotal = Number(cartState.subtotal || 0);
    const selectedShipRadio = shippingListEl.querySelector('input[name="shipping_method_id"]:checked');
    const selectedPayRadio = paymentListEl.querySelector('input[name="payment_method_id"]:checked');

    let shippingCost = 0;
    if (selectedShipRadio) {
      const method = shippingMethods.find(function (m) {
        return Number(m.id) === Number(selectedShipRadio.value);
      });
      if (method) {
        shippingCost = Number(method.base_cost || 0);
      }
    }

    let serviceFee = 0;
    if (selectedPayRadio) {
      const method = paymentMethods.find(function (m) {
        return Number(m.id) === Number(selectedPayRadio.value);
      });
      if (method) {
        serviceFee = Number(method.service_fee || 0);
      }
    }

    const discount = activePromo ? Number(activePromo.discount_amount || 0) : 0;
    const grandTotal = Math.max(0, subtotal - discount) + shippingCost + serviceFee;

    summarySubtotalEl.textContent = window.Pasaryo.formatRupiah(subtotal);
    summaryShippingEl.textContent = window.Pasaryo.formatRupiah(shippingCost);
    summaryServiceEl.textContent = window.Pasaryo.formatRupiah(serviceFee);

    if (discount > 0) {
      summaryDiscountEl.textContent = '-' + window.Pasaryo.formatRupiah(discount);
      summaryDiscountRow.hidden = false;
    } else {
      summaryDiscountRow.hidden = true;
    }

    summaryTotalEl.textContent = window.Pasaryo.formatRupiah(grandTotal);
    checkoutSubmitBtn.disabled = Boolean(cartState.has_stock_issue) || addresses.length === 0;
  }

  function renderCartItems() {
    itemsListEl.innerHTML = '';
    totalQtyBadge.textContent = (cartState.total_quantity || 0) + ' barang';
    stockAlertEl.hidden = !cartState.has_stock_issue;

    cartState.items.forEach(function (item) {
      const row = document.createElement('article');
      row.className = 'record-item';
      const detailUrl = '/produk/' + encodeURIComponent(item.product_id) + '/';
      const availBadge = item.is_available
        ? '<span class="badge badge-success mono-num">Stok: ' + item.stock + '</span>'
        : '<span class="badge badge-danger mono-num">Stok hanya ' + item.stock + '</span>';

      const qtyInputId = 'cart-qty-' + item.id;

      row.innerHTML =
        '<div class="record-info">' +
        '<h3><a href="' +
        detailUrl +
        '" style="color: var(--text-primary); text-decoration: none;">' +
        window.Pasaryo.escapeHtml(item.product_name) +
        '</a></h3>' +
        '<p class="text-muted mono-num" style="margin-bottom: 8px;">Varian: ' +
        window.Pasaryo.escapeHtml(item.color_name) +
        ' &middot; SKU: ' +
        window.Pasaryo.escapeHtml(item.sku) +
        '</p>' +
        '<div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">' +
        '<span class="mono-num" style="font-weight: 600;">' +
        window.Pasaryo.formatRupiah(item.unit_price) +
        ' / unit</span>' +
        availBadge +
        '</div>' +
        '</div>' +
        '<div class="record-controls">' +
        '<label for="' +
        qtyInputId +
        '" class="form-label" style="margin-right: 4px;">Jumlah</label>' +
        '<div class="qty-stepper">' +
        '<button type="button" class="qty-btn" data-qty-step="-1" aria-label="Kurangi jumlah ' +
        window.Pasaryo.escapeHtml(item.product_name) +
        '">-</button>' +
        '<input type="number" id="' +
        qtyInputId +
        '" class="qty-input" value="' +
        item.quantity +
        '" min="1" max="' +
        Math.max(1, item.stock) +
        '">' +
        '<button type="button" class="qty-btn" data-qty-step="1" aria-label="Tambah jumlah ' +
        window.Pasaryo.escapeHtml(item.product_name) +
        '">+</button>' +
        '</div>' +
        '<strong class="mono-num" style="min-width: 110px; text-align: right;">' +
        window.Pasaryo.formatRupiah(item.line_total) +
        '</strong>' +
        '<button type="button" class="btn btn-danger btn-sm" data-cart-remove="' +
        item.id +
        '">Hapus</button>' +
        '</div>';

      const inputEl = row.querySelector('#' + qtyInputId);
      const stepBtns = row.querySelectorAll('[data-qty-step]');
      stepBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
          const delta = Number(btn.dataset.qtyStep);
          const nextQty = Number(inputEl.value || item.quantity) + delta;
          if (nextQty >= 1) {
            handleUpdateQuantity(item.id, nextQty, btn);
          }
        });
      });

      inputEl.addEventListener('change', function () {
        const nextQty = Number(inputEl.value);
        if (Number.isInteger(nextQty) && nextQty >= 1 && nextQty !== item.quantity) {
          handleUpdateQuantity(item.id, nextQty, null);
        } else {
          inputEl.value = String(item.quantity);
        }
      });

      const removeBtn = row.querySelector('[data-cart-remove]');
      removeBtn.addEventListener('click', function () {
        handleRemoveCartItem(item.id, item.product_name, removeBtn);
      });

      itemsListEl.appendChild(row);
    });
  }

  async function handleUpdateQuantity(cartItemId, quantity, buttonEl) {
    if (buttonEl) {
      buttonEl.disabled = true;
    }
    const res = await window.Pasaryo.apiRequest(
      '/api/cart/' + encodeURIComponent(cartItemId) + '/',
      {
        method: 'PATCH',
        body: { quantity: Number(quantity) },
      }
    );
    if (buttonEl) {
      buttonEl.disabled = false;
    }

    if (!res.ok) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal memperbarui jumlah barang.',
        'error'
      );
      await refreshCartOnly();
      return;
    }

    cartState = res.data.data;
    checkoutKey = generateCheckoutKey();
    if (activePromo) {
      await revalidatePromoSilently();
    }
    await window.Pasaryo.refreshCartBadge();
    renderCartView();
  }

  async function handleRemoveCartItem(cartItemId, productName, buttonEl) {
    const confirmed = await window.Pasaryo.confirmAction({
      title: 'Hapus Barang dari Keranjang',
      description:
        'Apakah Anda yakin ingin menghapus "' +
        (productName || 'barang ini') +
        '" dari keranjang belanja?',
      confirmLabel: 'Ya, Hapus Barang',
      cancelLabel: 'Batal',
    });

    if (!confirmed) {
      return;
    }

    window.Pasaryo.setButtonBusy(buttonEl, true, 'Menghapus...');
    const res = await window.Pasaryo.apiRequest(
      '/api/cart/' + encodeURIComponent(cartItemId) + '/',
      { method: 'DELETE' }
    );
    window.Pasaryo.setButtonBusy(buttonEl, false);

    if (!res.ok) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal menghapus barang dari keranjang.',
        'error'
      );
      return;
    }

    cartState = res.data.data;
    checkoutKey = generateCheckoutKey();
    if (activePromo) {
      await revalidatePromoSilently();
    }
    await window.Pasaryo.refreshCartBadge();
    window.Pasaryo.showToast('Barang dihapus dari keranjang.', 'success');
    renderCartView();
  }

  async function revalidatePromoSilently() {
    if (!activePromo || !activePromo.code) {
      return;
    }
    const res = await window.Pasaryo.apiRequest('/api/promo-codes/validate/', {
      method: 'POST',
      body: { code: activePromo.code },
    });
    if (res.ok && res.data && res.data.data) {
      activePromo = res.data.data;
      promoActiveTextEl.textContent =
        'Kode ' +
        activePromo.code +
        ' aktif (-' +
        window.Pasaryo.formatRupiah(activePromo.discount_amount) +
        ')';
      promoBannerEl.hidden = false;
    } else {
      activePromo = null;
      promoBannerEl.hidden = true;
    }
  }

  function renderAddressOptions() {
    addressSelect.innerHTML = '';
    if (addresses.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'Belum ada alamat tersimpan';
      addressSelect.appendChild(opt);
      addressPreview.innerHTML =
        'Anda belum memiliki alamat pengiriman. <a href="/akun/#alamat" style="color: var(--accent-primary); font-weight: 700;">Tambah alamat baru di halaman Akun</a>.';
      return;
    }

    addresses.forEach(function (addr) {
      const opt = document.createElement('option');
      opt.value = String(addr.id);
      opt.textContent =
        addr.label +
        (addr.is_main ? ' (Utama)' : '') +
        ' - ' +
        addr.recipient_name +
        ', ' +
        addr.city;
      if (addr.is_main) {
        opt.selected = true;
      }
      addressSelect.appendChild(opt);
    });

    updateAddressPreview();
  }

  function updateAddressPreview() {
    const selectedId = Number(addressSelect.value);
    const addr = addresses.find(function (a) {
      return Number(a.id) === selectedId;
    });
    if (!addr) {
      addressPreview.textContent = '';
      return;
    }
    addressPreview.textContent =
      addr.recipient_name +
      ' (' +
      addr.recipient_phone +
      ') - ' +
      addr.street_address +
      ', ' +
      addr.subdistrict +
      ', ' +
      addr.city +
      ', ' +
      addr.province +
      ' ' +
      addr.postal_code;
  }

  function renderShippingMethods() {
    shippingListEl.innerHTML = '';
    if (shippingMethods.length === 0) {
      shippingListEl.innerHTML =
        '<p class="text-muted">Belum ada metode pengiriman aktif yang tersedia.</p>';
      return;
    }

    shippingMethods.forEach(function (method, idx) {
      const idAttr = 'ship-method-' + method.id;
      const label = document.createElement('label');
      label.className = 'choice-label';
      label.setAttribute('for', idAttr);
      label.innerHTML =
        '<span class="choice-left">' +
        '<input type="radio" id="' +
        idAttr +
        '" name="shipping_method_id" value="' +
        method.id +
        '" ' +
        (idx === 0 ? 'checked' : '') +
        '>' +
        '<span>' +
        '<strong style="display: block;">' +
        window.Pasaryo.escapeHtml(method.name) +
        '</strong>' +
        '<span class="text-muted">Estimasi tiba: ' +
        window.Pasaryo.escapeHtml(method.estimated_days || '2-4 hari') +
        '</span>' +
        '</span>' +
        '</span>' +
        '<strong class="mono-num">' +
        window.Pasaryo.formatRupiah(method.base_cost) +
        '</strong>';

      label.querySelector('input').addEventListener('change', updateSummaryNumbers);
      shippingListEl.appendChild(label);
    });
  }

  function renderPaymentMethods() {
    paymentListEl.innerHTML = '';
    if (paymentMethods.length === 0) {
      paymentListEl.innerHTML =
        '<p class="text-muted">Belum ada metode pembayaran aktif yang tersedia.</p>';
      return;
    }

    paymentMethods.forEach(function (method, idx) {
      const idAttr = 'pay-method-' + method.id;
      const label = document.createElement('label');
      label.className = 'choice-label';
      label.setAttribute('for', idAttr);
      label.innerHTML =
        '<span class="choice-left">' +
        '<input type="radio" id="' +
        idAttr +
        '" name="payment_method_id" value="' +
        method.id +
        '" ' +
        (idx === 0 ? 'checked' : '') +
        '>' +
        '<span>' +
        '<strong style="display: block;">' +
        window.Pasaryo.escapeHtml(method.name) +
        '</strong>' +
        '<span class="text-muted">Penyedia: ' +
        window.Pasaryo.escapeHtml(method.channel_provider || 'Transfer / Virtual Account') +
        '</span>' +
        '</span>' +
        '</span>' +
        '<span class="mono-num text-secondary">Biaya: ' +
        window.Pasaryo.formatRupiah(method.service_fee) +
        '</span>';

      label.querySelector('input').addEventListener('change', updateSummaryNumbers);
      paymentListEl.appendChild(label);
    });
  }

  function renderCartView() {
    if (!cartState.items || cartState.items.length === 0) {
      workspaceEl.hidden = true;
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    workspaceEl.hidden = false;
    renderCartItems();
    updateSummaryNumbers();
  }

  async function refreshCartOnly() {
    const res = await window.Pasaryo.apiRequest('/api/cart/');
    if (res.ok && res.data && res.data.data) {
      cartState = res.data.data;
      renderCartView();
    }
  }

  async function loadAllCartData() {
    loadingEl.hidden = false;
    authReqEl.hidden = true;
    errorEl.hidden = true;
    emptyEl.hidden = true;
    workspaceEl.hidden = true;

    const cartRes = await window.Pasaryo.apiRequest('/api/cart/');
    if (cartRes.status === 401) {
      loadingEl.hidden = true;
      authReqEl.hidden = false;
      return;
    }
    if (!cartRes.ok || !cartRes.data || !cartRes.data.data) {
      loadingEl.hidden = true;
      errorMsgEl.textContent =
        (cartRes.data && cartRes.data.message) || 'Gagal memuat keranjang belanja.';
      errorEl.hidden = false;
      return;
    }

    cartState = cartRes.data.data;
    if (!cartState.items || cartState.items.length === 0) {
      loadingEl.hidden = true;
      emptyEl.hidden = false;
      return;
    }

    const [addrRes, shipRes, payRes] = await Promise.all([
      window.Pasaryo.apiRequest('/accounts/addresses/'),
      window.Pasaryo.apiRequest('/api/shipping-methods/'),
      window.Pasaryo.apiRequest('/api/payment-methods/'),
    ]);

    loadingEl.hidden = true;

    addresses =
      addrRes.ok && addrRes.data && Array.isArray(addrRes.data.results)
        ? addrRes.data.results
        : [];
    shippingMethods =
      shipRes.ok && shipRes.data && Array.isArray(shipRes.data.data)
        ? shipRes.data.data
        : [];
    paymentMethods =
      payRes.ok && payRes.data && Array.isArray(payRes.data.data)
        ? payRes.data.data
        : [];

    renderAddressOptions();
    renderShippingMethods();
    renderPaymentMethods();
    renderCartView();
  }

  if (addressSelect) {
    addressSelect.addEventListener('change', updateAddressPreview);
  }

  if (promoForm) {
    window.Pasaryo.bindLiveErrorClear(promoForm);
    promoForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(promoForm);
      const code = String(promoInput.value || '').trim();
      if (!code) {
        window.Pasaryo.setFieldError(promoForm, 'code', 'Masukkan kode promo terlebih dahulu.');
        return;
      }

      window.Pasaryo.setButtonBusy(promoApplyBtn, true, 'Memeriksa...');
      const res = await window.Pasaryo.apiRequest('/api/promo-codes/validate/', {
        method: 'POST',
        body: { code: code },
      });
      window.Pasaryo.setButtonBusy(promoApplyBtn, false);

      if (!res.ok || !res.data || !res.data.data) {
        window.Pasaryo.setFieldError(
          promoForm,
          'code',
          (res.data && res.data.message) || 'Kode promo tidak valid atau tidak memenuhi syarat.'
        );
        return;
      }

      activePromo = res.data.data;
      checkoutKey = generateCheckoutKey();
      promoActiveTextEl.textContent =
        'Kode ' +
        activePromo.code +
        ' diterapkan (-' +
        window.Pasaryo.formatRupiah(activePromo.discount_amount) +
        ')';
      promoBannerEl.hidden = false;
      updateSummaryNumbers();
      window.Pasaryo.showToast('Kode promo berhasil diterapkan.', 'success');
    });
  }

  if (promoClearBtn) {
    promoClearBtn.addEventListener('click', function () {
      activePromo = null;
      promoInput.value = '';
      promoBannerEl.hidden = true;
      checkoutKey = generateCheckoutKey();
      updateSummaryNumbers();
    });
  }

  if (checkoutForm) {
    window.Pasaryo.bindLiveErrorClear(checkoutForm);
    checkoutForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(checkoutForm);

      const addressId = Number(addressSelect.value);
      const shipRadio = shippingListEl.querySelector('input[name="shipping_method_id"]:checked');
      const payRadio = paymentListEl.querySelector('input[name="payment_method_id"]:checked');

      if (!addressId) {
        window.Pasaryo.setFieldError(
          checkoutForm,
          'address_id',
          'Pilih atau tambahkan alamat pengiriman terlebih dahulu.'
        );
        return;
      }
      if (!shipRadio) {
        window.Pasaryo.setFieldError(
          checkoutForm,
          'shipping_method_id',
          'Pilih metode pengiriman.'
        );
        return;
      }
      if (!payRadio) {
        window.Pasaryo.setFieldError(
          checkoutForm,
          'payment_method_id',
          'Pilih metode pembayaran.'
        );
        return;
      }

      const payload = {
        checkout_key: checkoutKey,
        address_id: addressId,
        shipping_method_id: Number(shipRadio.value),
        payment_method_id: Number(payRadio.value),
      };
      if (activePromo && activePromo.code) {
        payload.promo_code = activePromo.code;
      }

      window.Pasaryo.setButtonBusy(checkoutSubmitBtn, true, 'Memproses Pesanan...');
      const res = await window.Pasaryo.apiRequest('/api/checkout/', {
        method: 'POST',
        body: payload,
      });
      window.Pasaryo.setButtonBusy(checkoutSubmitBtn, false);

      if (!res.ok || !res.data || !res.data.data) {
        window.Pasaryo.applyFormErrors(
          checkoutForm,
          res.data,
          (res.data && res.data.message) || 'Checkout gagal diproses.'
        );
        return;
      }

      const order = res.data.data;
      await window.Pasaryo.refreshCartBadge();
      window.Pasaryo.showToast('Pesanan ' + order.order_number + ' berhasil dibuat.', 'success');
      window.location.href = '/pesanan/' + encodeURIComponent(order.id) + '/';
    });
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', loadAllCartData);
  }

  document.addEventListener('DOMContentLoaded', loadAllCartData);
})();

