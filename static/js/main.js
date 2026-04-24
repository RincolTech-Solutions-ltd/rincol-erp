/* ── Rincol Web ERP — Main JS ─────────────────────────────────────────── */

// ── Sidebar toggle (mobile) ─────────────────────────────────────────────────
document.getElementById('sidebarToggle')?.addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('sidebar-collapsed');
});

// ── Number formatting ────────────────────────────────────────────────────────
function fmt(n) {
  return Math.round(n).toLocaleString('en-US');
}

// ── Column resize (vanilla, no lib dependency) ───────────────────────────────
function initColResize(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const cols = table.querySelectorAll('th');
  cols.forEach((th) => {
    const resizer = document.createElement('div');
    resizer.className = 'col-resizer';
    th.appendChild(resizer);
    let x = 0, w = 0;
    resizer.addEventListener('mousedown', (e) => {
      x = e.clientX;
      w = th.offsetWidth;
      th.classList.add('resizing');
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
    });
    function onMove(e) {
      th.style.width = Math.max(40, w + e.clientX - x) + 'px';
      th.style.minWidth = th.style.width;
    }
    function onUp() {
      th.classList.remove('resizing');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }
  });
}

// ── Quotation line-item editor ───────────────────────────────────────────────
(function () {
  const tbody   = document.getElementById('items-tbody');
  const addBtn  = document.getElementById('add-row-btn');
  const grandEl = document.getElementById('grand-total');
  if (!tbody) return;

  let rowIndex = tbody.querySelectorAll('tr').length;

  function recalcRow(row) {
    const qty   = parseFloat(row.querySelector('.col-qty').value)   || 0;
    const price = parseFloat(row.querySelector('.col-price').value) || 0;
    const total = qty * price;
    const totalEl = row.querySelector('.col-total');
    totalEl.textContent = fmt(total);
    totalEl.dataset.value = total;
  }

  function recalcAll() {
    let subtotal = 0;
    tbody.querySelectorAll('tr').forEach((row, i) => {
      row.querySelector('.col-no').textContent = i + 1;
      subtotal += parseFloat(row.querySelector('.col-total').dataset.value || 0);
    });

    const vatHidden   = document.getElementById('apply-vat-hidden');
    const vatPctEl    = document.getElementById('vat-pct');
    const vatRow      = document.getElementById('vat-row');
    const subtotalRow = document.getElementById('subtotal-row');
    const subtotalEl  = document.getElementById('subtotal-display');
    const vatEl       = document.getElementById('vat-display');
    const applyVat    = vatHidden?.value === '1';
    const vatPct      = parseFloat(vatPctEl?.value) || 18;
    const vatAmt      = applyVat ? subtotal * vatPct / 100 : 0;
    const grand       = subtotal + vatAmt;

    if (subtotalRow) subtotalRow.style.display = applyVat ? '' : 'none';
    if (vatRow)      vatRow.style.display      = applyVat ? '' : 'none';
    if (subtotalEl)  subtotalEl.textContent    = 'UGX ' + fmt(subtotal);
    if (vatEl)       vatEl.textContent         = 'UGX ' + fmt(vatAmt);
    if (grandEl)     grandEl.textContent       = 'UGX ' + fmt(grand);
  }

  // VAT toggle button
  document.getElementById('vat-toggle-btn')?.addEventListener('click', () => {
    const hidden = document.getElementById('apply-vat-hidden');
    const btn    = document.getElementById('vat-toggle-btn');
    const on     = hidden.value !== '1';
    hidden.value = on ? '1' : '0';
    btn.innerHTML = on
      ? '<i class="bi bi-dash"></i> Remove VAT'
      : '<i class="bi bi-plus"></i> Add VAT';
    btn.className = 'btn btn-sm py-0 px-2 ' + (on ? 'btn-outline-danger' : 'btn-outline-secondary');
    recalcAll();
  });
  document.getElementById('vat-pct')?.addEventListener('input', recalcAll);

  function lockQtyIfLot(row) {
    const uomSel = row.querySelector('.col-uom');
    const qtyIn  = row.querySelector('.col-qty');
    if (!uomSel || !qtyIn) return;
    const uom = uomSel.value.toLowerCase();
    if (uom === 'lot' || uom === 'job') {
      qtyIn.value = 1;
      qtyIn.readOnly = true;
      qtyIn.style.opacity = '.5';
    } else {
      qtyIn.readOnly = false;
      qtyIn.style.opacity = '1';
    }
  }

  // ── Catalog picker ─────────────────────────────────────────────────────────
  function buildCatalogSelect() {
    const catalog = window.CATALOG_ITEMS || [];
    const sel = document.createElement('select');
    sel.className = 'catalog-picker form-select form-select-sm mt-1';
    sel.title = 'Fill from catalog';
    // Blank/placeholder option
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = '📦 From catalog…';
    sel.appendChild(blank);
    // Group by category
    const groups = {};
    catalog.forEach(item => {
      const cat = item.category || 'Other';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    });
    Object.keys(groups).sort().forEach(cat => {
      const og = document.createElement('optgroup');
      og.label = cat;
      groups[cat].forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.id;
        const label = item.name + (item.spec ? ' — ' + item.spec : '');
        opt.textContent = label;
        opt.dataset.name  = item.name;
        opt.dataset.spec  = item.spec || '';
        opt.dataset.uom   = item.uom || 'pc';
        opt.dataset.price = item.sell_price || 0;
        og.appendChild(opt);
      });
      sel.appendChild(og);
    });
    return sel;
  }

  function addCatalogPicker(tr) {
    if (!(window.CATALOG_ITEMS && window.CATALOG_ITEMS.length)) return;
    const descTd = tr.querySelectorAll('td')[1];
    if (!descTd || descTd.querySelector('.catalog-picker')) return;
    const sel = buildCatalogSelect();
    descTd.appendChild(sel);
    sel.addEventListener('change', () => {
      const opt = sel.options[sel.selectedIndex];
      if (!opt || !opt.value) return;
      const descIn  = tr.querySelector('.col-desc');
      const uomSel  = tr.querySelector('.col-uom');
      const priceIn = tr.querySelector('.col-price');
      const fullName = opt.dataset.name + (opt.dataset.spec ? ' ' + opt.dataset.spec : '');
      if (descIn)  descIn.value  = fullName;
      if (priceIn) { priceIn.value = opt.dataset.price; priceIn.dispatchEvent(new Event('input')); }
      // Set UOM if the option exists
      if (uomSel) {
        const uomVal = opt.dataset.uom;
        for (let i = 0; i < uomSel.options.length; i++) {
          if (uomSel.options[i].value === uomVal) { uomSel.selectedIndex = i; break; }
        }
        uomSel.dispatchEvent(new Event('change'));
      }
      // Reset picker to placeholder
      sel.selectedIndex = 0;
    });
  }

  function makeRow(data = {}) {
    const tr = document.createElement('tr');
    tr.draggable = true;
    const uomOptions = ['pc','lot','job','m','roll','set','pair','box'].map(u =>
      `<option value="${u}" ${(data.uom||'pc')===u?'selected':''}>${u}</option>`
    ).join('');
    tr.innerHTML = `
      <td class="drag-handle" title="Drag to reorder">⠿</td>
      <td class="col-no td-no">${rowIndex + 1}</td>
      <td><input type="text" name="desc[]" class="col-desc" value="${escHtml(data.description||data.desc||'')}"></td>
      <td><select name="uom[]" class="col-uom">${uomOptions}</select></td>
      <td><input type="number" name="qty[]" class="col-qty" value="${data.qty||1}" min="0.01" step="any"></td>
      <td><input type="number" name="price[]" class="col-price" value="${data.unit_price||data.price||0}" min="0" step="any"></td>
      <td class="col-total td-total" data-value="${(data.qty||1)*(data.unit_price||0)}">${fmt((data.qty||1)*(data.unit_price||0))}</td>
      <td class="text-center">
        <button type="button" class="btn btn-sm btn-outline-danger py-0 px-1 remove-row-btn" title="Remove">
          <i class="bi bi-x"></i>
        </button>
      </td>`;
    rowIndex++;

    // Wire up events
    const qtyIn   = tr.querySelector('.col-qty');
    const priceIn = tr.querySelector('.col-price');
    const uomSel  = tr.querySelector('.col-uom');
    const rmBtn   = tr.querySelector('.remove-row-btn');

    qtyIn.addEventListener('input',   () => { recalcRow(tr); recalcAll(); });
    priceIn.addEventListener('input',  () => { recalcRow(tr); recalcAll(); });
    uomSel.addEventListener('change',  () => { lockQtyIfLot(tr); recalcRow(tr); recalcAll(); });
    rmBtn.addEventListener('click',    () => { tr.remove(); recalcAll(); });

    addCatalogPicker(tr);
    lockQtyIfLot(tr);
    return tr;
  }

  function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // Add empty row button
  addBtn?.addEventListener('click', () => {
    const tr = makeRow();
    tbody.appendChild(tr);
    tr.querySelector('.col-desc')?.focus();
    recalcAll();
  });

  // Wire up existing rows (rendered by Jinja2)
  tbody.querySelectorAll('tr').forEach(tr => {
    const qtyIn   = tr.querySelector('.col-qty');
    const priceIn = tr.querySelector('.col-price');
    const uomSel  = tr.querySelector('.col-uom');
    const rmBtn   = tr.querySelector('.remove-row-btn');
    qtyIn?.addEventListener('input',   () => { recalcRow(tr); recalcAll(); });
    priceIn?.addEventListener('input',  () => { recalcRow(tr); recalcAll(); });
    uomSel?.addEventListener('change',  () => { lockQtyIfLot(tr); recalcRow(tr); recalcAll(); });
    rmBtn?.addEventListener('click',    () => { tr.remove(); recalcAll(); });
    addCatalogPicker(tr);
    lockQtyIfLot(tr);
    recalcRow(tr);
  });
  recalcAll();

  // ── Drag-to-reorder rows ──────────────────────────────────────────────────
  function initDragSort(tb) {
    let dragSrc = null;
    let handleDown = false;

    // Track whether the mousedown was on a drag handle
    tb.addEventListener('mousedown', e => {
      handleDown = !!e.target.closest('.drag-handle');
    });

    tb.addEventListener('dragstart', e => {
      if (!handleDown) { e.preventDefault(); return; }
      dragSrc = e.target.closest('tr');
      if (!dragSrc) { e.preventDefault(); return; }
      dragSrc.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', '');
    });

    tb.addEventListener('dragover', e => {
      if (!dragSrc) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const row = e.target.closest('tr');
      if (!row || row === dragSrc) return;
      const rect = row.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      if (e.clientY < mid) {
        tb.insertBefore(dragSrc, row);
      } else {
        row.after(dragSrc);
      }
    });

    tb.addEventListener('dragend', () => {
      dragSrc?.classList.remove('dragging');
      dragSrc = null;
      handleDown = false;
      recalcAll();
    });
  }

  // ── Template item sort: Inverter → Battery → Other → Labour/Transport ────
  function sortTemplateItems(items) {
    const rank = desc => {
      const d = (desc || '').toLowerCase();
      if (/inverter|charger/.test(d))          return 0;
      if (/battery|batteries/.test(d))          return 1;
      if (/solar panel|pv panel|module/.test(d)) return 2;
      if (/labour|labor|transport|delivery/.test(d)) return 9;
      return 5;
    };
    return items.slice().sort((a, b) => rank(a.description) - rank(b.description));
  }

  // ── Quick Build template loader ─────────────────────────────────────────
  const tmplSel = document.getElementById('template-select');
  const loadBtn = document.getElementById('load-template-btn');
  loadBtn?.addEventListener('click', async () => {
    const tid = tmplSel?.value;
    if (!tid) return;
    try {
      const res   = await fetch(`/api/template/${tid}`);
      const raw   = await res.json();
      const items = sortTemplateItems(raw);
      // Clear existing rows
      tbody.innerHTML = '';
      rowIndex = 0;
      items.forEach(item => {
        const tr = makeRow({
          description: item.description,
          uom:         item.uom || 'pc',
          qty:         item.qty || 1,
          unit_price:  item.sell_price || 0,
        });
        tbody.appendChild(tr);
      });
      recalcAll();
    } catch (e) {
      alert('Failed to load template: ' + e.message);
    }
  });

  // Init column resize + drag sort
  initColResize('line-items-table');
  initDragSort(tbody);
})();

