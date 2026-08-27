/* ── Rincol Web ERP — Main JS ─────────────────────────────────────────── */

// ── Sidebar toggle (mobile) ─────────────────────────────────────────────────
document.getElementById('sidebarToggle')?.addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('sidebar-collapsed');
});

// ── Number formatting ────────────────────────────────────────────────────────
function fmt(n) {
  return Math.round(n).toLocaleString('en-US');
}

// ── Global money input — comma separators as you type ────────────────────────
// Usage: add class="money-input" to any text input that holds a currency amount.
// The raw numeric value (no commas) is submitted because commas are stripped
// on form submit via the event below.
(function () {
  function formatMoney(val) {
    // Allow digits and one decimal point only
    const raw = String(val).replace(/[^0-9.]/g, '');
    const parts = raw.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.slice(0, 2).join(parts.length > 1 ? '.' : '');
  }
  window.formatMoney = formatMoney;

  function applyFormatter(el) {
    el.addEventListener('input', function () {
      const pos = this.selectionStart;
      const oldLen = this.value.length;
      this.value = formatMoney(this.value);
      // Restore cursor roughly (comma insertions shift position)
      const delta = this.value.length - oldLen;
      this.setSelectionRange(pos + delta, pos + delta);
    });
  }

  // Apply to all existing .money-input elements on load
  document.querySelectorAll('.money-input').forEach(applyFormatter);

  // Also handle dynamically added elements (e.g. quotation line rows)
  const observer = new MutationObserver(mutations => {
    mutations.forEach(m => m.addedNodes.forEach(node => {
      if (node.nodeType !== 1) return;
      node.querySelectorAll?.('.money-input').forEach(applyFormatter);
      if (node.classList?.contains('money-input')) applyFormatter(node);
    }));
  });
  observer.observe(document.body, { childList: true, subtree: true });

  // Strip commas before every form submits so the server gets plain numbers
  document.addEventListener('submit', function (e) {
    e.target.querySelectorAll('.money-input').forEach(el => {
      el.value = el.value.replace(/,/g, '');
    });
  }, true);

  // Format initial values on page load
  document.querySelectorAll('.money-input').forEach(el => {
    if (el.value) el.value = formatMoney(el.value);
  });
})();

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
    const qty   = parseFloat(row.querySelector('.col-qty').value) || 0;
    const price = parseFloat((row.querySelector('.col-price').value || '').replace(/,/g, '')) || 0;
    const total = qty * price;
    const totalEl = row.querySelector('.col-total');
    totalEl.textContent = fmt(total);
    totalEl.dataset.value = total;
    updateMarkup(row, price);
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

  // ── Markup helper ─────────────────────────────────────────────────────────
  function updateMarkup(tr, sellPrice) {
    const mkDiv = tr.querySelector('.col-markup');
    if (!mkDiv) return;
    const buy = parseFloat(tr.dataset.buyPrice || 0);
    if (!buy || !sellPrice) { mkDiv.textContent = ''; return; }
    const val = sellPrice - buy;
    const pct = (val / buy * 100).toFixed(0);
    mkDiv.textContent = (val >= 0 ? '+' : '') + fmt(val) + ' (' + pct + '%)';
    mkDiv.style.color = val >= 0 ? '#a6e3a1' : '#f87171';
  }

  // ── Catalog autocomplete on description field ──────────────────────────────
  function addDescAutocomplete(tr) {
    const catalog = window.CATALOG_ITEMS || [];
    if (!catalog.length) return;
    const descIn = tr.querySelector('.col-desc');
    if (!descIn || descIn.dataset.acWired) return;
    descIn.dataset.acWired = '1';

    const dropdown = document.createElement('div');
    dropdown.style.cssText = [
      'position:absolute', 'z-index:9999', 'background:#1e293b',
      'border:1px solid #334155', 'border-radius:6px',
      'max-height:200px', 'overflow-y:auto', 'min-width:260px',
      'box-shadow:0 8px 24px rgba(0,0,0,.5)', 'display:none',
    ].join(';');
    document.body.appendChild(dropdown);

    function reposition() {
      const r = descIn.getBoundingClientRect();
      dropdown.style.top  = (r.bottom + window.scrollY + 2) + 'px';
      dropdown.style.left = r.left + 'px';
      dropdown.style.width = Math.max(r.width, 260) + 'px';
    }

    function fillFromItem(item) {
      descIn.value = item.name + (item.spec ? ' — ' + item.spec : '');
      tr.dataset.buyPrice = String(item.buy_price || 0);
      const uomSel  = tr.querySelector('.col-uom');
      const priceIn = tr.querySelector('.col-price');
      if (uomSel) {
        for (let i = 0; i < uomSel.options.length; i++) {
          if (uomSel.options[i].value === item.uom) { uomSel.selectedIndex = i; break; }
        }
        uomSel.dispatchEvent(new Event('change'));
      }
      if (priceIn) {
        priceIn.value = window.formatMoney(String(item.sell_price || 0));
        priceIn.dispatchEvent(new Event('input'));
      }
      dropdown.style.display = 'none';
    }

    function showMatches(q) {
      const matches = catalog.filter(item => {
        return (item.name + ' ' + (item.spec || '')).toLowerCase().includes(q);
      }).slice(0, 12);
      if (!matches.length) { dropdown.style.display = 'none'; return; }
      dropdown.innerHTML = matches.map((item, i) => {
        const label = item.name + (item.spec ? '<span style="color:#94a3b8"> — ' + item.spec + '</span>' : '');
        const price = '<span style="float:right;color:#a6e3a1">' + fmt(item.sell_price || 0) + '</span>';
        return '<div class="ac-item" data-idx="' + i + '" style="padding:6px 10px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.05);font-size:.82rem">' + label + price + '</div>';
      }).join('');
      reposition();
      dropdown.style.display = '';
      dropdown.querySelectorAll('.ac-item').forEach(el => {
        el.addEventListener('mousedown', e => { e.preventDefault(); fillFromItem(matches[+el.dataset.idx]); });
        el.addEventListener('mouseenter', () => { el.style.background = 'rgba(255,255,255,.07)'; });
        el.addEventListener('mouseleave', () => { el.style.background = ''; });
      });
    }

    descIn.addEventListener('input', function () {
      const q = this.value.toLowerCase().trim();
      if (q.length >= 2) showMatches(q);
      else dropdown.style.display = 'none';
    });
    descIn.addEventListener('blur', () => setTimeout(() => { dropdown.style.display = 'none'; }, 180));
    window.addEventListener('scroll', reposition, { passive: true });
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
      <td class="td-desc"><input type="text" name="desc[]" class="col-desc" value="${escHtml(data.description||data.desc||'')}"></td>
      <td class="td-uom"><select name="uom[]" class="col-uom">${uomOptions}</select></td>
      <td class="td-qty"><input type="number" name="qty[]" class="col-qty" value="${data.qty||1}" min="0.01" step="any"></td>
      <td class="td-price"><input type="text" inputmode="numeric" name="price[]" class="col-price money-input" value="${window.formatMoney(String(data.unit_price||data.price||0))}"><div class="col-markup"></div></td>
      <td class="col-total td-total" data-value="${(data.qty||1)*(data.unit_price||0)}">${fmt((data.qty||1)*(data.unit_price||0))}</td>
      <td class="td-delete text-center">
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

    if (data.buy_price != null) tr.dataset.buyPrice = String(data.buy_price);
    addDescAutocomplete(tr);
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
    // Look up buy price from catalog for markup display
    const descVal = tr.querySelector('.col-desc')?.value || '';
    if (descVal && window.CATALOG_ITEMS) {
      const match = window.CATALOG_ITEMS.find(item => {
        const full = item.name + (item.spec ? ' — ' + item.spec : '');
        return descVal === full || descVal.startsWith(item.name);
      });
      if (match) tr.dataset.buyPrice = String(match.buy_price || 0);
    }
    addDescAutocomplete(tr);
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

// Receipt auto-fill and balance logic is handled inline in templates/receipt/form.html

// ── Live search / filter helpers ─────────────────────────────────────────────
// liveSearch: text filter only.  liveFilter: text + one-or-more select dropdowns,
// all combined with AND — every non-empty filter must match for a row to show.
// No page ever has pagination, so filtering the already-rendered rows in place
// (no reload, no submit button) is always correct.
function _matchesFilterWord(text, f) {
  // Word-boundary match, not substring — "paid" must not match inside
  // "unpaid". Free-text search (q) stays substring-based; this is only for
  // dropdown values, which are known whole words/phrases.
  const escaped = f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp('\\b' + escaped + '\\b').test(text);
}
function _applyFilter(tbody, q, filters) {
  Array.from(tbody.rows).forEach(function (row) {
    if (row.cells.length <= 1) return;
    const text = row.textContent.toLowerCase();
    const matchesQ   = !q || text.includes(q);
    const matchesAll = filters.every(f => !f || _matchesFilterWord(text, f));
    row.style.display = (matchesQ && matchesAll) ? '' : 'none';
  });
}
function liveSearch(inputId, tbodyId) {
  const inp   = document.getElementById(inputId);
  const tbody = document.getElementById(tbodyId);
  if (!inp || !tbody) return;
  inp.addEventListener('input', function () {
    _applyFilter(tbody, this.value.toLowerCase().trim(), []);
  });
}
// selectIds: a single element id, or an array of ids (one page can combine
// several dropdowns — e.g. status + payment — with the same text search).
function liveFilter(inputId, selectIds, tbodyId) {
  const inp   = inputId ? document.getElementById(inputId) : null;
  const ids   = Array.isArray(selectIds) ? selectIds : [selectIds];
  const sels  = ids.filter(Boolean).map(id => document.getElementById(id)).filter(Boolean);
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  function apply() {
    const filters = sels.map(s => s.value.toLowerCase().trim());
    _applyFilter(tbody, inp ? inp.value.toLowerCase().trim() : '', filters);
  }
  inp?.addEventListener('input', apply);
  sels.forEach(s => s.addEventListener('change', apply));
}
