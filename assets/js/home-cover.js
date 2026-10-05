// Scatters twinkling stars over the home page cover (see _sass/_home-cover.scss).
// Ported from "Night Sky with twinkling stars" by getdesigning (CodePen, MIT),
// without jQuery and with fewer stars for a banner-sized sky.
(function () {
  var cover = document.querySelector(".home-cover");
  if (!cover) return;
  var sky = cover.querySelector(".home-cover-stars");
  var AMOUNT = 160;
  var frag = document.createDocumentFragment();

  for (var i = 0; i < AMOUNT; i++) {
    var star = document.createElement("div");
    star.className = "star";
    star.appendChild(document.createElement("div"));
    var size = Math.random() * 2 + 7 + "px";
    star.style.top = Math.random() * 100 + "%";
    star.style.left = Math.random() * 100 + "%";
    star.style.width = size;
    star.style.height = size;
    star.style.opacity = Math.random() * 0.5 + 0.5;
    star.style.animationDelay = -Math.random() * 100 + "s";
    if (i % 8 === 0) star.classList.add("pink");
    else if (i % 10 === 6) star.classList.add("blue");
    frag.appendChild(star);
  }
  sky.appendChild(frag);

  // Don't animate while the cover is off-screen.
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      cover.classList.toggle("is-paused", !entries[0].isIntersecting);
    }).observe(cover);
  }
})();
