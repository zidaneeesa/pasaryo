(function () {
  'use strict';

  const loadingEl = document.getElementById('wishlist-loading');
  const authReqEl = document.getElementById('wishlist-auth-required');
  const errorEl = document.getElementById('wishlist-error');
  const errorMsgEl = document.getElementById('wishlist-error-msg');
  const retryBtn = document.getElementById('wishlist-retry-btn');
  const emptyEl = document.getElementById('wishlist-empty');
  const toolbarEl = document.getElementById('wishlist-toolbar');
  const countLabelEl = document.getElementById('wishlist-count-label');
  const gridEl = document.getElementById('wishlist-grid');
  const paginationEl = document.getElementById('wishlist-pagination');
  const pageInfoEl = document.getElementById('wishlist-page-info');
  const prevBtn = document.getElementById('wishlist-prev-btn');
  const nextBtn = document.getElementById('wishlist-next-btn');

  let currentPage = 1;
  const pageSize = 12;

  function renderWishlistCard(item, index) {
    const product = item.product || {};
    const card = document.createElement('article');
    card.className = 'product-card';

    const detailUrl = '/produk/' + encodeURIComponent(product.id) + '/';
    const hasDiscount = Number(product.discount_amount || 0) > 0;
    const categoryName = (product.category && product.category.name) || 'Kategori';
    const brandName = (product.brand && product.brand.name) || 'Brand';
    const originCity = product.origin_city || 'Indonesia';

    let mediaInner = '';
    if (product.image_url) {
      const loadingAttr = index < 3 ? 'fetchpriority="high"' : 'loading="lazy"';
      mediaInner =
        '<img src="' +
        window.Pasaryo.escapeHtml(product.image_url) +
        '" alt="Foto produk ' +
        window.Pasaryo.escapeHtml(product.name) +
        '" width="400" height="300" ' +
        loadingAttr +
        '>';
    } else {
      mediaInner =
        '<div class="product-media-fallback">' +
        '<strong>' +
        window.Pasaryo.escapeHtml(brandName.toUpperCase()) +
        '</strong>' +
        '<span>Foto produk belum diunggah</span>' +
        '</div>';
    }

    const promoBadgeHtml = hasDiscount
      ? '<span class="badge badge-accent product-promo-tag">Hemat ' +
        window.Pasaryo.escapeHtml(product.discount_percentage) +
        '%</span>'
      : '';

    const originalPriceHtml = hasDiscount
      ? '<span class="price-original">' + window.Pasaryo.formatRupiah(product.price) + '</span>'
      : '';

    card.innerHTML =
      '<a href="' +
      detailUrl +
      '" class="product-media">' +
      mediaInner +
      promoBadgeHtml +
      '</a>' +
      '<div class="product-body">' +
      '<div class="product-meta">' +
      window.Pasaryo.escapeHtml(categoryName) +
      ' &middot; ' +
      window.Pasaryo.escapeHtml(brandName) +
      ' &middot; ' +
      window.Pasaryo.escapeHtml(originCity) +
      '</div>' +
      '<h3 class="product-title"><a href="' +
      detailUrl +
      '">' +
      window.Pasaryo.escapeHtml(product.name) +
      '</a></h3>' +
      '<div class="product-pricing">' +
      '<span class="price-final">' +
      window.Pasaryo.formatRupiah(product.final_price) +
      '</span>' +
      originalPriceHtml +
      '</div>' +
      '</div>' +
      '<div class="product-card-actions">' +
      '<a href="' +
      detailUrl +
      '" class="btn btn-primary btn-sm">Pilih Varian</a>' +
      '<button type="button" class="btn btn-danger btn-sm" data-wishlist-remove="' +
      window.Pasaryo.escapeHtml(product.id) +
      '">Hapus</button>' +
      '</div>';

    const removeBtn = card.querySelector('[data-wishlist-remove]');
    if (removeBtn) {
      removeBtn.addEventListener('click', function () {
        handleRemoveWishlist(Number(product.id), product.name, removeBtn);
      });
    }

    return card;
  }

  async function handleRemoveWishlist(productId, productName, buttonEl) {
    const confirmed = await window.Pasaryo.confirmAction({
      title: 'Hapus Produk dari Wishlist',
      description:
        'Apakah Anda yakin ingin menghapus "' +
        (productName || 'produk ini') +
        '" dari daftar wishlist Anda?',
      confirmLabel: 'Ya, Hapus Produk',
      cancelLabel: 'Batal',
    });

    if (!confirmed) {
      return;
    }

    window.Pasaryo.setButtonBusy(buttonEl, true, 'Menghapus...');
    const res = await window.Pasaryo.apiRequest(
      '/wishlist/' + encodeURIComponent(productId) + '/',
      { method: 'DELETE' }
    );
    window.Pasaryo.setButtonBusy(buttonEl, false);

    if (!res.ok) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal menghapus produk dari wishlist.',
        'error'
      );
      return;
    }

    window.Pasaryo.showToast('Produk dihapus dari wishlist.', 'success');
    await loadWishlist(currentPage);
  }

  async function loadWishlist(page) {
    currentPage = page || 1;
    loadingEl.hidden = false;
    authReqEl.hidden = true;
    errorEl.hidden = true;
    emptyEl.hidden = true;
    toolbarEl.hidden = true;
    gridEl.hidden = true;
    paginationEl.hidden = true;

    const params = new URLSearchParams({
      page: String(currentPage),
      page_size: String(pageSize),
    });

    const res = await window.Pasaryo.apiRequest('/wishlist/?' + params.toString());
    loadingEl.hidden = true;

    if (res.status === 401) {
      authReqEl.hidden = false;
      return;
    }

    if (!res.ok) {
      if (res.status === 404 && currentPage > 1) {
        await loadWishlist(currentPage - 1);
        return;
      }
      errorMsgEl.textContent =
        (res.data && res.data.message) || 'Gagal memuat daftar wishlist Anda.';
      errorEl.hidden = false;
      return;
    }

    const payload = res.data || {};
    const results = Array.isArray(payload.results) ? payload.results : [];
    const totalCount = Number(payload.count || 0);
    const totalPages = Number(payload.total_pages || 1);

    if (results.length === 0) {
      emptyEl.hidden = false;
      return;
    }

    countLabelEl.textContent = totalCount + ' produk tersimpan dalam wishlist Anda';
    toolbarEl.hidden = false;

    gridEl.innerHTML = '';
    results.forEach(function (item, idx) {
      gridEl.appendChild(renderWishlistCard(item, idx));
    });
    gridEl.hidden = false;

    pageInfoEl.textContent = 'Halaman ' + payload.page + ' dari ' + totalPages;
    prevBtn.disabled = payload.page <= 1;
    nextBtn.disabled = payload.page >= totalPages;
    paginationEl.hidden = totalPages <= 1;
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', function () {
      loadWishlist(currentPage);
    });
  }
  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (currentPage > 1) {
        loadWishlist(currentPage - 1);
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      loadWishlist(currentPage + 1);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    loadWishlist(1);
  });
})();

