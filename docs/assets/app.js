/* Client-side interactivity for The Muir Family Tree */
(function () {
  const relRoot = document.body.getAttribute("data-rel-root") || ".";

  // 1. Theme Toggle
  const savedTheme = localStorage.getItem("muir_theme");
  if (savedTheme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : "dark";
      if (next === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
      localStorage.setItem("muir_theme", next);
    });
  }

  // 2. Global Instant Search
  const searchInput = document.getElementById("global-person-search");
  const searchResults = document.getElementById("global-search-results");
  if (searchInput && searchResults && window.FAMILY_DATA) {
    const peopleList = Object.values(window.FAMILY_DATA.people);

    searchInput.addEventListener("input", function () {
      const q = searchInput.value.trim().toLowerCase();
      if (!q) {
        searchResults.hidden = true;
        searchResults.innerHTML = "";
        return;
      }
      const tokens = q.split(/\s+/);
      const matches = [];
      for (let i = 0; i < peopleList.length; i++) {
        const p = peopleList[i];
        const hay = (p.name + " " + p.sn + " " + p.cn + " " + p.dates + " " + p.b + " " + p.d + " " + p.prof + " " + p.ref).toLowerCase();
        if (tokens.every(function (t) { return hay.indexOf(t) !== -1; })) {
          matches.push(p);
        }
      }
      matches.sort(function (a, b) {
        if (a.da !== b.da) return a.da ? -1 : 1;
        return a.sn.localeCompare(b.sn) || a.cn.localeCompare(b.cn);
      });

      const top = matches.slice(0, 15);
      if (top.length === 0) {
        searchResults.innerHTML = '<div class="search-item"><span class="search-item-meta">No matching people found.</span></div>';
      } else {
        searchResults.innerHTML = top.map(function (p) {
          const badge = p.da ? '<span class="badge badge-ancestor">★ Direct</span>' : '<span class="badge">Gen ' + p.gen + '</span>';
          const prof = p.prof ? " · " + p.prof : "";
          return '<a class="search-item" href="' + relRoot + '/people/' + p.id + '.html">' +
            '<div class="search-item-title"><span>' + p.sn + ', ' + p.cn + '</span>' + badge + '</div>' +
            '<div class="search-item-meta">' + (p.dates || "") + prof + '</div>' +
          '</a>';
        }).join("");
      }
      searchResults.hidden = false;
    });

    document.addEventListener("click", function (e) {
      if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.hidden = true;
      }
    });
  }

  // 3. Draw SVG Connecting Lines on 3-Generation Tree Pages
  const treeStage = document.getElementById("tree-stage");
  const svgOverlay = document.getElementById("tree-connectors-svg");

  function drawTreeConnectors() {
    if (!treeStage || !svgOverlay) return;
    const stageRect = treeStage.getBoundingClientRect();
    const scale = parseFloat(treeStage.getAttribute("data-zoom") || "1");
    const w = treeStage.scrollWidth;
    const h = treeStage.scrollHeight;
    svgOverlay.setAttribute("width", w);
    svgOverlay.setAttribute("height", h);
    svgOverlay.setAttribute("viewBox", "0 0 " + w + " " + h);

    const cards = treeStage.querySelectorAll(".tree-node-card[data-parent-node]");
    let pathsHtml = "";

    const accentMap = {
      "#FFFF99": "#d99b26",
      "#8080FF": "#4a5fd9",
      "#80FF80": "#2e9e5b",
      "#00FFCC": "#0d9488",
      "#FF6666": "#dc2626"
    };

    cards.forEach(function (childCard) {
      const parentId = childCard.getAttribute("data-parent-node");
      if (!parentId) return;
      const parentCard = document.getElementById(parentId);
      if (!parentCard) return;

      const pRect = parentCard.getBoundingClientRect();
      const cRect = childCard.getBoundingClientRect();

      const x1 = (pRect.left - stageRect.left + pRect.width / 2) / scale;
      const y1 = (pRect.bottom - stageRect.top) / scale;
      const x2 = (cRect.left - stageRect.left + cRect.width / 2) / scale;
      const y2 = (cRect.top - stageRect.top) / scale;
      const midY = y1 + (y2 - y1) * 0.5;

      const colorCode = childCard.getAttribute("data-accent") || "";
      const stroke = accentMap[colorCode] || "var(--connector-color)";

      const d = "M " + x1.toFixed(1) + " " + y1.toFixed(1) +
                " L " + x1.toFixed(1) + " " + midY.toFixed(1) +
                " L " + x2.toFixed(1) + " " + midY.toFixed(1) +
                " L " + x2.toFixed(1) + " " + y2.toFixed(1);
      pathsHtml += '<path d="' + d + '" fill="none" stroke="' + stroke + '" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>';
      pathsHtml += '<circle cx="' + x2.toFixed(1) + '" cy="' + y2.toFixed(1) + '" r="3.2" fill="' + stroke + '"/>';
    });

    svgOverlay.innerHTML = pathsHtml;
  }

  if (treeStage && svgOverlay) {
    window.addEventListener("load", drawTreeConnectors);
    window.addEventListener("resize", drawTreeConnectors);
    setTimeout(drawTreeConnectors, 60);

    let zoom = 1;
    const zoomInBtn = document.getElementById("tree-zoom-in");
    const zoomOutBtn = document.getElementById("tree-zoom-out");
    const zoomResetBtn = document.getElementById("tree-zoom-reset");

    function applyZoom(newZoom) {
      zoom = Math.max(0.5, Math.min(1.5, newZoom));
      treeStage.setAttribute("data-zoom", zoom.toString());
      treeStage.style.transform = "scale(" + zoom + ")";
      drawTreeConnectors();
    }

    if (zoomInBtn) zoomInBtn.addEventListener("click", function () { applyZoom(zoom + 0.12); });
    if (zoomOutBtn) zoomOutBtn.addEventListener("click", function () { applyZoom(zoom - 0.12); });
    if (zoomResetBtn) zoomResetBtn.addEventListener("click", function () { applyZoom(1); });
  }
})();
