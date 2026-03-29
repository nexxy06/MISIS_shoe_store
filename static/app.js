'use strict';
/* ═══════════════════════════════════════════════════════════════════════════
   ООО «Обувь» — Frontend JavaScript
   ═══════════════════════════════════════════════════════════════════════════ */

// ── Init ──────────────────────────────────────────────────────────────────
function initPage(role, _title) {   // eslint-disable-line no-unused-vars
  markActiveNav();
  if (document.getElementById('fb-search')) {
    initLiveFilter(role);
  }
}

function markActiveNav() {
  const path = location.pathname;
  document.querySelectorAll('.nav-link').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === path);
  });
}

// ── Password toggle ───────────────────────────────────────────────────────
function togglePw() {               // eslint-disable-line no-unused-vars
  const inp = document.getElementById('f-pass');
  if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
}

// ── Login form ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errBox = document.getElementById('err-box');
    errBox.style.display = 'none';
    try {
      const res = await fetch('/login', {
        method:  'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body:    `login=${encodeURIComponent(document.getElementById('f-login').value)}`
               + `&password=${encodeURIComponent(document.getElementById('f-pass').value)}`,
      });
      const d = await res.json();
      if (d.ok) { location.href = '/products'; }
      else { errBox.textContent = d.error || 'Ошибка входа'; errBox.style.display = 'block'; }
    } catch {
      errBox.textContent = 'Ошибка соединения с сервером';
      errBox.style.display = 'block';
    }
  });
});

// ── Generic API fetch ─────────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  return res.json();
}

// ── Modal helpers ─────────────────────────────────────────────────────────
function openModal(id) {
  const el = document.getElementById(id);
  if (el) { el.style.display = 'flex'; document.body.style.overflow = 'hidden'; }
}
function closeModal(id) {           // eslint-disable-line no-unused-vars
  const el = document.getElementById(id);
  if (el) { el.style.display = 'none'; document.body.style.overflow = ''; }
}

// ── HTML escape ───────────────────────────────────────────────────────────
function esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function makeOpts(arr, selected) {
  return arr.map(v =>
    `<option value="${esc(v)}"${v === selected ? ' selected' : ''}>${esc(v)}</option>`
  ).join('');
}

// ══════════════════════════════════════════════════════════════════════════
//  LIVE FILTER ENGINE
//  ─────────────────────────────────────────────────────────────────────────
//  Strategy: fetch all products as JSON once on page load; keep a master
//  array in memory; on every control event run filter+sort in <1 ms and
//  rebuild only the <tbody> innerHTML.  Zero server round-trips.
// ══════════════════════════════════════════════════════════════════════════

let _allProducts = [];   // full dataset, never mutated after load
let _canEdit     = false;

async function initLiveFilter(role) {
  _canEdit = (role === 'Администратор');

  // Загружаем все товары один раз
  _allProducts = await apiFetch('/api/products');

  // Кнопка сброса
  const resetBtn = document.getElementById('fb-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('fb-search').value   = '';
      document.getElementById('fb-category').value = '';
      document.getElementById('fb-supplier').value = '';
      document.getElementById('fb-sort').value     = '';
      applyFilter();
    });
  }

  // Опрашиваем поля каждые 2 секунды — работает без Enter и без событий
  setInterval(applyFilter, 2000);

  applyFilter();
}

