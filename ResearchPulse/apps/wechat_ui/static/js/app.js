/**
 * WeChat Article List - Frontend Logic
 * Handles article loading, filtering, search, and pagination via AJAX.
 */
(function () {
  "use strict";

  const API_BASE = "/wechat/ui/api";
  const PAGE_SIZE = (window.UI_CONFIG && window.UI_CONFIG.defaultPageSize) || 20;

  // State
  let currentPage = 1;
  let currentAccount = "";
  let currentKeyword = "";
  let currentSort = "publish_time";
  let searchTimer = null;

  // DOM refs
  const accountSelect = document.getElementById("accountSelect");
  const searchInput = document.getElementById("searchInput");
  const sortSelect = document.getElementById("sortSelect");
  const articleList = document.getElementById("articleList");
  const pagination = document.getElementById("pagination");

  // --- Init ---
  loadAccounts();
  loadArticles();

  accountSelect.addEventListener("change", function () {
    currentAccount = this.value;
    currentPage = 1;
    loadArticles();
  });

  sortSelect.addEventListener("change", function () {
    currentSort = this.value;
    currentPage = 1;
    loadArticles();
  });

  searchInput.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      currentKeyword = searchInput.value.trim();
      currentPage = 1;
      loadArticles();
    }, 400);
  });

  // --- Load accounts for filter dropdown ---
  function loadAccounts() {
    fetch(API_BASE + "/accounts")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var accounts = data.accounts || [];
        accounts.forEach(function (name) {
          var opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          accountSelect.appendChild(opt);
        });
      })
      .catch(function (err) {
        console.error("Failed to load accounts:", err);
      });
  }

  // --- Load articles ---
  function loadArticles() {
    articleList.innerHTML = '<div class="loading">Loading articles...</div>';

    var params = new URLSearchParams({
      page: currentPage,
      page_size: PAGE_SIZE,
      sort: currentSort,
    });
    if (currentAccount) params.set("account", currentAccount);
    if (currentKeyword) params.set("keyword", currentKeyword);

    fetch(API_BASE + "/articles?" + params.toString())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderArticles(data.articles || []);
        renderPagination(data.total || 0, data.page || 1, data.page_size || PAGE_SIZE);
      })
      .catch(function (err) {
        articleList.innerHTML = '<div class="loading">Failed to load articles.</div>';
        console.error("Failed to load articles:", err);
      });
  }

  // --- Render article cards ---
  function renderArticles(articles) {
    if (articles.length === 0) {
      articleList.innerHTML = '<div class="empty-state"><p>No articles found.</p></div>';
      return;
    }

    var html = "";
    articles.forEach(function (a) {
      var readClass = a.is_read ? " is-read" : "";
      var coverHtml = a.cover_image_url
        ? '<img class="card-cover" src="' + escapeHtml(a.cover_image_url) + '" alt="" loading="lazy" />'
        : "";
      var pubTime = a.publish_time ? formatDate(a.publish_time) : "";

      html +=
        '<div class="article-card' + readClass + '" onclick="window.location.href=\'/wechat/ui/article/' + a.id + '\'">' +
          coverHtml +
          '<div class="card-body">' +
            '<div class="card-title">' + escapeHtml(a.title) + "</div>" +
            '<div class="card-digest">' + escapeHtml(a.digest) + "</div>" +
            '<div class="card-meta">' +
              '<span>' + escapeHtml(a.account_name) + "</span>" +
              '<span>' + pubTime + "</span>" +
              '<span class="badge badge-' + a.source_type + '">' + a.source_type + "</span>" +
            "</div>" +
          "</div>" +
        "</div>";
    });

    articleList.innerHTML = html;
  }

  // --- Render pagination ---
  function renderPagination(total, page, pageSize) {
    var totalPages = Math.max(1, Math.ceil(total / pageSize));

    if (totalPages <= 1) {
      pagination.innerHTML = "";
      return;
    }

    var prevDisabled = page <= 1 ? " disabled" : "";
    var nextDisabled = page >= totalPages ? " disabled" : "";

    pagination.innerHTML =
      '<button id="prevBtn"' + prevDisabled + '>&laquo; Prev</button>' +
      '<span class="page-info">Page ' + page + " / " + totalPages + " (" + total + " articles)</span>" +
      '<button id="nextBtn"' + nextDisabled + '>Next &raquo;</button>';

    document.getElementById("prevBtn").addEventListener("click", function () {
      if (currentPage > 1) {
        currentPage--;
        loadArticles();
      }
    });
    document.getElementById("nextBtn").addEventListener("click", function () {
      if (currentPage < totalPages) {
        currentPage++;
        loadArticles();
      }
    });
  }

  // --- Helpers ---
  function escapeHtml(str) {
    if (!str) return "";
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function formatDate(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      var y = d.getFullYear();
      var m = String(d.getMonth() + 1).padStart(2, "0");
      var day = String(d.getDate()).padStart(2, "0");
      var h = String(d.getHours()).padStart(2, "0");
      var min = String(d.getMinutes()).padStart(2, "0");
      return y + "-" + m + "-" + day + " " + h + ":" + min;
    } catch (e) {
      return isoStr;
    }
  }
})();
