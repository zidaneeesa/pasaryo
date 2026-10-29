(function () {
  'use strict';

  const form = document.getElementById('catalog-filter-form');
  const categorySelect = document.getElementById('filter-category');
  const brandSelect = document.getElementById('filter-brand');
  const resetBtn = document.getElementById('filter-reset-btn');
  const emptyResetBtn = document.getElementById('catalog-empty-reset-btn');
  const retryBtn = document.getElementById('catalog-retry-btn');

  const countLabel = document.getElementById('catalog-count-label');
  const loadingEl = document.getElementById('catalog-loading');
  const errorEl = document.getElementById('catalog-error');
  const errorMsgEl = document.getElementById('catalog-error-msg');
  const emptyEl = document.getElementById('catalog-empty');
  const gridEl = document.getElementById('catalog-grid');

  const paginationEl = document.getElementById('catalog-pagination');
  const paginationInfoEl = document.getElementById('pagination-info');
  const prevBtn = document.getElementById('page-prev-btn');
  const nextBtn = document.getElementById('page-next-btn');

  let currentPage = 1;
  const pageSize = 12;

  async function loadTaxonomy() {
    const [catRes, brandRes] = await Promise.all([
      window.Pasaryo.apiRequest('/catalog/categories/'),
      window.Pasaryo.apiRequest('/catalog/brands/'),
    ]);

    if (catRes.ok && catRes.data && Array.isArray(catRes.data.results)) {
      catRes.data.results.forEach(function (cat) {
        const opt = document.createElement('option');
        opt.value = String(cat.id);
        opt.textContent = cat.name;
        categorySelect.appendChild(opt);
      });
    }

    if (brandRes.ok && brandRes.data && Array.isArray(brandRes.data.results)) {
      brandRes.data.results.forEach(function (brand) {
        const opt = document.createElement('option');
        opt.value = String(brand.id);
        opt.textContent = brand.name;
        brandSelect.appendChild(opt);
      });
    }
  }

  function buildQueryParams(page) {
    const params = new URLSearchParams();
    const formData = new FormData(form);
    ['q', 'category_id', 'brand_id', 'min_price', 'max_price', 'origin_city', 'sort'].forEach(function (key) {
      const val = String(formData.get(key) || '').trim();
      if (val) {
        params.set(key, val);
      }
    });
    params.set('page', String(page));
    params.set('page_size', String(pageSize));
    return params;
  }

  function renderProductCard(product, index) {
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
      '<button type="button" class="btn btn-secondary btn-sm" data-wishlist-add="' +
      window.Pasaryo.escapeHtml(product.id) +
      '">Simpan Wishlist</button>' +
      '</div>';

    const wishBtn = card.querySelector('[data-wishlist-add]');
    if (wishBtn) {
      wishBtn.addEventListener('click', function () {
        handleAddWishlist(Number(product.id), wishBtn);
      });
    }

    return card;
  }

  async function handleAddWishlist(productId, buttonEl) {
    window.Pasaryo.setButtonBusy(buttonEl, true, 'Menyimpan...');
    const res = await window.Pasaryo.apiRequest('/wishlist/', {
      method: 'POST',
      body: { product_id: productId },
    });
    window.Pasaryo.setButtonBusy(buttonEl, false);

    if (res.status === 401) {
      window.Pasaryo.showToast('Silakan masuk ke akun terlebih dahulu untuk menyimpan wishlist.', 'error');
      return;
    }

    if (!res.ok) {
      window.Pasaryo.showToast(
        (res.data && res.data.message) || 'Gagal menyimpan produk ke wishlist.',
        'error'
      );
      return;
    }

    buttonEl.textContent = 'Tersimpan';
    buttonEl.dataset.originalLabel = 'Tersimpan';
    window.Pasaryo.showToast(res.data.message || 'Produk disimpan ke wishlist.', 'success');
  }

  async function loadProducts(page) {
    window.Pasaryo.clearFormErrors(form);

    const minVal = form.elements.min_price.value.trim();
    const maxVal = form.elements.max_price.value.trim();
    if (minVal && maxVal && Number(minVal) > Number(maxVal)) {
      window.Pasaryo.setFieldError(
        form,
        'min_price',
        'Harga minimum tidak boleh melebihi harga maksimum.'
      );
      return;
    }

    currentPage = page || 1;
    loadingEl.hidden = false;
    errorEl.hidden = true;
    emptyEl.hidden = true;
    gridEl.hidden = true;
    paginationEl.hidden = true;

    const query = buildQueryParams(currentPage);
    const res = await window.Pasaryo.apiRequest('/catalog/products/?' + query.toString());

    loadingEl.hidden = true;

    if (!res.ok) {
      if (res.status === 400 && res.data && res.data.errors) {
        window.Pasaryo.applyFormErrors(form, res.data, 'Filter pencarian tidak valid.');
      }
      errorMsgEl.textContent =
        (res.data && res.data.message) ||
        'Gagal memuat daftar produk. Periksa filter harga atau koneksi Anda.';
      errorEl.hidden = false;
      countLabel.textContent = '0 produk';
      return;
    }

    const payload = res.data || {};
    const items = Array.isArray(payload.results) ? payload.results : [];
    const totalCount = Number(payload.count || 0);
    const totalPages = Number(payload.total_pages || 1);

    countLabel.textContent = 'Menampilkan ' + items.length + ' dari ' + totalCount + ' produk';

    if (items.length === 0) {
      emptyEl.hidden = false;
      return;
    }

    gridEl.innerHTML = '';
    items.forEach(function (item, idx) {
      gridEl.appendChild(renderProductCard(item, idx));
    });
    gridEl.hidden = false;

    paginationInfoEl.textContent = 'Halaman ' + payload.page + ' dari ' + totalPages;
    prevBtn.disabled = payload.page <= 1;
    nextBtn.disabled = payload.page >= totalPages;
    paginationEl.hidden = totalPages <= 1;
  }

  function resetFilters() {
    form.reset();
    window.Pasaryo.clearFormErrors(form);
    loadProducts(1);
  }

  if (form) {
    window.Pasaryo.bindLiveErrorClear(form);
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      loadProducts(1);
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', resetFilters);
  }
  if (emptyResetBtn) {
    emptyResetBtn.addEventListener('click', resetFilters);
  }
  if (retryBtn) {
    retryBtn.addEventListener('click', function () {
      loadProducts(currentPage);
    });
  }
  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (currentPage > 1) {
        loadProducts(currentPage - 1);
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      loadProducts(currentPage + 1);
    });
  }

  document.addEventListener('DOMContentLoaded', async function () {
    await loadTaxonomy();
    await loadProducts(1);
  });
})();