function applyFilter() {
  const needle   = document.getElementById('fb-search').value.trim().toLowerCase();
  const cat      = document.getElementById('fb-category').value;
  const supplier = document.getElementById('fb-supplier').value;
  const sort     = document.getElementById('fb-sort').value;

  // ── 1. Filter ──────────────────────────────────────────────────────────
  let visible = _allProducts.filter(p => {
    // Search across ALL text fields simultaneously
    if (needle) {
      const hit = (p.product_name || '').toLowerCase().includes(needle)
               || (p.article || '').toLowerCase().includes(needle)
               || (p.category_name || '').toLowerCase().includes(needle)
               || (p.supplier_name || '').toLowerCase().includes(needle)
               || (p.manufacturer_name || '').toLowerCase().includes(needle)
               || (p.description || '').toLowerCase().includes(needle)
               || (p.unit || '').toLowerCase().includes(needle);
      if (!hit) return false;
    }
    // Category dropdown — exact match, empty = all
    if (cat && cat !== '' && p.category_name !== cat) return false;
    // Supplier dropdown — exact match, empty = all
    if (supplier && supplier !== '' && p.supplier_name !== supplier) return false;
    return true;
  });

  // ── 2. Sort ────────────────────────────────────────────────────────────
  const sorters = {
    name_asc:   (a, b) => a.product_name.localeCompare(b.product_name, 'ru'),
    name_desc:  (a, b) => b.product_name.localeCompare(a.product_name, 'ru'),
    price_asc:  (a, b) => a.price     - b.price,
    price_desc: (a, b) => b.price     - a.price,
    disc_asc:   (a, b) => a.discount  - b.discount,
    disc_desc:  (a, b) => b.discount  - a.discount,
    stock_asc:  (a, b) => a.stock_qty - b.stock_qty,
    stock_desc: (a, b) => b.stock_qty - a.stock_qty,
  };
  if (sorters[sort]) visible = [...visible].sort(sorters[sort]);

  // ── 3. Render ──────────────────────────────────────────────────────────
  renderTable(visible);
}

function renderTable(products) {
  const container = document.getElementById('prod-container');
  if (!container) return;

  if (products.length === 0) {
    container.innerHTML = '<div class="empty-state">Товары не найдены</div>';
    return;
  }

  const rows = products.map(p => (
    `<tr class="${p.row_cls}" data-id="${p.product_id}">`
    + `<td class="td-img">`
    +   `<img src="${p.img_src}" alt="фото" class="prod-img"`
    +       ` onerror="this.src='/static/images/picture.png'">`
    +   p.actions
    + `</td>`
    + `<td class="td-info">${p.info_html}</td>`
    + `<td class="td-disc">${p.disc_cell}</td>`
    + `</tr>`
  )).join('');

  container.innerHTML =
    `<table class="prod-table">`
    + `<tbody>${rows}</tbody>`
    + `</table>`;
}

// ══════════════════════════════════════════════════════════════════════════
//  PRODUCT MODAL (add / edit)
// ══════════════════════════════════════════════════════════════════════════

async function openProductModal(productId) { // eslint-disable-line no-unused-vars
  const overlay = document.getElementById('product-modal');
  if (!overlay) return;

  let prod = {}, cats = [], sups = [], mans = [];
  if (productId) {
    const d = await apiFetch(`/api/product?id=${productId}`);
    if (d.error) { alert('Ошибка загрузки: ' + d.error); return; }
    prod = d.product; cats = d.categories; sups = d.suppliers; mans = d.manufacturers;
  } else {
    [cats, sups, mans] = await Promise.all([
      apiFetch('/api/categories'),
      apiFetch('/api/suppliers'),
      apiFetch('/api/manufacturers'),
    ]);
  }


  overlay.innerHTML = `
    <div class="modal-box" onclick="event.stopPropagation()">
      <h3>${productId ? '✏️ Редактировать товар' : '＋ Добавить товар'}</h3>

      <form id="product-form">
        <label>Артикул *</label>
        <input id="m-article" name="article" value="${esc(prod.article || '')}" placeholder="А112Т4" required>

        <label>Наименование *</label>
        <input id="m-name" name="product_name" value="${esc(prod.product_name || '')}" placeholder="Ботинки" required>

        <label>Категория</label>
        <select id="m-cat" name="category_name">${makeOpts(cats, prod.category_name)}</select>

        <label>Производитель</label>
        <select id="m-man" name="manufacturer_name">${makeOpts(mans, prod.manufacturer_name)}</select>

        <label>Поставщик</label>
        <select id="m-sup" name="supplier_name">${makeOpts(sups, prod.supplier_name)}</select>

        <label>Единица измерения</label>
        <input id="m-unit" name="unit" value="${esc(prod.unit || 'шт.')}" >

        <label>Цена (₽) *</label>
        <input id="m-price" name="price" type="number" min="0" step="0.01" value="${prod.price ?? ''}">

        <label>Скидка (%)</label>
        <input id="m-disc" name="discount" type="number" min="0" max="100" step="0.1" value="${prod.discount ?? 0}">

        <label>Количество на складе</label>
        <input id="m-stock" name="stock_qty" type="number" min="0" value="${prod.stock_qty ?? 0}">

        <label>Описание</label>
        <textarea id="m-desc" name="description" rows="3">${esc(prod.description || '')}</textarea>

        <label>Фото (jpg/png, макс. 2 МБ)</label>
        <input id="m-photo-file" name="photo_file" type="file" accept="image/*">
        <div style="font-size:0.9em;color:#888;">${prod.photo ? `Текущее фото: ${esc(prod.photo)}` : ''}</div>

        <div class="modal-footer">
          <button type="button" class="btn-secondary" onclick="closeModal('product-modal')">Отмена</button>
          <button type="submit" class="btn-primary">💾 Сохранить</button>
        </div>
      </form>
    </div>`;

  overlay.onclick = (e) => { if (e.target === overlay) closeModal('product-modal'); };
  openModal('product-modal');

  document.getElementById('product-form').onsubmit = async function(e) {
    e.preventDefault();
    await saveProduct(productId, prod.photo || null);
  };
}

