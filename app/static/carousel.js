(function() {
  var carousel = document.getElementById('newsletter-carousel');
  if (!carousel) return;

  var CARD_SCROLL_STEP = 80;
  var DRAG_THRESHOLD = 5;

  // drag state
  var down = false, startX = 0, startY = 0, scrollLeft = 0, startScrollTop = 0;
  var dragMode = null; // 'horizontal' | 'vertical' | null (undecided)
  var dragBody = null; // .newsletter-body el when dragMode may go vertical

  function isFormField(el) { return el && el.closest && el.closest('input, textarea, select, [contenteditable]'); }
  function isNewsletterBody(el) { return el && el.closest ? el.closest('.newsletter-body') : null; }

  function allCards() {
    return Array.prototype.slice.call(carousel.querySelectorAll('.newsletter-card'));
  }
  function contentCards() {
    return Array.prototype.slice.call(carousel.querySelectorAll('.newsletter-card:not(.add-card)'));
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

  var activeBody = null;
  function activeNewsletterBody() {
    if (activeBody && carousel.contains(activeBody)) return activeBody;
    var cards = contentCards();
    if (!cards.length) return null;
    return cards[centeredCardIndex(cards)].querySelector('.newsletter-body');
  }
  function setActiveBody(body) { if (body) activeBody = body; }

  function scrollToCard(offset) {
    var cards = allCards();
    if (!cards.length) return;
    var idx = centeredCardIndex(cards) + offset;
    if (idx < 0 || idx >= cards.length) return;
    cards[idx].scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    var body = cards[idx].querySelector('.newsletter-body');
    if (body) setActiveBody(body);
  }

  function scrollActiveBodyBy(delta) {
    var body = activeNewsletterBody();
    if (!body) return;
    body.scrollTop += delta;
  }

  // Returns true if body can absorb this wheel delta (has more content to scroll toward)
  function bodyCanScroll(body, deltaY) {
    if (!body) return false;
    if (deltaY < 0 && body.scrollTop > 0) return true;
    if (deltaY > 0 && body.scrollTop < body.scrollHeight - body.clientHeight - 1) return true;
    return false;
  }

  carousel.addEventListener('mousedown', function(e) {
    if (e.target.closest('a, button, input, label, select, textarea')) return;
    down = true;
    startX = e.clientX; startY = e.clientY;
    scrollLeft = carousel.scrollLeft;
    dragMode = null;
    dragBody = isNewsletterBody(e.target);
    startScrollTop = dragBody ? dragBody.scrollTop : 0;
    if (activeBody) setActiveBody(dragBody || activeBody);
    carousel.classList.add('dragging');
  });

  document.addEventListener('mouseup', function() {
    if (!down) return;
    down = false; dragMode = null; dragBody = null;
    carousel.classList.remove('dragging');
  });

  document.addEventListener('mousemove', function(e) {
    if (!down) return;
    var dx = e.clientX - startX, dy = e.clientY - startY;

    if (!dragMode) {
      if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
      dragMode = (dragBody && Math.abs(dy) > Math.abs(dx)) ? 'vertical' : 'horizontal';
    }

    e.preventDefault();
    if (dragMode === 'vertical' && dragBody) {
      dragBody.scrollTop = startScrollTop - dy;
    } else {
      carousel.scrollLeft = scrollLeft - dx;
    }
  });

  document.addEventListener('wheel', function(e) {
    if (e.deltaX !== 0) return;
    if (e.deltaY === 0) return;
    var body = e.target.closest ? e.target.closest('.newsletter-body') : null;
    if (bodyCanScroll(body, e.deltaY)) return;
    e.preventDefault();
    carousel.scrollLeft += e.deltaY;
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
