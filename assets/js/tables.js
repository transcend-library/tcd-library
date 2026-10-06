// Keep short table cells ("3–6 months", "Permanent", "Completion") on one line, so
// the browser gives the space to columns with longer text instead of wrapping them.
// Without JS, cells still only wrap between words (see _sass/_notion.scss).
(function () {
  var MAX_CHARS = 22;
  document.querySelectorAll("main table").forEach(function (table) {
    table.querySelectorAll("th, td").forEach(function (cell) {
      var text = cell.textContent.replace(/\s+/g, " ").trim();
      if (text.length && text.length <= MAX_CHARS && !cell.querySelector("br, ul, ol, p + p")) {
        cell.classList.add("cell-nowrap");
      }
    });
  });
})();
