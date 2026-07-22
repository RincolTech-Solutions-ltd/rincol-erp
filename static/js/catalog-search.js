/**
 * initCatalogSearch(opts)
 *
 * Wires up a native <datalist>-backed text input so selecting or typing a
 * matching label fires a callback with the full item object.
 *
 * opts.inputId  {string}   — id of the <input type="text" list="...">
 * opts.items    {Array}    — [{label: string, ...rest}]  label must match <datalist> values
 * opts.onSelect {Function} — called with the matched item object, or null when cleared
 *
 * Example
 *   initCatalogSearch({
 *     inputId: 'panel-search',
 *     items: [{label: 'Hame 550Wp', wp: 550, voc: 40.5, isc: 13.1, price: 420000}],
 *     onSelect: function(item) { if (item) setVal('panel_wp', item.wp); }
 *   });
 */
function initCatalogSearch(opts) {
  var el = document.getElementById(opts.inputId);
  if (!el) { console.warn('initCatalogSearch: element not found:', opts.inputId); return; }

  var byLabel = {};
  (opts.items || []).forEach(function(it) { byLabel[it.label] = it; });

  function apply() {
    opts.onSelect(byLabel[el.value.trim()] || null);
  }

  el.addEventListener('change', apply);
  el.addEventListener('input',  apply);
}
