const entriesEl = document.getElementById("entries");
const paginationEl = document.getElementById("pagination");
const categorySelect = document.getElementById("categorySelect");
const showAllToggle = document.getElementById("showAllToggle");
const pageSizeSelect = document.getElementById("pageSizeSelect");

function renderEntries(entries) {
  entriesEl.innerHTML = "";
  if (!entries.length) {
    entriesEl.innerHTML = "<p>暂无数据</p>";
    return;
  }
  entries.forEach((entry) => {
    const div = document.createElement("div");
    div.className = "entry";
    const backfillMark = entry.backfill ? " ← 回溯" : "";
    const absUrl = entry.arxiv_id ? `https://arxiv.org/abs/${entry.arxiv_id}` : "";
    div.innerHTML = `
      <h3>[${entry.arxiv_id}] ${entry.title}</h3>
      <div class="meta">分类：${entry.category || ""}</div>
      <div class="meta">arXiv ID：${entry.arxiv_id || ""} | Primary：${entry.primary_category || ""}</div>
      <div class="meta">Categories：${entry.categories || ""}</div>
      <div class="meta">Published：${entry.published || ""}</div>
      <div class="meta">Date：${entry.source_date || ""}${backfillMark}</div>
      <div class="meta">Authors：${entry.authors || ""}</div>
      <p>${entry.abstract || ""}</p>
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

async function loadEntries(page = 1) {
  const category = categorySelect.value;
  const showAll = showAllToggle.checked;
  const pageSize = Number(pageSizeSelect?.value) || window.UI_CONFIG.defaultPageSize || 20;
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  params.set("show_all", showAll ? "true" : "false");
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  const resp = await fetch(`./api/entries?${params.toString()}`);
  const data = await resp.json();
  renderEntries(data.entries || []);
  renderPagination(data.total || 0, data.page || 1, data.page_size || pageSize);
}

if (pageSizeSelect) {
  pageSizeSelect.value = String(window.UI_CONFIG.defaultPageSize || 20);
}

categorySelect.addEventListener("change", () => loadEntries(1));
showAllToggle.addEventListener("change", () => loadEntries(1));
pageSizeSelect?.addEventListener("change", () => loadEntries(1));

loadEntries(1);