async function saveProduct(productId, oldPhoto) { // eslint-disable-line no-unused-vars
  const form = document.getElementById('product-form');
  const article = form.article.value.trim();
  const name    = form.product_name.value.trim();
  const price   = parseFloat(form.price.value);
  if (!article || !name || isNaN(price)) {
    alert('Заполните обязательные поля: артикул, наименование, цена'); return;
  }
  const fd = new FormData(form);
  fd.append('product_id', productId);
  fd.append('old_photo', oldPhoto || '');
  // Если файл не выбран, не отправлять photo_file
  if (!form.photo_file.files.length) fd.delete('photo_file');
  const res = await fetch('/api/product', { method: 'POST', body: fd });
  const d = await res.json();
  if (d.ok) { closeModal('product-modal'); location.reload(); }
  else       alert('Ошибка сохранения: ' + (d.error || 'неизвестно'));
}

function editProduct(productId)  { openProductModal(productId); }  // eslint-disable-line no-unused-vars

async function deleteProduct(productId) { // eslint-disable-line no-unused-vars
  if (!confirm('Удалить этот товар? Действие необратимо.')) return;
  const d = await apiFetch('/api/product/delete',
    { method: 'POST', body: JSON.stringify({ product_id: productId }) });
  if (d.ok) location.reload();
  else      alert('Ошибка удаления: ' + (d.error || 'неизвестно'));
}

// ══════════════════════════════════════════════════════════════════════════
//  ORDER MODAL (add / edit)
// ══════════════════════════════════════════════════════════════════════════

let _orderItems = [];

