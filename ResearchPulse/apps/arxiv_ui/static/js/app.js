const entriesEl = document.getElementById("entries");
const paginationEl = document.getElementById("pagination");
const categorySelect = document.getElementById("categorySelect");
const showAllToggle = document.getElementById("showAllToggle");
const backfillOnlyToggle = document.getElementById("backfillOnlyToggle");
const pageSizeSelect = document.getElementById("pageSizeSelect");
const styleSelect = document.getElementById("styleSelect");
const searchInput = document.getElementById("searchInput");
const sortSelect = document.getElementById("sortSelect");
const appRoot = document.getElementById("appRoot");

const STORAGE_KEY = "arxiv_ui_prefs";
const DEFAULTS = {
  style: window.UI_CONFIG?.defaultStyle || "high",
  sort: window.UI_CONFIG?.defaultSort || "date",
  search: "",
  backfillOnly: false,
};

function escapeHtml(value) {
  if (!value) return "";
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function highlightText(value, query) {
  const text = escapeHtml(value || "");
  if (!query) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regex = new RegExp(escaped, "ig");
  return text.replace(regex, (match) => `<span class="highlight">${match}</span>`);
}

function renderEntries(entries) {
  entriesEl.innerHTML = "";
  if (!entries.length) {
    entriesEl.innerHTML = "<p>暂无数据</p>";
    return;
  }
  const query = searchInput?.value?.trim() || "";
  entries.forEach((entry) => {
    const div = document.createElement("div");
    div.className = "entry";
    const backfillMark = entry.backfill ? " ← 回溯" : "";
    const absUrl = entry.arxiv_id ? `https://arxiv.org/abs/${entry.arxiv_id}` : "";
    const safeTitle = highlightText(entry.title || "", query);
    const safeAbstract = highlightText(entry.abstract || "", query);
    div.innerHTML = `
      <h3>[${escapeHtml(entry.arxiv_id || "")}] ${safeTitle}</h3>
      <div class="meta">分类：${escapeHtml(entry.category || "")}</div>
      <div class="meta">arXiv ID：${escapeHtml(entry.arxiv_id || "")} | Primary：${escapeHtml(entry.primary_category || "")}</div>
      <div class="meta">Categories：${escapeHtml(entry.categories || "")}</div>
      <div class="meta">Published：${escapeHtml(entry.published || "")}</div>
      <div class="meta">Date：${escapeHtml(entry.source_date || "")}${backfillMark}</div>
      <div class="meta">Authors：${escapeHtml(entry.authors || "")}</div>
      <p>${safeAbstract}</p>
      <div class="links">
        ${entry.pdf_url ? `<a href="${entry.pdf_url}" target="_blank">PDF</a>` : ""}
        ${absUrl ? `<a href="${absUrl}" target="_blank">abs</a>` : ""}
        ${entry.translate_url ? `<a href="${entry.translate_url}" target="_blank">翻译</a>` : ""}
      </div>
    `;
    entriesEl.appendChild(div);
  });
}

function renderPagination(total, page, pageSize) {
  paginationEl.innerHTML = "";
  if (!pageSize || total <= pageSize) {
    return;
  }
  const totalPages = Math.ceil(total / pageSize);
  const prevBtn = document.createElement("button");
  prevBtn.textContent = "上一页";
  prevBtn.disabled = page <= 1;
  prevBtn.onclick = () => loadEntries(page - 1);
  paginationEl.appendChild(prevBtn);

  const info = document.createElement("span");
  info.textContent = `${page} / ${totalPages}`;
  paginationEl.appendChild(info);

  const nextBtn = document.createElement("button");
  nextBtn.textContent = "下一页";
  nextBtn.disabled = page >= totalPages;
  nextBtn.onclick = () => loadEntries(page + 1);
  paginationEl.appendChild(nextBtn);
}

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch (err) {
    return { ...DEFAULTS };
  }
}

function savePrefs(next) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function applyDensity(style) {
  if (!appRoot) return;
  appRoot.classList.remove("density--high", "density--comfortable");
  appRoot.classList.add(style === "comfortable" ? "density--comfortable" : "density--high");
}

async function loadEntries(page = 1) {
  const category = categorySelect.value;
  const showAll = showAllToggle.checked;
  const backfillOnly = backfillOnlyToggle?.checked;
  const pageSize = Number(pageSizeSelect?.value) || window.UI_CONFIG.defaultPageSize || 20;
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  params.set("show_all", showAll ? "true" : "false");
  if (backfillOnly) params.set("backfill_only", "true");
  const search = searchInput?.value?.trim();
  if (search) params.set("search", search);
  const sort = sortSelect?.value;
  if (sort) params.set("sort", sort);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  const resp = await fetch(`./api/entries?${params.toString()}`);
  const data = await resp.json();
  renderEntries(data.entries || []);
  renderPagination(data.total || 0, data.page || 1, data.page_size || pageSize);
}

const prefs = loadPrefs();

if (pageSizeSelect) {
  pageSizeSelect.value = String(window.UI_CONFIG.defaultPageSize || 20);
}

if (styleSelect) {
  styleSelect.value = prefs.style;
  applyDensity(prefs.style);
}

if (sortSelect) {
  sortSelect.value = prefs.sort;
}

if (searchInput) {
  searchInput.value = prefs.search || "";
}

if (backfillOnlyToggle) {
  backfillOnlyToggle.checked = !!prefs.backfillOnly;
}

let searchTimer = null;

function handlePrefsUpdate() {
  const next = {
    style: styleSelect?.value || DEFAULTS.style,
    sort: sortSelect?.value || DEFAULTS.sort,
    search: searchInput?.value?.trim() || "",
    backfillOnly: !!backfillOnlyToggle?.checked,
  };
  savePrefs(next);
}

categorySelect.addEventListener("change", () => loadEntries(1));
showAllToggle.addEventListener("change", () => loadEntries(1));
pageSizeSelect?.addEventListener("change", () => loadEntries(1));
backfillOnlyToggle?.addEventListener("change", () => {
  handlePrefsUpdate();
  loadEntries(1);
});
styleSelect?.addEventListener("change", () => {
  applyDensity(styleSelect.value);
  handlePrefsUpdate();
});
sortSelect?.addEventListener("change", () => {
  handlePrefsUpdate();
  loadEntries(1);
});
searchInput?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    handlePrefsUpdate();
    loadEntries(1);
  }, 300);
});

loadEntries(1);
