/* Soft murmur of feed-noise behind the landing hero. Respects reduced motion. */
(function () {
  var root = document.getElementById("murmur");
  if (!root) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var scraps = [
    "breaking: everyone has an opinion",
    "you will not believe",
    "ratio'd into oblivion",
    "hot take incoming",
    "thread (1/47)",
    "this changes everything",
    "unpopular opinion but",
    "the discourse is exhausted",
    "quote-tweet pile-on",
    "algorithmic weather",
    "doomscroll weather report",
    "notification hunger",
    "timeline wants blood",
    "another dunk, another day",
    "signal lost in the noise",
  ];

  var max = 7;
  var active = 0;

  function spawn() {
    if (active >= max) return;
    var el = document.createElement("span");
    el.className = "landing-murmur-line";
    el.textContent = scraps[Math.floor(Math.random() * scraps.length)];
    el.style.top = (8 + Math.random() * 72) + "%";
    el.style.left = (4 + Math.random() * 55) + "%";
    var dur = 9 + Math.random() * 10;
    el.style.animationDuration = dur + "s";
    root.appendChild(el);
    active += 1;
    el.addEventListener("animationend", function () {
      el.remove();
      active -= 1;
    });
  }

  spawn();
  setInterval(spawn, 1600);
})();
