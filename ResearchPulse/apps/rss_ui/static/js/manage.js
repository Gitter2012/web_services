/**
 * RSS Subscription Management - Frontend Logic
 * Handles adding, toggling, deleting feeds and triggering crawl.
 */
(function () {
  "use strict";

  var API_BASE = "/rss/ui/api";

  var addTitle = document.getElementById("addTitle");
  var addFeedUrl = document.getElementById("addFeedUrl");
  var addCategory = document.getElementById("addCategory");
  var addBtn = document.getElementById("addBtn");
  var triggerCrawlBtn = document.getElementById("triggerCrawlBtn");
  var feedTableBody = document.querySelector("#feedTable tbody");
  var feedTable = document.getElementById("feedTable");
  var emptyState = document.getElementById("emptyState");
  var messageEl = document.getElementById("message");

  // --- Init ---
  loadSubscriptions();

  addBtn.addEventListener("click", addSubscription);
  addFeedUrl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") addSubscription();
  });

  triggerCrawlBtn.addEventListener("click", triggerCrawl);

  // --- Load subscriptions ---
  function loadSubscriptions() {
    fetch(API_BASE + "/subscriptions")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderSubscriptions(data.subscriptions || []);
      })
      .catch(function (err) {
        console.error("Failed to load subscriptions:", err);
      });
  }

  // --- Add subscription ---
  function addSubscription() {
    var feedUrl = addFeedUrl.value.trim();
    if (!feedUrl) {
      showMessage("Please enter an RSS feed URL.", "error");
      return;
    }

    addBtn.disabled = true;
    addBtn.textContent = "Adding...";

    fetch(API_BASE + "/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: addTitle.value.trim(),
        feed_url: feedUrl,
        category: addCategory.value,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showMessage(data.error, "error");
        } else {
          showMessage("Feed added successfully.", "success");
          addTitle.value = "";
          addFeedUrl.value = "";
          addCategory.value = "";
          loadSubscriptions();
        }
      })
      .catch(function (err) {
        showMessage("Failed to add feed.", "error");
        console.error(err);
      })
      .finally(function () {
        addBtn.disabled = false;
        addBtn.textContent = "Add Feed";
      });
  }

  // --- Trigger crawl ---
  function triggerCrawl() {
    triggerCrawlBtn.disabled = true;
    triggerCrawlBtn.textContent = "Crawling...";

    fetch(API_BASE + "/trigger", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status === "ok") {
          showMessage("Crawl completed successfully.", "success");
          loadSubscriptions();
        } else {
          showMessage("Crawl failed: " + (data.error || "unknown error"), "error");
        }
      })
      .catch(function (err) {
        showMessage("Failed to trigger crawl.", "error");
        console.error(err);
      })
      .finally(function () {
        triggerCrawlBtn.disabled = false;
        triggerCrawlBtn.textContent = "Trigger Crawl";
      });
  }

  // --- Render subscriptions table ---
  function renderSubscriptions(subs) {
    if (subs.length === 0) {
      feedTable.style.display = "none";
      emptyState.style.display = "block";
      return;
    }

    feedTable.style.display = "";
    emptyState.style.display = "none";
    feedTableBody.innerHTML = "";

    subs.forEach(function (s) {
      var tr = document.createElement("tr");
      var activeClass = s.is_active ? "active" : "inactive";
      var activeText = s.is_active ? "Active" : "Paused";
      var lastFetched = s.last_fetched_at ? formatDate(s.last_fetched_at) : "Never";
      var errorClass = s.error_count > 0 ? "has-errors" : "no-errors";

      tr.innerHTML =
        "<td>" + escapeHtml(s.title || "-") + "</td>" +
        '<td class="url-cell" title="' + escapeHtml(s.feed_url) + '">' + escapeHtml(s.feed_url) + "</td>" +
        "<td>" + '<span class="badge">' + escapeHtml(s.category || "-") + "</span></td>" +
        "<td>" + (s.article_count || 0) + "</td>" +
        "<td>" + lastFetched + "</td>" +
        "<td>" + '<span class="error-count ' + errorClass + '">' + s.error_count + "</span></td>" +
        "<td>" +
          '<button class="toggle-active ' + activeClass + '" data-id="' + s.id + '">' + activeText + "</button>" +
        "</td>" +
        '<td class="actions">' +
          '<button class="btn btn-sm btn-danger delete-btn" data-id="' + s.id + '">Delete</button>' +
        "</td>";

      feedTableBody.appendChild(tr);
    });

    // Bind toggle buttons
    feedTableBody.querySelectorAll(".toggle-active").forEach(function (btn) {
      btn.addEventListener("click", function () {
        toggleSubscription(parseInt(this.dataset.id));
      });
    });

    // Bind delete buttons
    feedTableBody.querySelectorAll(".delete-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (confirm("Are you sure you want to delete this feed and all its articles?")) {
          deleteSubscription(parseInt(this.dataset.id));
        }
      });
    });
  }

  // --- Toggle subscription active state ---
  function toggleSubscription(id) {
    fetch(API_BASE + "/subscriptions/" + id + "/toggle", { method: "PUT" })
      .then(function (r) { return r.json(); })
      .then(function () { loadSubscriptions(); })
      .catch(function (err) {
        showMessage("Failed to toggle feed.", "error");
        console.error(err);
      });
  }

  // --- Delete subscription ---
  function deleteSubscription(id) {
    fetch(API_BASE + "/subscriptions/" + id, { method: "DELETE" })
      .then(function (r) { return r.json(); })
      .then(function () {
        showMessage("Feed deleted.", "success");
        loadSubscriptions();
      })
      .catch(function (err) {
        showMessage("Failed to delete feed.", "error");
        console.error(err);
      });
  }

  // --- Helpers ---
  function showMessage(text, type) {
    messageEl.textContent = text;
    messageEl.className = "message message-" + type;
    messageEl.style.display = "block";
    setTimeout(function () {
      messageEl.style.display = "none";
    }, 4000);
  }

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
