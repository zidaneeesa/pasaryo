(function () {
  'use strict';

  const loadingEl = document.getElementById('orders-loading');
  const authReqEl = document.getElementById('orders-auth-required');
  const errorEl = document.getElementById('orders-error');
  const errorMsgEl = document.getElementById('orders-error-msg');
  const retryBtn = document.getElementById('orders-retry-btn');
  const emptyEl = document.getElementById('orders-empty');
  const toolbarEl = document.getElementById('orders-toolbar');
  const countLabelEl = document.getElementById('orders-count-label');
  const listEl = document.getElementById('orders-list');
  const paginationEl = document.getElementById('orders-pagination');
  const pageInfoEl = document.getElementById('orders-page-info');
  const prevBtn = document.getElementById('orders-prev-btn');
  const nextBtn = document.getElementById('orders-next-btn');

  let currentPage = 1;

  function statusBadgeHtml(status) {
    const key = String(status || '').toLowerCase();
    const map = {
      to_pay: { label: 'Menunggu Pembayaran', cls: 'badge-warning' },
      pending_payment: { label: 'Menunggu Pembayaran', cls: 'badge-warning' },
      paid: { label: 'Sudah Dibayar', cls: 'badge-success' },
      processing: { label: 'Sedang Diproses', cls: 'badge-accent' },
      shipped: { label: 'Dalam Pengiriman', cls: 'badge-warning' },
      delivered: { label: 'Tiba di Tujuan', cls: 'badge-success' },
      completed: { label: 'Pesanan Selesai', cls: 'badge-success' },
      cancelled: { label: 'Dibatalkan', cls: 'badge-danger' },
    };
    const info = map[key] || { label: status, cls: 'badge-neutral' };
    return '<span class="badge ' + info.cls + '">' + window.Pasaryo.escapeHtml(info.label) + '</span>';
  }

  function paymentBadgeHtml(payment) {
    if (!payment) {
      return '<span class="badge badge-neutral">Belum Ada Tagihan</span>';
    }
    const map = {
      PENDING: { label: 'Tagihan Menunggu (' + payment.payment_method + ')', cls: 'badge-warning' },
      SUCCESS: { label: 'Pembayaran Lunas (' + payment.payment_method + ')', cls: 'badge-success' },
      FAILED: { label: 'Pembayaran Gagal', cls: 'badge-danger' },
      EXPIRED: { label: 'Tagihan Kedaluwarsa', cls: 'badge-danger' },
    };
    const info = map[payment.payment_status] || {
      label: payment.payment_status,
      cls: 'badge-neutral',
    };
    return '<span class="badge ' + info.cls + '">' + window.Pasaryo.escapeHtml(info.label) + '</span>';
  }

  function renderOrderCard(order) {
    const card = document.createElement('article');
    card.className = 'record-item';
    const detailUrl = '/pesanan/' + encodeURIComponent(order.id) + '/';
    const items = Array.isArray(order.items) ? order.items : [];
    const itemsSummary =
      items.length > 0
        ? items
            .map(function (it) {
              return it.product_name + ' (' + it.variant_name + ' x' + it.quantity + ')';
            })
            .join(', ')
        : 'Tidak ada rincian item';

    card.innerHTML =
      '<div class="record-info">' +
      '<div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px;">' +
      '<strong class="mono-num" style="font-size: 1.05rem;">' +
      window.Pasaryo.escapeHtml(order.order_number) +
      '</strong>' +
      statusBadgeHtml(order.status) +
      paymentBadgeHtml(order.payment) +
      '</div>' +
      '<p class="text-muted" style="margin-bottom: 6px;">Dibuat pada ' +
      window.Pasaryo.escapeHtml(window.Pasaryo.formatDateTime(order.created_at)) +
      ' &middot; Kurir: ' +
      window.Pasaryo.escapeHtml(order.shipping_method) +
      '</p>' +
      '<p class="text-secondary" style="margin-bottom: 0;">' +
      window.Pasaryo.escapeHtml(itemsSummary) +
      '</p>' +
      '</div>' +
      '<div class="record-controls">' +
      '<div style="text-align: right; margin-right: 8px;">' +
      '<span class="text-muted" style="display: block; font-size: 0.78rem;">Total Tagihan</span>' +
      '<strong class="mono-num" style="font-size: 1.125rem;">' +
      window.Pasaryo.formatRupiah(order.total_amount) +
      '</strong>' +
      '</div>' +
      '<a href="' +
      detailUrl +
      '" class="btn btn-primary btn-sm">Rincian & Lacak Pesanan</a>' +
      '</div>';

    return card;
  }

  async function loadOrders(page) {
    currentPage = page || 1;
    loadingEl.hidden = false;
    authReqEl.hidden = true;
    errorEl.hidden = true;
    emptyEl.hidden = true;
    toolbarEl.hidden = true;
    listEl.hidden = true;
    paginationEl.hidden = true;

    const res = await window.Pasaryo.apiRequest('/api/orders/?page=' + encodeURIComponent(currentPage));
    loadingEl.hidden = true;

    if (res.status === 401) {
      authReqEl.hidden = false;
      return;
    }

    if (!res.ok || !res.data) {
      errorMsgEl.textContent =
        (res.data && res.data.message) || 'Gagal memuat riwayat pesanan.';
      errorEl.hidden = false;
      return;
    }

    const orders = Array.isArray(res.data.data) ? res.data.data : [];
    const meta = res.data.meta || { page: 1, total: 0, total_pages: 1 };

    if (orders.length === 0) {
      emptyEl.hidden = false;
      return;
    }

    countLabelEl.textContent = 'Total ' + meta.total + ' transaksi tercatat';
    toolbarEl.hidden = false;

    listEl.innerHTML = '';
    orders.forEach(function (order) {
      listEl.appendChild(renderOrderCard(order));
    });
    listEl.hidden = false;

    pageInfoEl.textContent = 'Halaman ' + meta.page + ' dari ' + meta.total_pages;
    prevBtn.disabled = meta.page <= 1;
    nextBtn.disabled = meta.page >= meta.total_pages;
    paginationEl.hidden = meta.total_pages <= 1;
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', function () {
      loadOrders(currentPage);
    });
  }
  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (currentPage > 1) {
        loadOrders(currentPage - 1);
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      loadOrders(currentPage + 1);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    loadOrders(1);
  });
})();

