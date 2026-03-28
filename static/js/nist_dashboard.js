/* ========================================================
   NIST SP 800-53 Mapping Dashboard - Visualization
   ======================================================== */

(function () {
  'use strict';

  var CHAPTER_COLORS = {
    1: '#1565C0', 2: '#00838F', 3: '#2E7D32',
    4: '#AD1457', 5: '#E65100', 6: '#4527A0'
  };

  var CHAPTER_NAMES = {
    1: '권한', 2: '인증', 3: '분리/격리',
    4: '통제', 5: '데이터', 6: '정보자산'
  };

  var GROUP_NAMES = {
    'LP': '최소 권한', 'IV': '신원 검증', 'IM': '식별자 관리',
    'AC': '계정 관리', 'MA': '다중요소 인증', 'EI': '외부인증수단',
    'DA': '단말인증', 'AU': '인증보호', 'AP': '인증정책',
    'AM': '인증수단', 'LI': '로그인', 'SG': '분리',
    'IS': '격리', 'IF': '정보흐름', 'EB': '외부경계',
    'CD': 'CDS', 'RA': '원격접속', 'SN': '세션',
    'WA': '무선망 접속', 'BC': '블루투스 연결', 'EK': '암호 키 관리',
    'EA': '암호 모듈 사용', 'DT': '데이터 전송', 'DU': '데이터 사용',
    'MD': '모바일 단말', 'DV': '하드웨어', 'IN': '정보시스템 구성요소'
  };

  var NIST_COLOR = '#78909C';
  var DATA = null;
  var GRAPH = null;

  document.addEventListener('DOMContentLoaded', function () {
    loadData();
  });

  /* ---- Data Loading ---- */
  function loadData() {
    var dataUrl = window.NIST_DATA_URL || '../data/nist_mapping.json';

    fetch(dataUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        DATA = data;
        initDashboard();
      })
      .catch(function (err) {
        console.error('Failed to load mapping data:', err);
        document.getElementById('graph-container').innerHTML =
          '<p style="padding:40px;text-align:center;color:#999;">매핑 데이터를 불러올 수 없습니다.</p>';
      });
  }

  function initDashboard() {
    updateStats();
    buildGraph();
    buildLegend();
    initFilters();
    initSearch();
    initZoomControls();
    initPanelClose();
  }

  /* ---- Stats ---- */
  function updateStats() {
    var meta = DATA.metadata;
    document.getElementById('stat-n2sf').textContent = meta.n2sf_controls_count;
    document.getElementById('stat-nist').textContent = meta.nist_controls_referenced;
    document.getElementById('stat-edges').textContent = meta.total_mappings;
    document.getElementById('stat-families').textContent = meta.nist_families_referenced + '/20';
  }

  /* ---- Graph ---- */
  function buildGraph() {
    var graphData = transformToGraphData();
    var container = document.getElementById('graph-container');
    var width = container.clientWidth;
    var height = container.clientHeight;

    var svg = d3.select('#nist-graph')
      .attr('width', width)
      .attr('height', height);

    svg.selectAll('*').remove();

    // Tooltip
    var tooltip = d3.select('body').selectAll('.graph-tooltip').data([0]);
    tooltip = tooltip.enter().append('div').attr('class', 'graph-tooltip')
      .style('display', 'none').merge(tooltip);

    // Zoom (Ctrl+scroll only, regular scroll passes through to page)
    var g = svg.append('g');
    var zoom = d3.zoom()
      .scaleExtent([0.3, 4])
      .filter(function (event) {
        // Allow programmatic zoom (from buttons)
        if (event.type === 'start' || event.type === 'zoom' || event.type === 'end') return true;
        // Block plain wheel — only allow Ctrl+wheel (or Cmd+wheel on Mac)
        if (event.type === 'wheel') return event.ctrlKey || event.metaKey;
        // Allow drag, double-click, touch gestures
        return !event.button;
      })
      .on('zoom', function (event) { g.attr('transform', event.transform); });
    svg.call(zoom);

    // Force simulation
    var simulation = d3.forceSimulation(graphData.nodes)
      .force('link', d3.forceLink(graphData.links).id(function (d) { return d.id; }).distance(180))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(function (d) { return d.radius + 8; }))
      .force('x', d3.forceX(width / 2).strength(0.04))
      .force('y', d3.forceY(height / 2).strength(0.04));

    // Links
    var link = g.append('g')
      .selectAll('line')
      .data(graphData.links)
      .enter().append('line')
      .attr('class', 'link-line')
      .attr('stroke', function (d) { return d.color || '#999'; })
      .attr('stroke-width', function (d) { return Math.max(1, Math.min(d.weight, 8)); });

    // Nodes
    var node = g.append('g')
      .selectAll('g')
      .data(graphData.nodes)
      .enter().append('g')
      .attr('class', 'node-group')
      .call(d3.drag()
        .on('start', function (event, d) {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', function (event, d) { d.fx = event.x; d.fy = event.y; })
        .on('end', function (event, d) {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    // N2SF nodes: circles
    node.filter(function (d) { return d.type === 'n2sf'; })
      .append('circle')
      .attr('r', function (d) { return d.radius; })
      .attr('fill', function (d) { return d.color; })
      .attr('stroke', 'white')
      .attr('stroke-width', 2);

    // NIST nodes: rounded rectangles
    node.filter(function (d) { return d.type === 'nist'; })
      .append('rect')
      .attr('width', function (d) { return d.radius * 2; })
      .attr('height', function (d) { return d.radius * 1.4; })
      .attr('x', function (d) { return -d.radius; })
      .attr('y', function (d) { return -d.radius * 0.7; })
      .attr('rx', 4)
      .attr('fill', NIST_COLOR)
      .attr('stroke', 'white')
      .attr('stroke-width', 2);

    // Labels
    node.append('text')
      .attr('class', 'node-label')
      .attr('dy', function (d) { return d.type === 'n2sf' ? '0.35em' : '0.1em'; })
      .text(function (d) { return d.id; });

    node.append('text')
      .attr('class', 'node-sublabel')
      .attr('dy', function (d) { return d.type === 'n2sf' ? (d.radius + 12) + 'px' : '1.2em'; })
      .text(function (d) { return d.label; });

    // Hover
    node.on('mouseover', function (event, d) {
      tooltip
        .style('display', 'block')
        .html(getTooltipHtml(d))
        .style('left', (event.pageX + 12) + 'px')
        .style('top', (event.pageY - 10) + 'px');
      highlightConnected(d, node, link);
    })
    .on('mousemove', function (event) {
      tooltip
        .style('left', (event.pageX + 12) + 'px')
        .style('top', (event.pageY - 10) + 'px');
    })
    .on('mouseout', function () {
      tooltip.style('display', 'none');
      clearHighlight(node, link);
    });

    // Click -> detail panel
    node.on('click', function (event, d) {
      event.stopPropagation();
      showDetailPanel(d);
    });

    svg.on('click', function () {
      hideDetailPanel();
    });

    // Tick
    simulation.on('tick', function () {
      link
        .attr('x1', function (d) { return d.source.x; })
        .attr('y1', function (d) { return d.source.y; })
        .attr('x2', function (d) { return d.target.x; })
        .attr('y2', function (d) { return d.target.y; });

      node.attr('transform', function (d) { return 'translate(' + d.x + ',' + d.y + ')'; });
    });

    GRAPH = { svg: svg, g: g, zoom: zoom, simulation: simulation, node: node, link: link, data: graphData };

    // Resize handler
    window.addEventListener('resize', function () {
      var w = container.clientWidth;
      var h = container.clientHeight;
      svg.attr('width', w).attr('height', h);
      simulation.force('center', d3.forceCenter(w / 2, h / 2));
      simulation.alpha(0.1).restart();
    });
  }

  function transformToGraphData() {
    var nodes = [];
    var links = [];
    var linkMap = {}; // "n2sf_group|nist_family" -> { weight, highCount, ... }

    // Aggregate mappings to group-family level
    var groupInfo = {}; // group_id -> { chapter, name, controlCount }
    DATA.mappings.forEach(function (m) {
      var gid = m.n2sf_group;
      if (!groupInfo[gid]) {
        groupInfo[gid] = { chapter: m.n2sf_chapter, name: '', count: 0 };
      }
      groupInfo[gid].count++;

      (m.nist_mappings || []).forEach(function (nm) {
        var nistCtrl = DATA.nist_controls[nm.nist_id];
        var famId = nistCtrl ? nistCtrl.family_id : nm.nist_id.replace(/-\d+.*/, '').toUpperCase();

        var key = gid + '|' + famId;
        if (!linkMap[key]) {
          linkMap[key] = { source: gid, target: 'NIST-' + famId, weight: 0, high: 0, medium: 0, low: 0 };
        }
        linkMap[key].weight++;
        linkMap[key][nm.relevance || 'medium']++;
      });
    });

    // N2SF group nodes
    Object.keys(groupInfo).forEach(function (gid) {
      var info = groupInfo[gid];
      nodes.push({
        id: gid,
        type: 'n2sf',
        label: CHAPTER_NAMES[info.chapter] || '',
        chapter: info.chapter,
        color: CHAPTER_COLORS[info.chapter] || '#666',
        controlCount: info.count,
        radius: Math.max(18, Math.min(8 + info.count * 0.8, 35)),
      });
    });

    // NIST family nodes
    var nistFamilyMappingCount = {};
    Object.keys(linkMap).forEach(function (key) {
      var famId = linkMap[key].target.replace('NIST-', '');
      nistFamilyMappingCount[famId] = (nistFamilyMappingCount[famId] || 0) + linkMap[key].weight;
    });

    DATA.nist_families.forEach(function (fam) {
      var count = nistFamilyMappingCount[fam.family_id] || 0;
      if (count > 0) {
        nodes.push({
          id: 'NIST-' + fam.family_id,
          type: 'nist',
          label: fam.family_title,
          familyId: fam.family_id,
          mappingCount: count,
          radius: Math.max(20, Math.min(12 + count * 0.3, 40)),
        });
      }
    });

    // Links
    Object.keys(linkMap).forEach(function (key) {
      var lk = linkMap[key];
      var chap = groupInfo[lk.source] ? groupInfo[lk.source].chapter : 1;
      links.push({
        source: lk.source,
        target: lk.target,
        weight: Math.sqrt(lk.weight) * 1.5,
        rawWeight: lk.weight,
        high: lk.high,
        medium: lk.medium,
        low: lk.low,
        color: CHAPTER_COLORS[chap] || '#999',
        chapter: chap,
      });
    });

    return { nodes: nodes, links: links };
  }

  function getTooltipHtml(d) {
    if (d.type === 'n2sf') {
      return '<strong>' + d.id + '</strong> ' + (GROUP_NAMES[d.id] || '') + '<br>' +
        '제' + d.chapter + '장 ' + CHAPTER_NAMES[d.chapter] + ' · ' + d.controlCount + '개 통제항목';
    } else {
      return '<strong>' + d.id.replace('NIST-', '') + '</strong><br>' +
        d.label + '<br>' + d.mappingCount + '개 매핑';
    }
  }

  function highlightConnected(d, nodeSelection, linkSelection) {
    var connected = new Set();
    connected.add(d.id);

    linkSelection.each(function (l) {
      var srcId = typeof l.source === 'object' ? l.source.id : l.source;
      var tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (srcId === d.id) connected.add(tgtId);
      if (tgtId === d.id) connected.add(srcId);
    });

    nodeSelection.classed('dimmed', function (n) { return !connected.has(n.id); });
    linkSelection.classed('dimmed', function (l) {
      var srcId = typeof l.source === 'object' ? l.source.id : l.source;
      var tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      return srcId !== d.id && tgtId !== d.id;
    });
    linkSelection.classed('highlighted', function (l) {
      var srcId = typeof l.source === 'object' ? l.source.id : l.source;
      var tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      return srcId === d.id || tgtId === d.id;
    });
  }

  function clearHighlight(nodeSelection, linkSelection) {
    nodeSelection.classed('dimmed', false);
    linkSelection.classed('dimmed', false).classed('highlighted', false);
  }

  /* ---- Detail Panel ---- */
  function showDetailPanel(d) {
    var panel = document.getElementById('detail-panel');
    var title = document.getElementById('panel-title');
    var content = document.getElementById('panel-content');

    panel.classList.remove('collapsed');

    if (d.type === 'n2sf') {
      title.textContent = d.id + ' ' + (GROUP_NAMES[d.id] || '') + ' 매핑 상세';
      content.innerHTML = buildN2sfPanelHtml(d);
    } else {
      title.textContent = d.id.replace('NIST-', '') + ' 패밀리 매핑';
      content.innerHTML = buildNistPanelHtml(d);
    }
  }

  function hideDetailPanel() {
    document.getElementById('detail-panel').classList.add('collapsed');
  }

  function nistUrl(nistId) {
    var parts = nistId.toLowerCase().split('-');
    var family = parts[0];
    var control = parts.slice(0, 2).join('-');
    return 'https://csf.tools/reference/nist-sp-800-53/r5/' + family + '/' + control + '/';
  }

  function n2sfUrl(n2sfId) {
    var basePath = (window.NIST_DATA_URL || '').replace('data/nist_mapping.json', '');
    return basePath + 'controls/' + n2sfId.toLowerCase() + '.html';
  }

  function buildN2sfPanelHtml(d) {
    var html = '<p class="panel-node-id">' + d.id + ' ' + (GROUP_NAMES[d.id] || '') + '</p>';
    html += '<p class="panel-node-name">제' + d.chapter + '장 ' + CHAPTER_NAMES[d.chapter] + ' · ' + d.controlCount + '개 통제항목</p>';

    // Find all controls in this group
    var groupMappings = DATA.mappings.filter(function (m) { return m.n2sf_group === d.id; });

    groupMappings.forEach(function (m) {
      html += '<div class="panel-section-title"><a href="' + n2sfUrl(m.n2sf_id) + '" class="panel-link">' + m.n2sf_id + '</a> ' + (m.n2sf_name || '') + '</div>';
      (m.nist_mappings || []).forEach(function (nm) {
        var nistCtrl = DATA.nist_controls[nm.nist_id];
        var nistTitle = nistCtrl ? nistCtrl.title : '';
        var nistProse = nistCtrl ? (nistCtrl.prose || '') : '';
        html += '<div class="panel-mapping-item">' +
          '<a href="' + nistUrl(nm.nist_id) + '" target="_blank" rel="noopener" class="panel-mapping-id">' + nm.nist_id + ' &#x2197;</a>' +
          '<span class="relevance-tag ' + nm.relevance + '">' + nm.relevance + '</span>' +
          (nistTitle ? '<div class="panel-mapping-title">' + nistTitle + '</div>' : '') +
          (nistProse ? '<div class="panel-mapping-prose">' + nistProse + '</div>' : '') +
          (nm.rationale ? '<div class="panel-mapping-rationale">' + nm.rationale + '</div>' : '') +
          '</div>';
      });
    });

    return html;
  }

  function buildNistPanelHtml(d) {
    var famId = d.familyId;
    var html = '<p class="panel-node-id">' + famId + '</p>';
    html += '<p class="panel-node-name">' + d.label + ' · ' + d.mappingCount + '개 매핑</p>';

    // Find all N2SF controls mapped to this family
    var mapped = [];
    DATA.mappings.forEach(function (m) {
      (m.nist_mappings || []).forEach(function (nm) {
        var nistCtrl = DATA.nist_controls[nm.nist_id];
        var fid = nistCtrl ? nistCtrl.family_id : '';
        if (fid === famId) {
          mapped.push({
            n2sf_id: m.n2sf_id,
            n2sf_name: m.n2sf_name || '',
            n2sf_group: m.n2sf_group,
            nist_id: nm.nist_id,
            relevance: nm.relevance,
            rationale: nm.rationale,
          });
        }
      });
    });

    // Group by NIST control
    var byNist = {};
    mapped.forEach(function (item) {
      if (!byNist[item.nist_id]) byNist[item.nist_id] = [];
      byNist[item.nist_id].push(item);
    });

    Object.keys(byNist).sort().forEach(function (nistId) {
      var nistCtrl = DATA.nist_controls[nistId];
      var nistProse = nistCtrl ? (nistCtrl.prose || '') : '';
      html += '<div class="panel-section-title"><a href="' + nistUrl(nistId) + '" target="_blank" rel="noopener" class="panel-link">' + nistId + ' &#x2197;</a> ' + (nistCtrl ? nistCtrl.title : '') + '</div>';
      if (nistProse) html += '<div class="panel-nist-prose">' + nistProse + '</div>';
      byNist[nistId].forEach(function (item) {
        html += '<div class="panel-mapping-item">' +
          '<a href="' + n2sfUrl(item.n2sf_id) + '" class="panel-mapping-id">' + item.n2sf_id + '</a>' +
          '<span class="relevance-tag ' + item.relevance + '">' + item.relevance + '</span>' +
          '<div class="panel-mapping-title">' + item.n2sf_name + '</div>' +
          (item.rationale ? '<div class="panel-mapping-rationale">' + item.rationale + '</div>' : '') +
          '</div>';
      });
    });

    return html;
  }

  function initPanelClose() {
    document.getElementById('panel-close').addEventListener('click', function (e) {
      e.stopPropagation();
      hideDetailPanel();
    });
    // Start collapsed
    document.getElementById('detail-panel').classList.add('collapsed');
  }

  /* ---- Legend ---- */
  function buildLegend() {
    var html = '<div class="legend-title">범례</div>';

    // N2SF chapters
    Object.keys(CHAPTER_COLORS).forEach(function (ch) {
      html += '<div class="legend-row">' +
        '<span class="legend-dot" style="background:' + CHAPTER_COLORS[ch] + '"></span>' +
        '<span>제' + ch + '장 ' + CHAPTER_NAMES[ch] + '</span></div>';
    });

    html += '<div class="legend-row" style="margin-top:6px;">' +
      '<span class="legend-rect"></span>' +
      '<span>NIST 패밀리</span></div>';

    document.getElementById('graph-legend').innerHTML = html;
  }

  /* ---- Filters ---- */
  function initFilters() {
    // Chapter filters
    document.querySelectorAll('[data-chapter]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var ch = btn.dataset.chapter;
        if (ch === 'ALL') {
          document.querySelectorAll('[data-chapter]').forEach(function (b) { b.classList.remove('active'); });
          btn.classList.add('active');
        } else {
          document.querySelector('[data-chapter="ALL"]').classList.remove('active');
          btn.classList.toggle('active');
          if (!document.querySelectorAll('[data-chapter].active').length) {
            document.querySelector('[data-chapter="ALL"]').classList.add('active');
          }
        }
        applyFilters();
      });
    });

    // Relevance filters
    document.querySelectorAll('.relevance-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var rel = btn.dataset.relevance;
        if (rel === 'ALL') {
          document.querySelectorAll('.relevance-btn').forEach(function (b) { b.classList.remove('active'); });
          btn.classList.add('active');
        } else {
          document.querySelector('.relevance-btn[data-relevance="ALL"]').classList.remove('active');
          btn.classList.toggle('active');
          if (!document.querySelectorAll('.relevance-btn.active').length) {
            document.querySelector('.relevance-btn[data-relevance="ALL"]').classList.add('active');
          }
        }
        applyFilters();
      });
    });
  }

  function applyFilters() {
    if (!GRAPH) return;

    // Get active chapter filters
    var activeChapters = [];
    document.querySelectorAll('[data-chapter].active').forEach(function (b) {
      activeChapters.push(b.dataset.chapter);
    });
    var showAllChapters = activeChapters.indexOf('ALL') !== -1 || activeChapters.length === 0;

    // Get active relevance filters
    var activeRelevance = [];
    document.querySelectorAll('.relevance-btn.active').forEach(function (b) {
      activeRelevance.push(b.dataset.relevance);
    });
    var showAllRelevance = activeRelevance.indexOf('ALL') !== -1 || activeRelevance.length === 0;

    // Find visible N2SF groups
    var visibleN2sf = new Set();
    GRAPH.data.nodes.forEach(function (n) {
      if (n.type === 'n2sf') {
        if (showAllChapters || activeChapters.indexOf(String(n.chapter)) !== -1) {
          visibleN2sf.add(n.id);
        }
      }
    });

    // Find visible links
    var visibleNist = new Set();
    GRAPH.link.each(function (l) {
      var srcId = typeof l.source === 'object' ? l.source.id : l.source;
      if (!visibleN2sf.has(srcId)) return;

      if (showAllRelevance) {
        visibleNist.add(typeof l.target === 'object' ? l.target.id : l.target);
        return;
      }

      var hasRelevance = false;
      activeRelevance.forEach(function (r) {
        if (l[r] > 0) hasRelevance = true;
      });
      if (hasRelevance) {
        visibleNist.add(typeof l.target === 'object' ? l.target.id : l.target);
      }
    });

    // Apply visibility
    GRAPH.node.style('display', function (n) {
      if (n.type === 'n2sf') return visibleN2sf.has(n.id) ? null : 'none';
      return visibleNist.has(n.id) ? null : 'none';
    });

    GRAPH.link.style('display', function (l) {
      var srcId = typeof l.source === 'object' ? l.source.id : l.source;
      var tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (!visibleN2sf.has(srcId) || !visibleNist.has(tgtId)) return 'none';

      if (showAllRelevance) return null;
      var hasRelevance = false;
      activeRelevance.forEach(function (r) { if (l[r] > 0) hasRelevance = true; });
      return hasRelevance ? null : 'none';
    });
  }

  /* ---- Search ---- */
  function initSearch() {
    var searchBox = document.getElementById('nist-search');
    if (!searchBox) return;

    searchBox.addEventListener('input', function () {
      var query = searchBox.value.trim().toUpperCase();

      if (!query) {
        clearHighlight(GRAPH.node, GRAPH.link);
        return;
      }

      var matched = new Set();
      GRAPH.data.nodes.forEach(function (n) {
        var searchId = n.id.replace('NIST-', '');
        if (searchId.indexOf(query) !== -1 || (n.label && n.label.toUpperCase().indexOf(query) !== -1)) {
          matched.add(n.id);
        }
      });

      if (matched.size === 0) {
        clearHighlight(GRAPH.node, GRAPH.link);
        return;
      }

      // Also include connected nodes
      var connected = new Set(matched);
      GRAPH.link.each(function (l) {
        var srcId = typeof l.source === 'object' ? l.source.id : l.source;
        var tgtId = typeof l.target === 'object' ? l.target.id : l.target;
        if (matched.has(srcId)) connected.add(tgtId);
        if (matched.has(tgtId)) connected.add(srcId);
      });

      GRAPH.node.classed('dimmed', function (n) { return !connected.has(n.id); });
      GRAPH.link.classed('dimmed', function (l) {
        var srcId = typeof l.source === 'object' ? l.source.id : l.source;
        var tgtId = typeof l.target === 'object' ? l.target.id : l.target;
        return !matched.has(srcId) && !matched.has(tgtId);
      });
    });
  }

  /* ---- Zoom Controls ---- */
  function initZoomControls() {
    document.getElementById('zoom-in').addEventListener('click', function () {
      GRAPH.svg.transition().duration(300).call(GRAPH.zoom.scaleBy, 1.4);
    });
    document.getElementById('zoom-out').addEventListener('click', function () {
      GRAPH.svg.transition().duration(300).call(GRAPH.zoom.scaleBy, 0.7);
    });
    document.getElementById('zoom-reset').addEventListener('click', function () {
      GRAPH.svg.transition().duration(500).call(GRAPH.zoom.transform, d3.zoomIdentity);
    });
  }

})();
