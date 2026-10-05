// Turns <time class="relative-time" datetime="..."> into "3 years ago" etc.
// See _includes/relative-time.html.
(function () {
  if (typeof Intl === "undefined" || !Intl.RelativeTimeFormat) return;
  var rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  var UNITS = [
    ["year", 365 * 24 * 3600],
    ["month", 30 * 24 * 3600],
    ["week", 7 * 24 * 3600],
    ["day", 24 * 3600],
    ["hour", 3600],
    ["minute", 60]
  ];

  function relative(date) {
    var seconds = (date.getTime() - Date.now()) / 1000;
    for (var i = 0; i < UNITS.length; i++) {
      var value = seconds / UNITS[i][1];
      // Truncate so 2 years 11 months reads "2 years ago", not "3 years ago".
      if (Math.abs(value) >= 1) return rtf.format(Math.trunc(value), UNITS[i][0]);
    }
    return "just now";
  }

  document.querySelectorAll("time.relative-time[datetime]").forEach(function (el) {
    var date = new Date(el.getAttribute("datetime"));
    if (isNaN(date)) return;
    el.textContent = relative(date);
  });
})();
