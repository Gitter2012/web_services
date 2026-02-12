/**
 * RSS Article List - Frontend Logic
 * Handles article loading, filtering, search, star, read, and pagination via AJAX.
 */
(function () {
  "use strict";

  var API_BASE = "/rss/ui/api";
  var PAGE_SIZE = (window.UI_CONFIG && window.UI_CONFIG.defaultPageSize) || 20;

  // State
  var currentPage = 1;
  var currentCategory = "";
  var currentFeed = "";
  var currentKeyword = "";
  var currentSort = "publish_time";
  var currentFilter = "all"; // all | unread | starred
  var searchTimer = null;

  // DOM refs
  var categorySelect = document.getElementById("categorySelect");
  var feedSelect = document.getElementById("feedSelect");
  var searchInput = document.getElementById("searchInput");
  var sortSelect = document.getElementById("sortSelect");
  var articleList = document.getElementById("articleList");
  var pagination = document.getElementById("pagination");
  var filterBtns = document.querySelectorAll(".filter-btn");

  // --- Init ---
  loadCategories();
  loadFeeds();
  loadArticles();

  // --- Event listeners ---
  categorySelect.addEventListener("change", function () {
    currentCategory = this.value;
    currentPage = 1;
    loadArticles();
  });

  feedSelect.addEventListener("change", function () {
    currentFeed = this.value;
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

  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      filterBtns.forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      currentFilter = btn.dataset.filter;
      currentPage = 1;
      loadArticles();
    });
  });

  // --- Load categories for filter dropdown ---
  function loadCategories() {
    fetch(API_BASE + "/categories")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var categories = data.categories || [];
        categories.forEach(function (name) {
          var opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          categorySelect.appendChild(opt);
        });
      })
      .catch(function (err) {
        console.error("Failed to load categories:", err);
      });
  }

  // --- Load feeds for filter dropdown ---
  function loadFeeds() {
    fetch(API_BASE + "/feeds")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var feeds = data.feeds || [];
        feeds.forEach(function (f) {
          var opt = document.createElement("option");
          opt.value = f.id;
          opt.textContent = f.title + (f.category ? " [" + f.category + "]" : "");
          feedSelect.appendChild(opt);
        });
      })
      .catch(function (err) {
        console.error("Failed to load feeds:", err);
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
    if (currentCategory) params.set("category", currentCategory);
    if (currentFeed) params.set("feed_id", currentFeed);
    if (currentKeyword) params.set("keyword", currentKeyword);
    if (currentFilter === "starred") params.set("starred", "true");
    if (currentFilter === "unread") params.set("unread", "true");

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
      var starredClass = a.is_starred ? " starred" : "";
      var coverHtml = a.cover_image_url
        ? '<img class="card-cover" src="' + escapeHtml(a.cover_image_url) + '" alt="" loading="lazy" />'
        : "";
      var pubTime = a.publish_time ? formatDate(a.publish_time) : "";
      var starIcon = a.is_starred ? "\u2605" : "\u2606";

      html +=
        '<div class="article-card' + readClass + '" data-id="' + a.id + '" data-url="' + escapeHtml(a.url) + '">' +
          '<button class="star-btn' + starredClass + '" data-id="' + a.id + '" title="Toggle star">' + starIcon + '</button>' +
          coverHtml +
          '<div class="card-body">' +
            '<div class="card-title">' + escapeHtml(a.title) + "</div>" +
            '<div class="card-digest">' + escapeHtml(a.summary) + "</div>" +
            '<div class="card-meta">' +
              '<span class="feed-name">' + escapeHtml(a.feed_title) + "</span>" +
              (a.author ? '<span>' + escapeHtml(a.author) + "</span>" : "") +
              (pubTime ? '<span>' + pubTime + "</span>" : "") +
              '<span class="badge">' + escapeHtml(a.feed_title ? (a.feed_title.substring(0, 8)) : "") + "</span>" +
            "</div>" +
          "</div>" +
        "</div>";
    });

    articleList.innerHTML = html;

    // Bind card click: mark as read and open in new tab
    articleList.querySelectorAll(".article-card").forEach(function (card) {
      card.addEventListener("click", function (e) {
        // Ignore clicks on star button
        if (e.target.classList.contains("star-btn")) return;

        var id = card.dataset.id;
        var url = card.dataset.url;

        // Mark as read
        fetch(API_BASE + "/articles/" + id + "/read", { method: "POST" })
          .then(function () {
            card.classList.add("is-read");
          })
          .catch(function (err) {
            console.error("Failed to mark as read:", err);
          });

        // Open in new tab
        if (url) {
          window.open(url, "_blank");
        }
      });
    });

    // Bind star button click
    articleList.querySelectorAll(".star-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var id = btn.dataset.id;

        fetch(API_BASE + "/articles/" + id + "/star", { method: "POST" })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.is_starred) {
              btn.classList.add("starred");
              btn.textContent = "\u2605";
            } else {
              btn.classList.remove("starred");
              btn.textContent = "\u2606";
            }
          })
          .catch(function (err) {
            console.error("Failed to toggle star:", err);
          });
      });
    });
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
