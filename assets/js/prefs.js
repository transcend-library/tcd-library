// Runs in <head> before first paint: apply saved theme and text size so the
// page doesn't flash. Toggle buttons are wired up in nav.js.
(function () {
  var root = document.documentElement;
  root.classList.add("js");
  try {
    var theme = localStorage.getItem("theme");
    var size = localStorage.getItem("font-size");
    if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
    if (size) root.setAttribute("data-font-size", size);
  } catch (e) { /* storage unavailable: fall back to defaults */ }
})();
