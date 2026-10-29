(function () {
  'use strict';

  const root = document.getElementById('order-detail-root');
  const orderId = Number((root && root.dataset.orderId) || 0);

  const loadingEl = document.getElementById('order-detail-loading');
  const authEl = document.getElementById('order-detail-auth');
  const errorEl = document.getElementById('order-detail-error');
  const errorMsgEl = document.getElementById('order-detail-error-msg');
  const retryBtn = document.getElementById('order-detail-retry-btn');
  const contentEl = document.getElementById('order-detail-content');

  const statusBadgeEl = document.getElementById('order-status-badge');
  const createdTextEl = document.getElementById('order-created-text');
  const orderNumberHeading = document.getElementById('order-number-heading');
  const completeBtn = document.getElementById('order-complete-btn');
  const cancelBtn = document.getElementById('order-cancel-btn');

  const reviewHintEl = document.getElementById('order-review-hint');
  const itemsBoxEl = document.getElementById('order-items-box');
  const shippingSnapshotBox = document.getElementById('shipping-snapshot-box');
  const refreshTrackingBtn = document.getElementById('refresh-tracking-btn');
  const trackingEmptyEl = document.getElementById('tracking-empty');
  const trackingTimelineEl = document.getElementById('tracking-timeline');

  const paymentInfoBox = document.getElementById('payment-info-box');
  const repaymentForm = document.getElementById('repayment-form');
  const repaymentSelect = document.getElementById('repayment-method-select');
  const repaymentSubmitBtn = document.getElementById('repayment-submit-btn');

  const summaryCourierEl = document.getElementById('order-summary-courier');
  const summarySubtotalEl = document.getElementById('order-summary-subtotal');
  const summaryShippingEl = document.getElementById('order-summary-shipping');
  const summaryServiceEl = document.getElementById('order-summary-service');
  const summaryDiscountRow = document.getElementById('order-summary-discount-row');
  const summaryDiscountEl = document.getElementById('order-summary-discount');
  const summaryTotalEl = document.getElementById('order-summary-total');

  let currentOrder = null;
  let existingReviewsByItem = {};
  let paymentMethods = [];

  function normalizeStatus(status) {
    return String(status || '').toLowerCase();
  }

  function setOrderStatusBadge(status) {
    const key = normalizeStatus(status);
    const map = {
      to_pay: { label: 'Menunggu Pembayaran', cls: 'badge badge-warning' },
      pending_payment: { label: 'Menunggu Pembayaran', cls: 'badge badge-warning' },
      paid: { label: 'Sudah Dibayar', cls: 'badge badge-success' },
      processing: { label: 'Sedang Diproses', cls: 'badge badge-accent' },
      shipped: { label: 'Dalam Pengiriman', cls: 'badge badge-warning' },
      delivered: { label: 'Tiba di Tujuan', cls: 'badge badge-success' },
      completed: { label: 'Pesanan Selesai', cls: 'badge badge-success' },
      cancelled: { label: 'Dibatalkan', cls: 'badge badge-danger' },
    };
    const info = map[key] || { label: status, cls: 'badge badge-neutral' };
    statusBadgeEl.className = info.cls;
    statusBadgeEl.textContent = info.label;
  }

  function renderShippingSnapshot(order) {
    let snap = order.shipping_address_snapshot;
    const estFrom = order.estimated_delivery_from
      ? window.Pasaryo.formatDateOnly(order.estimated_delivery_from)
      : null;
    const estTo = order.estimated_delivery_to
      ? window.Pasaryo.formatDateOnly(order.estimated_delivery_to)
      : null;
    const estLine =
      estFrom && estTo ? 'Estimasi tiba: ' + estFrom + ' s/d ' + estTo : 'Estimasi mengikuti kurir';

    if (typeof snap === 'string') {
      try {
        const parsed = JSON.parse(snap);
        if (parsed && typeof parsed === 'object') {
          snap = parsed;
        }
      } catch (_err) {
        shippingSnapshotBox.innerHTML =
          '<p class="text-secondary" style="margin-bottom: 4px; white-space: pre-line;">' +
          window.Pasaryo.escapeHtml(snap) +
          '</p>' +
          '<span class="text-muted mono-num">' +
          window.Pasaryo.escapeHtml(estLine) +
          '</span>';
        return;
      }
    }

    snap = snap || {};
    shippingSnapshotBox.innerHTML =
      '<strong style="display: block; margin-bottom: 4px;">Penerima: ' +
      window.Pasaryo.escapeHtml(snap.recipient_name || '-') +
      ' (' +
      window.Pasaryo.escapeHtml(snap.recipient_phone || '-') +
      ')</strong>' +
      '<p class="text-secondary" style="margin-bottom: 4px;">' +
      window.Pasaryo.escapeHtml(snap.street_address || '') +
      ', ' +
      window.Pasaryo.escapeHtml(snap.subdistrict || '') +
      ', ' +
      window.Pasaryo.escapeHtml(snap.city || '') +
      ', ' +
      window.Pasaryo.escapeHtml(snap.province || '') +
      ' ' +
      window.Pasaryo.escapeHtml(snap.postal_code || '') +
      '</p>' +
      '<span class="text-muted mono-num">' +
      window.Pasaryo.escapeHtml(estLine) +
      '</span>';
  }

  function renderTrackingEvents(events) {
    trackingTimelineEl.innerHTML = '';
    if (!Array.isArray(events) || events.length === 0) {
      trackingEmptyEl.hidden = false;
      return;
    }
    trackingEmptyEl.hidden = true;

    events.forEach(function (ev) {
      const li = document.createElement('li');
      li.className = 'timeline-step' + (ev.is_completed ? ' is-completed' : '');
      const timeLabel = ev.event_time
        ? window.Pasaryo.formatDateTime(ev.event_time)
        : ev.expected_time
          ? 'Estimasi: ' + window.Pasaryo.formatDateTime(ev.expected_time)
          : '';
      li.innerHTML =
        '<span class="timeline-dot" aria-hidden="true"></span>' +
        '<div style="display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap;">' +
        '<strong>' +
        window.Pasaryo.escapeHtml(ev.status_code) +
        '</strong>' +
        '<span class="text-muted mono-num">' +
        window.Pasaryo.escapeHtml(timeLabel) +
        '</span>' +
        '</div>' +
        '<p class="text-secondary" style="margin-bottom: 0;">' +
        window.Pasaryo.escapeHtml(ev.description || '') +
        '</p>';
      trackingTimelineEl.appendChild(li);
    });
  }

  function renderPaymentSection(order) {
    const p = order.payment;
    if (!p) {
      paymentInfoBox.innerHTML =
        '<strong>Belum Ada Tagihan Pembayaran</strong>' +
        '<p class="text-muted" style="margin-bottom: 0;">Pilih metode pembayaran di bawah untuk menerbitkan kode referensi pembayaran.</p>';
    } else {
      const statusMap = {
        PENDING: { label: 'Menunggu Pembayaran', cls: 'badge-warning' },
        SUCCESS: { label: 'Lunas', cls: 'badge-success' },
        FAILED: { label: 'Gagal', cls: 'badge-danger' },
        EXPIRED: { label: 'Kedaluwarsa', cls: 'badge-danger' },
      };
      const st = statusMap[p.payment_status] || { label: p.payment_status, cls: 'badge-neutral' };
      paymentInfoBox.innerHTML =
        '<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">' +
        '<strong>' +
        window.Pasaryo.escapeHtml(p.payment_method) +
        '</strong>' +
        '<span class="badge ' +
        st.cls +
        '">' +
        window.Pasaryo.escapeHtml(st.label) +
        '</span>' +
        '</div>' +
        '<p class="text-muted mono-num" style="margin-bottom: 4px;">Referensi: ' +
        window.Pasaryo.escapeHtml(p.payment_reference || '-') +
        '</p>' +
        '<p class="text-muted mono-num" style="margin-bottom: 0;">Batas Bayar: ' +
        window.Pasaryo.escapeHtml(
          window.Pasaryo.formatDateTime(p.expires_at || order.payment_due_at)
        ) +
        '</p>';
    }

    const normStatus = normalizeStatus(order.status);
    const canCreatePayment =
      (normStatus === 'to_pay' || normStatus === 'pending_payment') &&
      (!p || p.payment_status !== 'SUCCESS') &&
      paymentMethods.length > 0;

    repaymentForm.hidden = !canCreatePayment;
    if (canCreatePayment) {
      repaymentSelect.innerHTML = '';
      paymentMethods.forEach(function (m) {
        const opt = document.createElement('option');
        opt.value = String(m.id);
        opt.textContent = m.name + ' (Biaya: ' + window.Pasaryo.formatRupiah(m.service_fee) + ')';
        repaymentSelect.appendChild(opt);
      });
    }
  }

  function renderOrderItems(order) {
    itemsBoxEl.innerHTML = '';
    const isCompleted = normalizeStatus(order.status) === 'completed';
    reviewHintEl.hidden = !isCompleted;

    const items = Array.isArray(order.items) ? order.items : [];
    items.forEach(function (item) {
      const box = document.createElement('article');
      box.className = 'record-item';
      box.style.flexDirection = 'column';
      box.style.alignItems = 'stretch';

      const topRow = document.createElement('div');
      topRow.style.display = 'flex';
      topRow.style.flexWrap = 'wrap';
      topRow.style.justifyContent = 'space-between';
      topRow.style.gap = '12px';
      topRow.innerHTML =
        '<div>' +
        '<h3 style="margin-bottom: 4px;">' +
        window.Pasaryo.escapeHtml(item.product_name) +
        '</h3>' +
        '<p class="text-muted mono-num" style="margin-bottom: 0;">Varian: ' +
        window.Pasaryo.escapeHtml(item.variant_name) +
        ' &middot; SKU: ' +
        window.Pasaryo.escapeHtml(item.sku) +
        ' &middot; ' +
        item.quantity +
        ' x ' +
        window.Pasaryo.formatRupiah(item.unit_price) +
        '</p>' +
        '</div>' +
        '<strong class="mono-num" style="font-size: 1.05rem;">' +
        window.Pasaryo.formatRupiah(item.line_total) +
        '</strong>';

      box.appendChild(topRow);

      const existingReview = existingReviewsByItem[String(item.id)];
      if (existingReview) {
        const revBox = document.createElement('div');
        revBox.className = 'panel-subtle';
        revBox.style.marginTop = '12px';
        revBox.innerHTML =
          '<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px;">' +
          '<strong>Ulasan Anda</strong>' +
          '<span class="badge badge-success mono-num">Rating ' +
          window.Pasaryo.escapeHtml(existingReview.rating) +
          ' / 5</span>' +
          '</div>' +
          '<p style="margin-bottom: 0;">' +
          window.Pasaryo.escapeHtml(
            existingReview.comment || 'Anda memberikan rating tanpa komentar tertulis.'
          ) +
          '</p>';
        box.appendChild(revBox);
      } else if (isCompleted) {
        const revForm = document.createElement('form');
        revForm.className = 'panel-subtle';
        revForm.style.marginTop = '12px';
        revForm.noValidate = true;

        const ratingSelectId = 'review-rating-' + item.id;
        const commentInputId = 'review-comment-' + item.id;

        revForm.innerHTML =
          '<div class="field-error" data-form-alert role="alert" style="margin-bottom: 8px;" hidden></div>' +
          '<div class="form-row">' +
          '<div class="form-group" style="margin-bottom: 8px;">' +
          '<label for="' +
          ratingSelectId +
          '" class="form-label">Rating Produk (1 sampai 5)</label>' +
          '<select id="' +
          ratingSelectId +
          '" name="rating" class="form-control">' +
          '<option value="5">5 - Sangat Memuaskan</option>' +
          '<option value="4">4 - Sesuai Deskripsi</option>' +
          '<option value="3">3 - Cukup Baik</option>' +
          '<option value="2">2 - Kurang Sesuai</option>' +
          '<option value="1">1 - Tidak Sesuai</option>' +
          '</select>' +
          '<div class="field-error" data-error-for="rating" role="alert" hidden></div>' +
          '</div>' +
          '<div class="form-group" style="margin-bottom: 8px;">' +
          '<label for="' +
          commentInputId +
          '" class="form-label">Ulasan Tertulis</label>' +
          '<input type="text" id="' +
          commentInputId +
          '" name="comment" class="form-control" placeholder="Bagikan pengalaman kualitas produk ini..." maxlength="1000">' +
          '<div class="field-error" data-error-for="comment" role="alert" hidden></div>' +
          '</div>' +
          '</div>' +
          '<button type="submit" class="btn btn-primary btn-sm">Kirim Ulasan Produk</button>';

        window.Pasaryo.bindLiveErrorClear(revForm);
        revForm.addEventListener('submit', function (event) {
          event.preventDefault();
          handleSubmitReview(item.id, revForm);
        });

        box.appendChild(revForm);
      }

      itemsBoxEl.appendChild(box);
    });
  }

  async function handleSubmitReview(orderItemId, formEl) {
    window.Pasaryo.clearFormErrors(formEl);
    const submitBtn = formEl.querySelector('button[type="submit"]');
    const ratingVal = Number(formEl.elements.rating.value);
    const commentVal = String(formEl.elements.comment.value || '').trim();

    if (!Number.isInteger(ratingVal) || ratingVal < 1 || ratingVal > 5) {
      window.Pasaryo.setFieldError(formEl, 'rating', 'Pilih rating antara 1 sampai 5.');
      return;
    }

    window.Pasaryo.setButtonBusy(submitBtn, true, 'Mengirim Ulasan...');
    const res = await window.Pasaryo.apiRequest('/reviews/', {
      method: 'POST',
      body: {
        order_item_id: Number(orderItemId),
        rating: ratingVal,
        comment: commentVal,
      },
    });
    window.Pasaryo.setButtonBusy(submitBtn, false);

    if (!res.ok) {
      window.Pasaryo.applyFormErrors(
        formEl,
        res.data,
        (res.data && res.data.message) || 'Gagal menyimpan ulasan produk.'
      );
      return;
    }

    if (res.data && res.data.review) {
      existingReviewsByItem[String(orderItemId)] = res.data.review;
    }
    window.Pasaryo.showToast('Ulasan produk berhasil disimpan.', 'success');
    renderOrderItems(currentOrder);
  }

  function renderOrderView(order) {
    currentOrder = order;
    document.title = 'Pesanan ' + order.order_number + ' | Pasaryo';
    orderNumberHeading.textContent = order.order_number;
    createdTextEl.textContent = 'Dibuat ' + window.Pasaryo.formatDateTime(order.created_at);
    setOrderStatusBadge(order.status);

    const normStatus = normalizeStatus(order.status);
    completeBtn.hidden = !(normStatus === 'shipped' || normStatus === 'delivered');
    cancelBtn.hidden = !(normStatus === 'to_pay' || normStatus === 'pending_payment');

    summaryCourierEl.textContent = order.shipping_method || '-';
    summarySubtotalEl.textContent = window.Pasaryo.formatRupiah(order.subtotal);
    summaryShippingEl.textContent = window.Pasaryo.formatRupiah(order.shipping_fee);
    summaryServiceEl.textContent = window.Pasaryo.formatRupiah(order.service_fee);

    const discount = Number(order.discount_amount || 0);
    if (discount > 0) {
      summaryDiscountEl.textContent = '-' + window.Pasaryo.formatRupiah(discount);
      summaryDiscountRow.hidden = false;
    } else {
      summaryDiscountRow.hidden = true;
    }
    summaryTotalEl.textContent = window.Pasaryo.formatRupiah(order.total_amount);

    renderShippingSnapshot(order);
    renderTrackingEvents(order.tracking || []);
    renderPaymentSection(order);
    renderOrderItems(order);
  }

  async function loadOrderDetail() {
    loadingEl.hidden = false;
    authEl.hidden = true;
    errorEl.hidden = true;
    contentEl.hidden = true;

    const [orderRes, payMethodsRes, reviewsRes] = await Promise.all([
      window.Pasaryo.apiRequest('/api/orders/' + encodeURIComponent(orderId) + '/'),
      window.Pasaryo.apiRequest('/api/payment-methods/'),
      window.Pasaryo.apiRequest('/frontend-api/orders/' + encodeURIComponent(orderId) + '/reviews/'),
    ]);

    loadingEl.hidden = true;

    if (orderRes.status === 401) {
      authEl.hidden = false;
      return;
    }

    if (!orderRes.ok || !orderRes.data || !orderRes.data.data) {
      errorMsgEl.textContent =
        (orderRes.data && orderRes.data.message) || 'Pesanan tidak ditemukan.';
      errorEl.hidden = false;
      return;
    }

    paymentMethods =
      payMethodsRes.ok && payMethodsRes.data && Array.isArray(payMethodsRes.data.data)
        ? payMethodsRes.data.data
        : [];
    existingReviewsByItem =
      reviewsRes.ok && reviewsRes.data && reviewsRes.data.reviews_by_item
        ? reviewsRes.data.reviews_by_item
        : {};

    renderOrderView(orderRes.data.data);
    contentEl.hidden = false;
  }

  if (refreshTrackingBtn) {
    refreshTrackingBtn.addEventListener('click', async function () {
      window.Pasaryo.setButtonBusy(refreshTrackingBtn, true, 'Memperbarui...');
      const res = await window.Pasaryo.apiRequest(
        '/api/orders/' + encodeURIComponent(orderId) + '/tracking/'
      );
      window.Pasaryo.setButtonBusy(refreshTrackingBtn, false);

      if (!res.ok || !res.data || !res.data.data) {
        window.Pasaryo.showToast(
          (res.data && res.data.message) || 'Gagal memperbarui pelacakan.',
          'error'
        );
        return;
      }

      const trackData = res.data.data;
      setOrderStatusBadge(trackData.order_status);
      renderTrackingEvents(trackData.tracking || []);
      window.Pasaryo.showToast('Status pelacakan berhasil diperbarui.', 'success');
    });
  }

  if (repaymentForm) {
    window.Pasaryo.bindLiveErrorClear(repaymentForm);
    repaymentForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(repaymentForm);

      const methodId = Number(repaymentSelect.value);
      if (!methodId) {
        window.Pasaryo.setFieldError(
          repaymentForm,
          'payment_method_id',
          'Pilih metode pembayaran terlebih dahulu.'
        );
        return;
      }

      window.Pasaryo.setButtonBusy(repaymentSubmitBtn, true, 'Membuat Tagihan...');
      const res = await window.Pasaryo.apiRequest(
        '/api/orders/' + encodeURIComponent(orderId) + '/payments/',
        {
          method: 'POST',
          body: { payment_method_id: methodId },
        }
      );
      window.Pasaryo.setButtonBusy(repaymentSubmitBtn, false);

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          repaymentForm,
          res.data,
          (res.data && res.data.message) || 'Gagal membuat tagihan pembayaran.'
        );
        return;
      }

      window.Pasaryo.showToast('Tagihan pembayaran baru berhasil diterbitkan.', 'success');
      await loadOrderDetail();
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', async function () {
      const confirmed = await window.Pasaryo.confirmAction({
        title: 'Batalkan Pesanan Ini',
        description:
          'Apakah Anda yakin ingin membatalkan pesanan ' +
          (currentOrder ? currentOrder.order_number : '') +
          '? Stok barang akan dikembalikan dan pesanan tidak dapat dilanjutkan.',
        confirmLabel: 'Ya, Batalkan Pesanan',
        cancelLabel: 'Kembali',
      });
      if (!confirmed) {
        return;
      }

      window.Pasaryo.setButtonBusy(cancelBtn, true, 'Membatalkan...');
      const res = await window.Pasaryo.apiRequest(
        '/api/orders/' + encodeURIComponent(orderId) + '/cancel/',
        { method: 'POST' }
      );
      window.Pasaryo.setButtonBusy(cancelBtn, false);

      if (!res.ok) {
        window.Pasaryo.showToast(
          (res.data && res.data.message) || 'Pesanan tidak dapat dibatalkan.',
          'error'
        );
        return;
      }

      window.Pasaryo.showToast(res.data.message || 'Pesanan berhasil dibatalkan.', 'success');
      await loadOrderDetail();
    });
  }

  if (completeBtn) {
    completeBtn.addEventListener('click', async function () {
      const confirmed = await window.Pasaryo.confirmAction({
        title: 'Konfirmasi Penerimaan Barang',
        description:
          'Pastikan barang telah diterima dalam kondisi baik. Setelah dikonfirmasi, pesanan dinyatakan selesai.',
        confirmLabel: 'Ya, Barang Sudah Diterima',
        cancelLabel: 'Batal',
      });
      if (!confirmed) {
        return;
      }

      window.Pasaryo.setButtonBusy(completeBtn, true, 'Mengonfirmasi...');
      const res = await window.Pasaryo.apiRequest(
        '/api/orders/' + encodeURIComponent(orderId) + '/complete/',
        { method: 'POST' }
      );
      window.Pasaryo.setButtonBusy(completeBtn, false);

      if (!res.ok) {
        window.Pasaryo.showToast(
          (res.data && res.data.message) || 'Gagal mengonfirmasi penerimaan pesanan.',
          'error'
        );
        return;
      }

      window.Pasaryo.showToast(
        res.data.message || 'Pesanan dikonfirmasi selesai. Silakan tulis ulasan Anda.',
        'success'
      );
      await loadOrderDetail();
    });
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', loadOrderDetail);
  }

  document.addEventListener('DOMContentLoaded', loadOrderDetail);
})();

