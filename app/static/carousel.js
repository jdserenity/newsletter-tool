(function() {
  var carousel = document.getElementById('newsletter-carousel');
  if (!carousel) return;

  var down = false, startX = 0, scrollLeft = 0, activeBody = null;
  var CARD_SCROLL_STEP = 80;

  function isNewsletterBody(el) { return el && el.closest && el.closest('.newsletter-body'); }
  function isFormField(el) { return el && el.closest && el.closest('input, textarea, select, [contenteditable]'); }

  function newsletterCards() {
    return Array.prototype.slice.call(carousel.querySelectorAll('.newsletter-card:not(.add-card)'));
  }

  function newsletterBodies() {
    return Array.prototype.slice.call(carousel.querySelectorAll('.newsletter-card:not(.add-card) .newsletter-body'));
  }

  function centeredCardIndex(cards) {
    var rect = carousel.getBoundingClientRect(), mid = rect.left + rect.width / 2;
    var idx = 0, best = Infinity;
    cards.forEach(function(card, i) {
      var r = card.getBoundingClientRect(), d = Math.abs(r.left + r.width / 2 - mid);
      if (d < best) { best = d; idx = i; }
    });
    return idx;
  }

  function activeNewsletterBody() {
    if (activeBody && carousel.contains(activeBody)) return activeBody;
    var cards = newsletterCards();
    if (!cards.length) return null;
    return cards[centeredCardIndex(cards)].querySelector('.newsletter-body');
  }

  function setActiveBody(body) { if (body) activeBody = body; }

  function scrollCarouselBy(deltaY) {
    carousel.scrollLeft += deltaY;
  }

  function scrollToCard(offset) {
    var cards = newsletterCards();
    if (!cards.length) return;
    var idx = centeredCardIndex(cards) + offset;
    if (idx < 0 || idx >= cards.length) return;
    cards[idx].scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    setActiveBody(cards[idx].querySelector('.newsletter-body'));
  }

  function scrollActiveBodyBy(delta) {
    var body = activeNewsletterBody();
    if (!body) return;
    body.scrollTop += delta;
  }

  carousel.addEventListener('mousedown', function(e) {
    if (e.target.closest('a, button, input, label, select, textarea')) return;
    if (isNewsletterBody(e.target)) return;
    down = true; startX = e.clientX; scrollLeft = carousel.scrollLeft;
    carousel.classList.add('dragging');
  });
  document.addEventListener('mouseup', function() {
    if (!down) return;
    down = false; carousel.classList.remove('dragging');
  });
  document.addEventListener('mousemove', function(e) {
    if (!down) return;
    e.preventDefault();
    carousel.scrollLeft = scrollLeft - (e.clientX - startX);
  });

  carousel.addEventListener('wheel', function(e) {
    if (e.deltaX !== 0) return;
    if (e.deltaY === 0) return;
    if (isNewsletterBody(e.target)) return;
    e.preventDefault();
    scrollCarouselBy(e.deltaY);
  }, { passive: false });

  carousel.addEventListener('click', function(e) {
    var body = e.target.closest('.newsletter-body');
    if (body) setActiveBody(body);
  });

  document.addEventListener('keydown', function(e) {
    if (isFormField(e.target)) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); scrollToCard(-1); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); scrollToCard(1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); scrollActiveBodyBy(-CARD_SCROLL_STEP); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); scrollActiveBodyBy(CARD_SCROLL_STEP); }
  });
})();
