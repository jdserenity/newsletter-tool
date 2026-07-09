(function() {
  // In-place actions (settings, mark read). Full form POSTs used to redirect to /
  // and reload the page, which always reset the carousel to scrollLeft = 0.

  function postForm(url, fields) {
    var body = new URLSearchParams();
    Object.keys(fields).forEach(function(k) { body.set(k, fields[k]); });
    return fetch(url, {
      method: 'POST', body: body,
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    }).then(function(r) {
      if (!r.ok) throw new Error('request failed');
      return r.json();
    });
  }

  function sortTweetList(list) {
    if (!list) return;
    var tweets = Array.prototype.slice.call(list.querySelectorAll('.tweet'));
    tweets.sort(function(a, b) {
      var ar = a.classList.contains('tweet-read') ? 1 : 0;
      var br = b.classList.contains('tweet-read') ? 1 : 0;
      if (ar !== br) return ar - br;
      return (a.getAttribute('data-created-at') || '').localeCompare(b.getAttribute('data-created-at') || '');
    });
    tweets.forEach(function(t) { list.appendChild(t); });
  }

  // Newsletter checkmark lives at the bottom until every tweet is checked off,
  // then moves to the top so you can dismiss the card without scrolling.
  function updateNewsletterCheckPosition(body) {
    if (!body) return;
    var footer = body.querySelector('.newsletter-footer');
    var list = body.querySelector('.tweet-list');
    if (!footer || !list) return;
    var tweets = list.querySelectorAll('.tweet');
    if (!tweets.length) {
      footer.classList.remove('is-top');
      body.appendChild(footer);
      return;
    }
    var allRead = true;
    for (var i = 0; i < tweets.length; i++) {
      if (!tweets[i].classList.contains('tweet-read')) { allRead = false; break; }
    }
    footer.classList.toggle('is-top', allRead);
    if (allRead) body.insertBefore(footer, body.firstChild);
    else body.appendChild(footer);
  }

  function setupTextClamp(root) {
    (root || document).querySelectorAll('.tweet-text').forEach(function(wrap) {
      var text = wrap.querySelector('.text-content');
      var btn = wrap.querySelector('.tweet-more');
      if (!text || !btn || wrap.dataset.clampReady) return;
      wrap.dataset.clampReady = '1';
      wrap.classList.add('is-clamped');
      // If clamped height still fits full content, no expand control needed.
      requestAnimationFrame(function() {
        if (text.scrollHeight <= text.clientHeight + 1) {
          wrap.classList.remove('is-clamped');
          btn.hidden = true;
          return;
        }
        btn.hidden = false;
        btn.addEventListener('click', function() {
          var open = wrap.classList.toggle('is-expanded');
          wrap.classList.toggle('is-clamped', !open);
          btn.textContent = open ? 'Less' : 'More';
        });
      });
    });
  }

  document.addEventListener('change', function(e) {
    var input = e.target;
    if (!input.matches || !input.matches('.settings-row input[type="checkbox"]')) return;
    var form = input.closest('form.settings-row');
    if (!form) return;
    // Omit unchecked boxes (same as a normal HTML form). Server Form(False) defaults.
    var body = new URLSearchParams();
    if (form.querySelector('[name="include_quotes"]').checked) body.set('include_quotes', 'true');
    if (form.querySelector('[name="include_replies"]').checked) body.set('include_replies', 'true');
    if (form.querySelector('[name="include_retweets"]').checked) body.set('include_retweets', 'true');
    fetch(form.action, {
      method: 'POST', body: body,
      headers: { 'Accept': 'application/json' },
      credentials: 'same-origin'
    }).catch(function() { /* keep toggled state; next reload will reconcile */ });
  });

  // Stop native form submit on settings (no full page navigation).
  document.addEventListener('submit', function(e) {
    if (e.target && e.target.matches && e.target.matches('form.settings-row')) e.preventDefault();
  });

  document.addEventListener('click', function(e) {
    var btn = e.target.closest && e.target.closest('button.mark-check');
    if (!btn) return;
    e.preventDefault();

    if (btn.classList.contains('mark-check-newsletter')) {
      var accountId = btn.getAttribute('data-account-id');
      var weekStart = btn.getAttribute('data-week-start');
      if (!accountId || !weekStart) return;
      btn.disabled = true;
      postForm('/accounts/' + accountId + '/read-newsletter', { week_start: weekStart })
        .then(function() {
          var card = btn.closest('.newsletter-card');
          if (card) card.remove();
        })
        .catch(function() { btn.disabled = false; });
      return;
    }

    var tweetId = btn.getAttribute('data-tweet-id');
    if (!tweetId) return;
    var tweet = btn.closest('.tweet');
    var nextRead = !btn.classList.contains('is-read');
    btn.disabled = true;
    postForm('/tweets/' + encodeURIComponent(tweetId) + '/read', { read: nextRead ? 'true' : 'false' })
      .then(function() {
        btn.classList.toggle('is-read', nextRead);
        btn.setAttribute('aria-pressed', nextRead ? 'true' : 'false');
        btn.setAttribute('aria-label', nextRead ? 'Mark as unread' : 'Mark as read');
        btn.title = nextRead ? 'Mark as unread' : 'Mark as read';
        if (tweet) {
          tweet.classList.toggle('tweet-read', nextRead);
          sortTweetList(tweet.parentElement);
          updateNewsletterCheckPosition(tweet.closest('.newsletter-body'));
        }
      })
      .finally(function() { btn.disabled = false; });
  });

  setupTextClamp(document);
})();
