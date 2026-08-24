(function () {
  "use strict";
  var input = document.getElementById("search-input");
  var results = document.getElementById("search-results");
  var status = document.getElementById("search-status");
  if (!input || !results || !status) {
    return;
  }

  var index = [];
  var loaded = false;

  fetch("search-index.json")
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      index = data;
      loaded = true;
      if (input.value.trim()) {
        runSearch(input.value);
      }
    })
    .catch(function () {
      status.textContent = "検索データの読み込みに失敗しました。時間をおいて再度お試しください。";
    });

  function escapeHtml(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : value;
    return div.innerHTML;
  }

  function shortenExcerpt(text) {
    if (text.length > 160) {
      return text.slice(0, 160) + "…";
    }
    return text;
  }

  function renderCard(entry) {
    var card = document.createElement("a");
    card.className = "card";
    card.href = entry.url;
    var thumbClass = entry.image_url ? "thumb" : "thumb no-image";
    var thumbHtml = entry.image_url
      ? '<img src="' + escapeHtml(entry.image_url) + '" alt="">'
      : "";
    card.innerHTML =
      '<div class="' + thumbClass + '">' + thumbHtml + "</div>" +
      '<div class="card-body">' +
      '<div class="card-title">' + escapeHtml(entry.title) + "</div>" +
      '<div class="card-meta"><span class="source-badge">' + escapeHtml(entry.source) + "</span><span>" + escapeHtml(entry.date) + "</span></div>" +
      '<p class="excerpt">' + escapeHtml(shortenExcerpt(entry.excerpt || "")) + "</p>" +
      "</div>";
    return card;
  }

  function runSearch(query) {
    results.innerHTML = "";
    var q = query.trim().toLowerCase();
    if (!q) {
      status.textContent = "";
      return;
    }
    var matched = index.filter(function (entry) {
      var title = (entry.title || "").toLowerCase();
      var body = (entry.excerpt || "").toLowerCase();
      return title.indexOf(q) !== -1 || body.indexOf(q) !== -1;
    });
    status.textContent = matched.length + "件見つかりました";
    matched.forEach(function (entry) {
      results.appendChild(renderCard(entry));
    });
  }

  input.addEventListener("input", function () {
    if (!loaded) {
      return;
    }
    runSearch(input.value);
  });
})();