// ── Balancing ratio sync (form page — costs entered as spend lines post-save) ─
(function () {
  const hRatio = document.getElementById('h_ratio');
  const dRatio = document.getElementById('d_ratio');
  if (!hRatio || !dRatio) return;

  function sync(changed, other) {
    const v = parseInt(changed.value) || 0;
    other.value = Math.max(0, 100 - v);
    recalcBalancing();
  }

  hRatio.addEventListener('input', () => sync(hRatio, dRatio));
  dRatio.addEventListener('input', () => sync(dRatio, hRatio));

  function recalcBalancing() {
    // On the form page we only have the quoted amount; costs are added later as spend lines.
    // Preview shows the split assuming zero costs so Hillary/Dennis can see their expected share.
    const quoted = parseFloat(document.getElementById('b_quoted')?.value || 0);
    const hr     = parseInt(hRatio.value) || 45;
    const dr     = parseInt(dRatio.value) || 55;
    const profit = quoted;   // estimate: no costs known yet
    const hShare = profit * hr / 100;
    const dShare = profit * dr / 100;
    const profEl = document.getElementById('b_profit_display');
    const hEl    = document.getElementById('b_h_share');
    const dEl    = document.getElementById('b_d_share');
    if (profEl) { profEl.textContent = 'UGX ' + fmt(profit); profEl.style.color = 'var(--accent-green)'; }
    if (hEl)    hEl.textContent = 'UGX ' + fmt(hShare);
    if (dEl)    dEl.textContent = 'UGX ' + fmt(dShare);
  }

  document.getElementById('b_quoted')?.addEventListener('input', recalcBalancing);
  recalcBalancing();
})();

