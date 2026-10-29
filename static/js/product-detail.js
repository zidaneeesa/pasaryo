(function () {
  'use strict';

  const root = document.getElementById('product-detail-root');
  const productId = Number((root && root.dataset.productId) || 0);

  const loadingEl = document.getElementById('detail-loading');
  const errorEl = document.getElementById('detail-error');
  const errorMsgEl = document.getElementById('detail-error-msg');
  const retryBtn = document.getElementById('detail-retry-btn');
  const contentEl = document.getElementById('detail-content');

  const galleryMainBox = document.getElementById('gallery-main-box');
  const galleryThumbsBox = document.getElementById('gallery-thumbs-box');
  const metaLineEl = document.getElementById('detail-meta-line');
  const nameEl = document.getElementById('detail-product-name');
  const promoBannerEl = document.getElementById('detail-promo-banner');
  const promoBadgeEl = document.getElementById('detail-promo-badge');
  const promoNameEl = document.getElementById('detail-promo-name');
  const finalPriceEl = document.getElementById('detail-final-price');
  const originalPriceEl = document.getElementById('detail-original-price');
  const descriptionEl = document.getElementById('detail-description');

  const cartForm = document.getElementById('add-to-cart-form');
  const variantPillsBox = document.getElementById('variant-pills');
  const selectedVariantMeta = document.getElementById('selected-variant-meta');
  const qtyInput = document.getElementById('buy-quantity');
  const qtyMinusBtn = document.getElementById('qty-minus-btn');
  const qtyPlusBtn = document.getElementById('qty-plus-btn');
  const stockBadgeEl = document.getElementById('stock-status-badge');
  const addCartBtn = document.getElementById('add-cart-submit-btn');
  const wishlistBtn = document.getElementById('detail-wishlist-btn');

  const specListEl = document.getElementById('detail-spec-list');
  const reviewsSummaryBadge = document.getElementById('reviews-summary-badge');
  const reviewsLoadingEl = document.getElementById('reviews-loading');
  const reviewsEmptyEl = document.getElementById('reviews-empty');
  const reviewsListEl = document.getElementById('reviews-list');

  let currentProduct = null;
  let selectedVariant = null;
  let inWishlist = false;

  function renderMainImage(imageUrl, altText) {
    if (imageUrl) {
      galleryMainBox.innerHTML =
        '<img src="' +
        window.Pasaryo.escapeHtml(imageUrl) +
        '" alt="' +
        window.Pasaryo.escapeHtml(altText) +
        '" width="640" height="480" fetchpriority="high">';
    } else {
      const brandLabel =
        (currentProduct && currentProduct.brand && currentProduct.brand.name) || 'PASARYO';
      galleryMainBox.innerHTML =
        '<div class="product-media-fallback">' +
        '<strong>' +
        window.Pasaryo.escapeHtml(brandLabel.toUpperCase()) +
        '</strong>' +
        '<span>Produk ini belum memiliki foto galeri</span>' +
        '</div>';
    }
  }

  function renderGallery(product) {
    const images = Array.isArray(product.images) ? product.images : [];
    const primaryUrl = (images[0] && images[0].image_url) || product.image_url || null;
    renderMainImage(primaryUrl, 'Foto utama ' + product.name);

    galleryThumbsBox.innerHTML = '';
    if (images.length <= 1) {
      return;
    }

    images.forEach(function (imgObj, idx) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'thumb-btn';
      btn.setAttribute('aria-pressed', idx === 0 ? 'true' : 'false');
      btn.setAttribute('aria-label', 'Tampilkan foto ' + (idx + 1));
      btn.innerHTML =
        '<img src="' +
        window.Pasaryo.escapeHtml(imgObj.image_url) +
        '" alt="Thumbnail ' +
        (idx + 1) +
        '" width="72" height="56" loading="lazy">';

      btn.addEventListener('click', function () {
        galleryThumbsBox.querySelectorAll('.thumb-btn').forEach(function (b) {
          b.setAttribute('aria-pressed', 'false');
        });
        btn.setAttribute('aria-pressed', 'true');
        renderMainImage(imgObj.image_url, 'Foto ' + (idx + 1) + ' ' + product.name);
      });

      galleryThumbsBox.appendChild(btn);
    });
  }

  function selectVariant(variant) {
    selectedVariant = variant;
    variantPillsBox.querySelectorAll('.variant-pill').forEach(function (btn) {
      const isMatch = Number(btn.dataset.variantId) === Number(variant.id);
      btn.setAttribute('aria-pressed', isMatch ? 'true' : 'false');
    });

    const stockCount = Number(variant.stock || 0);
    selectedVariantMeta.textContent =
      'SKU: ' + variant.sku + ' | Stok tersedia: ' + stockCount + ' unit';

    if (stockCount > 0) {
      stockBadgeEl.className = 'badge badge-success mono-num';
      stockBadgeEl.textContent = 'Stok Tersedia (' + stockCount + ')';
      qtyInput.max = String(stockCount);
      if (Number(qtyInput.value) > stockCount) {
        qtyInput.value = String(stockCount);
      }
      addCartBtn.disabled = false;
      addCartBtn.textContent = 'Tambah ke Keranjang';
    } else {
      stockBadgeEl.className = 'badge badge-danger';
      stockBadgeEl.textContent = 'Stok Habis';
      addCartBtn.disabled = true;
      addCartBtn.textContent = 'Varian Habis';
    }
  }

  function renderVariants(variants) {
    variantPillsBox.innerHTML = '';
    if (!Array.isArray(variants) || variants.length === 0) {
      selectedVariant = null;
      selectedVariantMeta.textContent = 'Produk ini belum memiliki varian yang dapat dibeli.';
      stockBadgeEl.className = 'badge badge-danger';
      stockBadgeEl.textContent = 'Stok Tidak Tersedia';
      addCartBtn.disabled = true;
      return;
    }

    let firstAvailable = variants[0];
    variants.forEach(function (v) {
      if (firstAvailable.stock <= 0 && v.stock > 0) {
        firstAvailable = v;
      }
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'variant-pill';
      btn.dataset.variantId = String(v.id);
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = v.color_name + ' (' + v.stock + ')';
      btn.addEventListener('click', function () {
        selectVariant(v);
      });
      variantPillsBox.appendChild(btn);
    });

    selectVariant(firstAvailable);
  }

  function renderSpecifications(product) {
    specListEl.innerHTML = '';
    const rows = [
      ['Kategori', (product.category && product.category.name) || 'Umum'],
      ['Brand', (product.brand && product.brand.name) || 'Pasaryo'],
      ['Kota Asal Pengiriman', product.origin_city || 'Indonesia'],
    ];

    const specs = product.specifications;
    if (specs && typeof specs === 'object' && !Array.isArray(specs)) {
      Object.keys(specs).forEach(function (k) {
        rows.push([k, String(specs[k])]);
      });
    } else if (typeof specs === 'string' && specs.trim()) {
      rows.push(['Rincian Teknis', specs.trim()]);
    }

    rows.forEach(function (pair) {
      const dt = document.createElement('dt');
      dt.textContent = pair[0];
      const dd = document.createElement('dd');
      dd.textContent = pair[1];
      specListEl.appendChild(dt);
      specListEl.appendChild(dd);
    });
  }

  async function loadReviews() {
    reviewsLoadingEl.hidden = false;
    reviewsEmptyEl.hidden = true;
    reviewsListEl.hidden = true;

    const res = await window.Pasaryo.apiRequest(
      '/frontend-api/products/' + encodeURIComponent(productId) + '/reviews/'
    );
    reviewsLoadingEl.hidden = true;

    if (!res.ok || !res.data) {
      reviewsSummaryBadge.textContent = '0 ulasan';
      reviewsEmptyEl.hidden = false;
      return;
    }

    const count = Number(res.data.count || 0);
    const avg = res.data.average_rating;
    reviewsSummaryBadge.textContent =
      count > 0 && avg !== null
        ? 'Rating ' + avg + '/5 (' + count + ' ulasan)'
        : '0 ulasan';

    const items = Array.isArray(res.data.results) ? res.data.results : [];
    if (items.length === 0) {
      reviewsEmptyEl.hidden = false;
      return;
    }

    reviewsListEl.innerHTML = '';
    items.forEach(function (rev) {
      const itemEl = document.createElement('article');
      itemEl.className = 'record-item';
      itemEl.innerHTML =
        '<div class="record-info">' +
        '<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">' +
        '<span class="avatar-initials">' +
        window.Pasaryo.escapeHtml(rev.reviewer_initials) +
        '</span>' +
        '<strong>' +
        window.Pasaryo.escapeHtml(rev.reviewer_name) +
        '</strong>' +
        '<span class="badge badge-accent mono-num">' +
        window.Pasaryo.escapeHtml(rev.rating) +
        ' / 5</span>' +
        '</div>' +
        '<p class="text-muted" style="margin-bottom: 6px;">Varian: ' +
        window.Pasaryo.escapeHtml(rev.variant_name || '-') +
        ' &middot; ' +
        window.Pasaryo.escapeHtml(window.Pasaryo.formatDateOnly(rev.created_at)) +
        '</p>' +
        '<p style="margin-bottom: 0;">' +
        window.Pasaryo.escapeHtml(rev.comment || 'Pembeli memberikan rating tanpa komentar tertulis.') +
        '</p>' +
        '</div>';
      reviewsListEl.appendChild(itemEl);
    });
    reviewsListEl.hidden = false;
  }

  async function loadProductDetail() {
    loadingEl.hidden = false;
    errorEl.hidden = true;
    contentEl.hidden = true;

    const res = await window.Pasaryo.apiRequest(
      '/catalog/products/' + encodeURIComponent(productId) + '/'
    );
    loadingEl.hidden = true;

    if (!res.ok || !res.data || !res.data.product) {
      errorMsgEl.textContent =
        (res.data && res.data.message) || 'Produk tidak ditemukan di katalog.';
      errorEl.hidden = false;
      return;
    }

    const product = res.data.product;
    currentProduct = product;
    document.title = product.name + ' | Pasaryo';

    const catName = (product.category && product.category.name) || 'Kategori';
    const brandName = (product.brand && product.brand.name) || 'Brand';
    metaLineEl.textContent =
      catName + ' / ' + brandName + ' / Dikirim dari ' + (product.origin_city || 'Indonesia');
    nameEl.textContent = product.name;

    const hasDiscount = Number(product.discount_amount || 0) > 0;
    finalPriceEl.textContent = window.Pasaryo.formatRupiah(product.final_price);
    if (hasDiscount) {
      originalPriceEl.textContent = window.Pasaryo.formatRupiah(product.price);
      originalPriceEl.hidden = false;
    } else {
      originalPriceEl.hidden = true;
    }

    if (product.promotion && product.promotion.name) {
      promoBadgeEl.textContent = 'Diskon ' + product.discount_percentage + '%';
      promoNameEl.textContent = product.promotion.name;
      promoBannerEl.hidden = false;
    } else {
      promoBannerEl.hidden = true;
    }

    descriptionEl.textContent =
      product.description || 'Belum ada deskripsi tambahan untuk produk ini.';

    renderGallery(product);
    renderVariants(product.variants || []);
    renderSpecifications(product);

    contentEl.hidden = false;
    await loadReviews();
  }

  if (qtyMinusBtn && qtyInput) {
    qtyMinusBtn.addEventListener('click', function () {
      const current = Number(qtyInput.value) || 1;
      if (current > 1) {
        qtyInput.value = String(current - 1);
      }
    });
  }

  if (qtyPlusBtn && qtyInput) {
    qtyPlusBtn.addEventListener('click', function () {
      const current = Number(qtyInput.value) || 1;
      const maxStock = selectedVariant ? Number(selectedVariant.stock || 99) : 99;
      if (current < maxStock) {
        qtyInput.value = String(current + 1);
      }
    });
  }

  if (cartForm) {
    window.Pasaryo.bindLiveErrorClear(cartForm);
    cartForm.addEventListener('submit', async function (event) {
      event.preventDefault();
      window.Pasaryo.clearFormErrors(cartForm);

      if (!selectedVariant) {
        window.Pasaryo.applyFormErrors(cartForm, null, 'Pilih varian produk terlebih dahulu.');
        return;
      }

      const qty = Number(qtyInput.value);
      if (!Number.isInteger(qty) || qty < 1) {
        window.Pasaryo.setFieldError(cartForm, 'quantity', 'Jumlah pembelian minimal 1 unit.');
        return;
      }
      if (qty > Number(selectedVariant.stock || 0)) {
        window.Pasaryo.setFieldError(
          cartForm,
          'quantity',
          'Jumlah melebihi stok varian yang tersedia (' + selectedVariant.stock + ' unit).'
        );
        return;
      }

      window.Pasaryo.setButtonBusy(addCartBtn, true, 'Menambahkan ke Keranjang...');
      const res = await window.Pasaryo.apiRequest('/api/cart/', {
        method: 'POST',
        body: {
          product_variant_id: Number(selectedVariant.id),
          quantity: qty,
        },
      });
      window.Pasaryo.setButtonBusy(addCartBtn, false);

      if (res.status === 401) {
        window.Pasaryo.showToast('Silakan masuk ke akun untuk menambahkan barang ke keranjang.', 'error');
        return;
      }

      if (!res.ok) {
        window.Pasaryo.applyFormErrors(
          cartForm,
          res.data,
          (res.data && res.data.message) || 'Gagal menambahkan produk ke keranjang.'
        );
        return;
      }

      await window.Pasaryo.refreshCartBadge();
      window.Pasaryo.showToast('Produk berhasil ditambahkan ke keranjang belanja.', 'success');
    });
  }

  if (wishlistBtn) {
    wishlistBtn.addEventListener('click', async function () {
      if (!inWishlist) {
        window.Pasaryo.setButtonBusy(wishlistBtn, true, 'Menyimpan...');
        const res = await window.Pasaryo.apiRequest('/wishlist/', {
          method: 'POST',
          body: { product_id: productId },
        });
        window.Pasaryo.setButtonBusy(wishlistBtn, false);

        if (res.status === 401) {
          window.Pasaryo.showToast('Silakan masuk terlebih dahulu untuk menyimpan wishlist.', 'error');
          return;
        }
        if (!res.ok) {
          window.Pasaryo.showToast(
            (res.data && res.data.message) || 'Gagal menyimpan ke wishlist.',
            'error'
          );
          return;
        }
        inWishlist = true;
        wishlistBtn.textContent = 'Hapus dari Wishlist';
        wishlistBtn.dataset.originalLabel = 'Hapus dari Wishlist';
        window.Pasaryo.showToast(res.data.message || 'Produk disimpan ke wishlist.', 'success');
      } else {
        const confirmed = await window.Pasaryo.confirmAction({
          title: 'Hapus dari Wishlist',
          description: 'Apakah Anda yakin ingin menghapus produk ini dari daftar wishlist Anda?',
          confirmLabel: 'Ya, Hapus dari Wishlist',
          cancelLabel: 'Batal',
        });
        if (!confirmed) {
          return;
        }
        window.Pasaryo.setButtonBusy(wishlistBtn, true, 'Menghapus...');
        const res = await window.Pasaryo.apiRequest(
          '/wishlist/' + encodeURIComponent(productId) + '/',
          { method: 'DELETE' }
        );
        window.Pasaryo.setButtonBusy(wishlistBtn, false);
        if (res.ok) {
          inWishlist = false;
          wishlistBtn.textContent = 'Simpan ke Wishlist';
          wishlistBtn.dataset.originalLabel = 'Simpan ke Wishlist';
          window.Pasaryo.showToast('Produk dihapus dari wishlist.', 'success');
        } else {
          window.Pasaryo.showToast(
            (res.data && res.data.message) || 'Gagal menghapus dari wishlist.',
            'error'
          );
        }
      }
    });
  }

  if (retryBtn) {
    retryBtn.addEventListener('click', loadProductDetail);
  }

  document.addEventListener('DOMContentLoaded', loadProductDetail);
})();

