// Filters for Notion databases rendered as cards (.db-cards, see DB_AS_CARDS in
// _tools/notion2jekyll.py). Adds a search box and tag buttons above each grid.
// - Search matches any text on a card.
// - "Type" tags (the card subtitle): a card matches if it has ANY selected type.
// - Other tag groups (e.g. "What they provide"): a card must have ALL selected tags.
// Without JS the cards simply all show.
(function () {
  var grids = document.querySelectorAll(".db-cards");
  if (!grids.length) return;

  function norm(s) { return (s || "").replace(/\s+/g, " ").trim().toLowerCase(); }

  grids.forEach(function (grid, gi) {
    var cards = Array.prototype.slice.call(grid.querySelectorAll(".db-card"));
    if (cards.length < 4) return;

    // Collect tag groups from the cards: [{name, any, values: [{text, cls}]}]
    var groups = [];
    function group(name, any) {
      for (var i = 0; i < groups.length; i++) if (groups[i].name === name) return groups[i];
      var g = { name: name, any: any, values: [], seen: {} };
      groups.push(g);
      return g;
    }
    cards.forEach(function (card) {
      card._tags = {};
      card._text = norm(card.textContent);
      card.querySelectorAll(".db-card-type .tag").forEach(function (t) {
        add(card, group("Type", true), t);
      });
      card.querySelectorAll(".db-card-tags").forEach(function (box) {
        var label = box.previousElementSibling && box.previousElementSibling.classList.contains("db-card-label")
          ? box.previousElementSibling.textContent.trim() : "Tags";
        box.querySelectorAll(".tag").forEach(function (t) { add(card, group(label, false), t); });
      });
    });
    function add(card, g, el) {
      var text = el.textContent.trim(), key = g.name + "|" + text;
      card._tags[key] = true;
      if (!g.seen[text]) {
        g.seen[text] = true;
        g.values.push({ text: text, cls: el.className, key: key });
      }
    }

    // Build the filter bar
    var bar = document.createElement("div");
    bar.className = "db-filter";
    var id = "db-filter-" + gi;
    bar.innerHTML =
      '<label class="db-filter-search" for="' + id + '-q"><span>Filter</span>' +
      '<input type="search" id="' + id + '-q" placeholder="Search name, area, notes…" autocomplete="off"></label>';
    var selected = {};
    groups.forEach(function (g) {
      if (g.values.length < 2) return;
      var row = document.createElement("div");
      row.className = "db-filter-group";
      row.setAttribute("role", "group");
      row.setAttribute("aria-label", g.name);
      row.innerHTML = '<span class="db-filter-label">' + g.name + (g.any ? "" : " (all of)") + "</span>";
      g.values.forEach(function (v) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = v.cls + " db-filter-chip";
        b.textContent = v.text;
        b.setAttribute("aria-pressed", "false");
        b.addEventListener("click", function () {
          var on = b.getAttribute("aria-pressed") !== "true";
          b.setAttribute("aria-pressed", on ? "true" : "false");
          if (on) selected[v.key] = g; else delete selected[v.key];
          apply();
        });
        row.appendChild(b);
      });
      bar.appendChild(row);
    });
    var foot = document.createElement("div");
    foot.className = "db-filter-foot";
    foot.innerHTML = '<span class="db-filter-count" aria-live="polite"></span>' +
      '<button type="button" class="db-filter-clear" hidden>Clear filters</button>';
    bar.appendChild(foot);
    var empty = document.createElement("p");
    empty.className = "db-filter-empty";
    empty.hidden = true;
    empty.textContent = "No matches. Try fewer filters.";
    grid.parentNode.insertBefore(bar, grid);
    grid.parentNode.insertBefore(empty, grid.nextSibling);

    var input = bar.querySelector("input");
    var count = foot.querySelector(".db-filter-count");
    var clear = foot.querySelector(".db-filter-clear");
    input.addEventListener("input", apply);
    clear.addEventListener("click", function () {
      input.value = "";
      selected = {};
      bar.querySelectorAll(".db-filter-chip").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      apply();
      input.focus();
    });

    function apply() {
      var q = norm(input.value), keys = Object.keys(selected), shown = 0;
      cards.forEach(function (card) {
        var ok = !q || card._text.indexOf(q) !== -1;
        if (ok && keys.length) {
          groups.forEach(function (g) {
            if (!ok) return;
            var mine = keys.filter(function (k) { return selected[k] === g; });
            if (!mine.length) return;
            ok = g.any ? mine.some(function (k) { return card._tags[k]; })
                       : mine.every(function (k) { return card._tags[k]; });
          });
        }
        card.hidden = !ok;
        if (ok) shown++;
      });
      var filtering = q || keys.length;
      count.textContent = filtering ? "Showing " + shown + " of " + cards.length : cards.length + " listed";
      clear.hidden = !filtering;
      empty.hidden = shown > 0;
    }
    apply();
  });
})();
