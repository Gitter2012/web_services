/**
 * WeChat Subscription Management - Frontend Logic
 * Handles adding, toggling, and deleting RSS subscriptions.
 */
(function () {
  "use strict";

  const API_BASE = "/wechat/ui/api";

  const addAccountName = document.getElementById("addAccountName");
  const addRssUrl = document.getElementById("addRssUrl");
  const addBtn = document.getElementById("addBtn");
  const subTableBody = document.querySelector("#subTable tbody");
  const emptyState = document.getElementById("emptyState");
  const subTable = document.getElementById("subTable");
  const messageEl = document.getElementById("message");

  // --- Init ---
  loadSubscriptions();

  addBtn.addEventListener("click", addSubscription);
  addRssUrl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") addSubscription();
  });

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
    var rssUrl = addRssUrl.value.trim();
    if (!rssUrl) {
      showMessage("Please enter an RSS feed URL.", "error");
      return;
    }

    addBtn.disabled = true;
    addBtn.textContent = "Adding...";

    fetch(API_BASE + "/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account_name: addAccountName.value.trim(),
        rss_url: rssUrl,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) {
          showMessage(data.error, "error");
        } else {
          showMessage("Subscription added successfully.", "success");
          addAccountName.value = "";
          addRssUrl.value = "";
          loadSubscriptions();
        }
      })
      .catch(function (err) {
        showMessage("Failed to add subscription.", "error");
        console.error(err);
      })
      .finally(function () {
        addBtn.disabled = false;
        addBtn.textContent = "Add Subscription";
      });
  }

  // --- Render subscriptions table ---
  function renderSubscriptions(subs) {
    if (subs.length === 0) {
      subTable.style.display = "none";
      emptyState.style.display = "block";
      return;
    }

    subTable.style.display = "";
    emptyState.style.display = "none";
    subTableBody.innerHTML = "";

    subs.forEach(function (s) {
      var tr = document.createElement("tr");
      var activeClass = s.is_active ? "active" : "inactive";
      var activeText = s.is_active ? "Active" : "Paused";
      var createdDate = s.created_at ? formatDate(s.created_at) : "";

      tr.innerHTML =
        "<td>" + escapeHtml(s.account_name || "-") + "</td>" +
        '<td class="url-cell" title="' + escapeHtml(s.rss_url) + '">' + escapeHtml(s.rss_url) + "</td>" +
        "<td>" +
          '<button class="toggle-active ' + activeClass + '" data-id="' + s.id + '">' + activeText + "</button>" +
        "</td>" +
        "<td>" + createdDate + "</td>" +
        '<td class="actions">' +
          '<button class="btn btn-sm btn-danger delete-btn" data-id="' + s.id + '">Delete</button>' +
        "</td>";

      subTableBody.appendChild(tr);
    });

    // Bind toggle buttons
    subTableBody.querySelectorAll(".toggle-active").forEach(function (btn) {
      btn.addEventListener("click", function () {
        toggleSubscription(parseInt(this.dataset.id));
      });
    });

    // Bind delete buttons
    subTableBody.querySelectorAll(".delete-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (confirm("Are you sure you want to delete this subscription?")) {
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
        showMessage("Failed to toggle subscription.", "error");
        console.error(err);
      });
  }

  // --- Delete subscription ---
  function deleteSubscription(id) {
    fetch(API_BASE + "/subscriptions/" + id, { method: "DELETE" })
      .then(function (r) { return r.json(); })
      .then(function () {
        showMessage("Subscription deleted.", "success");
        loadSubscriptions();
      })
      .catch(function (err) {
        showMessage("Failed to delete subscription.", "error");
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
      return y + "-" + m + "-" + day;
    } catch (e) {
      return isoStr;
    }
  }
})();