async function openOrderModal(orderId) { // eslint-disable-line no-unused-vars
  const overlay = document.getElementById('order-modal');
  if (!overlay) return;

  let order = {}, items = [], users = [], pps = [];
  if (orderId) {
    const d = await apiFetch(`/api/order?id=${orderId}`);
    if (d.error) { alert('Ошибка загрузки: ' + d.error); return; }
    order = d.order; items = d.items; users = d.users; pps = d.pickup_points;
  } else {
    [users, pps] = await Promise.all([apiFetch('/api/users'), apiFetch('/api/pickup_points')]);
  }
  _orderItems = items.map(i => ({ article: i.article, quantity: i.quantity }));

  const userOpts = users.map(u =>
    `<option value="${u.user_id}"${u.user_id == order.user_id ? ' selected' : ''}>${esc(u.full_name)}</option>`
  ).join('');
  const ppOpts = pps.map(p =>
    `<option value="${p.pickup_point_id}"${p.pickup_point_id == order.pickup_point_id ? ' selected' : ''}>${esc(p.address)}</option>`
  ).join('');

  overlay.innerHTML = `
    <div class="modal-box" onclick="event.stopPropagation()">
      <h3>${orderId ? '✏️ Редактировать заказ' : '＋ Новый заказ'}</h3>

      <label>Дата заказа</label>
      <input id="o-date"  type="date" value="${esc(order.order_date    || '')}">

      <label>Дата доставки</label>
      <input id="o-ddate" type="date" value="${esc(order.delivery_date || '')}">

      <label>Клиент</label>
      <select id="o-user"><option value="">— не указан —</option>${userOpts}</select>

      <label>Пункт выдачи</label>
      <select id="o-pp"><option value="">— не указан —</option>${ppOpts}</select>

      <label>Код получения</label>
      <input id="o-code" value="${esc(order.pickup_code || '')}" placeholder="901">

      <label>Статус</label>
      <select id="o-status">
        <option value="Новый"    ${order.status === 'Новый'    ? 'selected' : ''}>Новый</option>
        <option value="Завершен" ${order.status === 'Завершен' ? 'selected' : ''}>Завершен</option>
      </select>

      <div class="order-items-section">
        <h4>Позиции заказа</h4>
        <div id="order-items-list"></div>
        <button class="btn-secondary btn-add-item" onclick="addOrderItem()">＋ Добавить позицию</button>
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" onclick="closeModal('order-modal')">Отмена</button>
        <button class="btn-primary"   onclick="saveOrder(${orderId || 'null'})">💾 Сохранить</button>
      </div>
    </div>`;

  overlay.onclick = (e) => { if (e.target === overlay) closeModal('order-modal'); };
  openModal('order-modal');
  renderOrderItems();
}

function renderOrderItems() {
  const list = document.getElementById('order-items-list');
  if (!list) return;
  if (_orderItems.length === 0) {
    list.innerHTML = '<div class="items-empty">Нет позиций</div>'; return;
  }
  list.innerHTML = _orderItems.map((item, i) => `
    <div class="order-item-row">
      <input value="${esc(item.article)}" placeholder="Артикул"
             oninput="_orderItems[${i}].article = this.value">
      <input class="qty-input" type="number" min="1" value="${item.quantity}"
             oninput="_orderItems[${i}].quantity = parseInt(this.value) || 1">
      <button class="btn-icon btn-del" title="Удалить позицию"
              onclick="_orderItems.splice(${i},1); renderOrderItems()">🗑️</button>
    </div>`).join('');
}

function addOrderItem() {           // eslint-disable-line no-unused-vars
  _orderItems.push({ article: '', quantity: 1 });
  renderOrderItems();
  const rows = document.querySelectorAll('.order-item-row');
  if (rows.length) rows[rows.length - 1].querySelector('input').focus();
}

async function saveOrder(orderId) { // eslint-disable-line no-unused-vars
  const data = {
    order_id:        orderId,
    order_date:      document.getElementById('o-date').value  || null,
    delivery_date:   document.getElementById('o-ddate').value || null,
    user_id:         document.getElementById('o-user').value  || null,
    pickup_point_id: document.getElementById('o-pp').value    || null,
    pickup_code:     document.getElementById('o-code').value.trim() || null,
    status:          document.getElementById('o-status').value,
    items:           _orderItems.filter(i => i.article.trim()),
  };
  const d = await apiFetch('/api/order', { method: 'POST', body: JSON.stringify(data) });
  if (d.ok) { closeModal('order-modal'); location.reload(); }
  else       alert('Ошибка сохранения: ' + (d.error || 'неизвестно'));
}

async function deleteOrder(orderId) { // eslint-disable-line no-unused-vars
  if (!confirm('Удалить заказ? Действие необратимо.')) return;
  const d = await apiFetch('/api/order/delete',
    { method: 'POST', body: JSON.stringify({ order_id: orderId }) });
  if (d.ok) location.reload();
  else      alert('Ошибка: ' + (d.error || 'неизвестно'));
}