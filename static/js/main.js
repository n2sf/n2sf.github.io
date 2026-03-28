/* ========================================================
   N2SF Security Controls Matrix - Interactions
   ======================================================== */

document.addEventListener('DOMContentLoaded', function () {
  initFilters();
  initSearch();
  initSidebarHighlight();
});


/* ---- Classification Filter (Matrix Page) ---- */
function initFilters() {
  const filterBtns = document.querySelectorAll('.filter-btn[data-filter]');
  if (!filterBtns.length) return;

  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      const filter = btn.dataset.filter;

      // Toggle active state
      if (filter === 'ALL') {
        filterBtns.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
      } else {
        document.querySelector('.filter-btn[data-filter="ALL"]').classList.remove('active');
        btn.classList.toggle('active');

        // If no filter is active, activate ALL
        var anyActive = document.querySelectorAll('.filter-btn.active');
        if (!anyActive.length) {
          document.querySelector('.filter-btn[data-filter="ALL"]').classList.add('active');
        }
      }

      applyFilters();
    });
  });
}

function applyFilters() {
  var activeFilters = [];
  document.querySelectorAll('.filter-btn.active').forEach(function (btn) {
    activeFilters.push(btn.dataset.filter);
  });

  var showAll = activeFilters.indexOf('ALL') !== -1 || activeFilters.length === 0;
  var cells = document.querySelectorAll('.matrix-cell');

  cells.forEach(function (cell) {
    if (showAll) {
      cell.classList.remove('hidden');
      return;
    }

    var show = false;
    activeFilters.forEach(function (f) {
      if (cell.dataset[f.toLowerCase()] === 'true') {
        show = true;
      }
    });

    if (show) {
      cell.classList.remove('hidden');
    } else {
      cell.classList.add('hidden');
    }
  });

  // Hide sub-groups where all children are hidden
  document.querySelectorAll('.matrix-sub-group').forEach(function (grp) {
    var hasVisible = grp.querySelector('.matrix-cell:not(.hidden)');
    grp.classList.toggle('hidden', !hasVisible);
  });

  // Update visible count
  var countEl = document.getElementById('visible-count');
  if (countEl) {
    var visible = document.querySelectorAll('.matrix-cell:not(.hidden)').length;
    countEl.textContent = visible;
  }

  // Hide empty columns and dim their group headers
  var columns = document.querySelectorAll('.matrix-column');
  var groupCells = document.querySelectorAll('.matrix-group-cell');
  columns.forEach(function (col, i) {
    var hasVisible = col.querySelector('.matrix-cell:not(.hidden)');
    col.classList.toggle('column-empty', !hasVisible);
    if (groupCells[i]) {
      groupCells[i].classList.toggle('column-empty', !hasVisible);
    }
  });
}


/* ---- Search (Controls List Page) ---- */
function initSearch() {
  var searchBox = document.getElementById('controls-search');
  if (!searchBox) return;

  searchBox.addEventListener('input', function () {
    var query = searchBox.value.toLowerCase().trim();
    var rows = document.querySelectorAll('.controls-table tbody tr');

    rows.forEach(function (row) {
      var text = row.textContent.toLowerCase();
      row.style.display = text.indexOf(query) !== -1 ? '' : 'none';
    });

    // Update count
    var countEl = document.getElementById('search-count');
    if (countEl) {
      var visible = 0;
      rows.forEach(function (r) { if (r.style.display !== 'none') visible++; });
      countEl.textContent = visible;
    }
  });
}


/* ---- Sidebar Active Highlight ---- */
function initSidebarHighlight() {
  var currentPath = window.location.pathname;
  var links = document.querySelectorAll('.sidebar-group');

  links.forEach(function (link) {
    var href = link.getAttribute('href');
    if (href && currentPath.indexOf(href.replace(/^\.\.\//, '')) !== -1) {
      link.classList.add('active');
    }
  });
}