// ── Receipt: auto-fill fields from linked quotation ──────────────────────────
(function () {
  const sel      = document.getElementById('receipt_quotation_id');
  const figEl    = document.getElementById('amount_fig');
  const nameEl   = document.querySelector('input[name="customer_name"]');
  const phoneEl  = document.querySelector('input[name="customer_phone"]');
  if (!sel) return;

  function fillFromSelected() {
    const opt = sel.options[sel.selectedIndex];
    if (!opt || !opt.value) return;
    const amt = parseFloat(opt.dataset.amount || 0);
    if (figEl && amt > 0) { figEl.value = amt; figEl.dispatchEvent(new Event('input')); }
    if (nameEl  && opt.dataset.customer) nameEl.value  = opt.dataset.customer;
    if (phoneEl && opt.dataset.phone)    phoneEl.value = opt.dataset.phone;
  }

  sel.addEventListener('change', fillFromSelected);
  // Auto-fill on page load if a quotation is pre-selected
  if (sel.value) fillFromSelected();
})();

// ── Receipt amount auto-balance ──────────────────────────────────────────────
(function () {
  const figEl  = document.getElementById('amount_fig');
  const paidEl = document.getElementById('amount_paid');
  const balEl  = document.getElementById('balance_display');
  if (!figEl || !paidEl) return;
  function updateBalance() {
    const fig  = parseFloat(figEl.value)  || 0;
    const paid = parseFloat(paidEl.value) || 0;
    if (balEl) balEl.textContent = 'UGX ' + fmt(fig - paid);
  }
  figEl.addEventListener('input',  updateBalance);
  paidEl.addEventListener('input', updateBalance);
  updateBalance();
})();
