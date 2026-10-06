// Header behaviour: /guide dropdown, colour theme + text size toggles, and
// click-to-zoom for images. Everything degrades without JS: the dropdown is a
// <details>, the toggles stay hidden, and images link to the full-size file.
(function () {
  var root = document.documentElement;

  function store(key, value) {
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch (e) { /* storage unavailable: setting lasts for this page only */ }
  }

  /* ---- /guide dropdown: close on outside click or Escape ---- */
  document.addEventListener("click", function (e) {
    document.querySelectorAll(".dropdown details[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".dropdown details[open]").forEach(function (d) {
      d.removeAttribute("open");
      d.querySelector("summary").focus();
    });
  });

  /* ---- /guide dropdown: full-width panel when the nav has wrapped under the logo ---- */
  var menu = document.querySelector(".menu");
  var logo = document.querySelector(".menu .logo");
  var guideSummary = document.querySelector(".dropdown summary");
  function layoutMenu() {
    if (!menu || !logo || !guideSummary) return;
    menu.classList.remove("menu-stacked");
    var stacked = guideSummary.getBoundingClientRect().top >= logo.getBoundingClientRect().bottom;
    menu.classList.toggle("menu-stacked", stacked);
  }
  layoutMenu();
  window.addEventListener("resize", layoutMenu);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(layoutMenu);
  document.querySelectorAll(".dropdown details").forEach(function (d) {
    d.addEventListener("toggle", layoutMenu);
  });

  /* ---- light / dark toggle ---- */
  var themeBtn = document.getElementById("theme-toggle");
  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  function currentTheme() {
    return root.getAttribute("data-theme") || (systemDark.matches ? "dark" : "light");
  }
  function renderTheme() {
    var dark = currentTheme() === "dark";
    themeBtn.textContent = dark ? "☀︎" : "☾︎";
    themeBtn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    themeBtn.title = themeBtn.getAttribute("aria-label");
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      store("theme", next);
      renderTheme();
    });
    systemDark.addEventListener("change", renderTheme);
    renderTheme();
  }

  /* ---- text size toggle: default -> large -> larger -> default ---- */
  var SIZES = [
    { key: null, label: "aA", name: "default" },
    { key: "l", label: "aA+", name: "large" },
    { key: "xl", label: "aA++", name: "larger" }
  ];
  var fontBtn = document.getElementById("font-toggle");
  function sizeIndex() {
    var k = root.getAttribute("data-font-size");
    for (var i = 0; i < SIZES.length; i++) if (SIZES[i].key === k) return i;
    return 0;
  }
  function renderSize() {
    var s = SIZES[sizeIndex()];
    fontBtn.textContent = s.label;
    fontBtn.setAttribute("aria-label", "Text size: " + s.name + ". Click to change.");
    fontBtn.title = "Text size: " + s.name;
  }
  if (fontBtn) {
    fontBtn.addEventListener("click", function () {
      var next = SIZES[(sizeIndex() + 1) % SIZES.length];
      if (next.key) root.setAttribute("data-font-size", next.key);
      else root.removeAttribute("data-font-size");
      store("font-size", next.key);
      renderSize();
      layoutMenu();
    });
    renderSize();
  }

  /* ---- image zoom ---- */
  var images = document.querySelectorAll("main figure.image img, main td img, main .column img, main p > img");
  if (!images.length || typeof HTMLDialogElement === "undefined") return;

  var dialog = document.createElement("dialog");
  dialog.className = "lightbox";
  dialog.setAttribute("aria-label", "Image viewer");
  dialog.innerHTML =
    '<button type="button" class="lightbox-close" aria-label="Close">×</button>' +
    '<div class="lightbox-stage"><img alt=""></div>' +
    '<p class="lightbox-hint">click image to zoom · esc to close</p>';
  document.body.appendChild(dialog);
  var stage = dialog.querySelector(".lightbox-stage");
  var big = stage.querySelector("img");

  function open(img) {
    big.src = img.currentSrc || img.src;
    big.alt = img.alt;
    dialog.classList.remove("zoomed");
    dialog.showModal();
  }
  images.forEach(function (img) {
    img.classList.add("zoomable");
    var link = img.closest("a");
    (link || img).addEventListener("click", function (e) {
      e.preventDefault();
      open(img);
    });
    if (!link) {
      img.tabIndex = 0;
      img.setAttribute("role", "button");
      img.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(img); }
      });
    }
  });

  // Click the image to toggle between fit-to-screen and full size, keeping
  // the clicked point under the cursor.
  big.addEventListener("click", function (e) {
    var rect = big.getBoundingClientRect();
    var fx = (e.clientX - rect.left) / rect.width;
    var fy = (e.clientY - rect.top) / rect.height;
    var zoomed = dialog.classList.toggle("zoomed");
    if (zoomed) {
      stage.scrollLeft = fx * big.offsetWidth - stage.clientWidth / 2;
      stage.scrollTop = fy * big.offsetHeight - stage.clientHeight / 2;
    }
  });
  dialog.querySelector(".lightbox-close").addEventListener("click", function () { dialog.close(); });
  // Clicking the backdrop (outside the image) closes.
  stage.addEventListener("click", function (e) { if (e.target === stage) dialog.close(); });
  dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
})();
