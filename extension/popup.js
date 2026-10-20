const list = document.getElementById("list");
const msg = document.getElementById("msg");

function cleanTitle(t) { return t.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube$/, ""); }

function videoId(url) {
  const u = new URL(url);
  return u.hostname === "youtu.be" ? u.pathname.slice(1) : u.searchParams.get("v");
}

// Helper status dot in the header, plus the save folder in the footer.
async function checkHelper() {
  const dot = document.getElementById("dot"), label = document.getElementById("helper");
  try {
    const j = await helper("hello");
    dot.className = "dot on"; label.textContent = "Helper online";
    const o = document.getElementById("outdir"); o.textContent = `Saving to ${j.out_dir}`; o.title = j.out_dir;
    return true;
  } catch (e) {
    dot.className = "dot off"; label.textContent = "Helper offline";
    msg.textContent = e.message;
    return false;
  }
}

function setState(card, state, text, pct) {
  const st = card.querySelector(".st"), bar = card.querySelector(".bar");
  st.className = "st " + state;
  st.textContent = text;
  card.classList.toggle("busy", state === "running");
  card.querySelectorAll("button").forEach(b => b.disabled = state === "running");
  bar.classList.toggle("indeterminate", pct == null);
  bar.firstElementChild.style.width = pct == null ? "" : pct + "%";
}

// Shows a job's state on its card. Jobs live in chrome.storage.session, kept up to date by background.js,
// so a download started earlier still shows its progress when the popup is opened again.
function showJob(card, job) {
  const fmt = String(job.format || "").toUpperCase();
  if (job.status === "done") return setState(card, "done", `✔ Saved ${fmt} to ${job.out_dir}`);
  if (job.status === "error") return setState(card, "error", "Error: " + job.error);
  if (job.progress === "converting") return setState(card, "running", "Converting and tagging…", null);
  const pct = parseFloat(job.progress);
  const what = job.format === "mp4" ? (job.part > 1 ? " audio" : " video") : "";
  setState(card, "running", `Downloading${what} ${job.progress || ""}`, isNaN(pct) ? null : pct);
}

const cards = new Map(); // video id -> card
function render(jobs = {}) {
  const latest = new Map();
  for (const j of Object.values(jobs)) {
    const id = j.url && videoId(j.url);
    if (id && cards.has(id) && (latest.get(id)?.started || 0) <= (j.started || 0)) latest.set(id, j);
  }
  for (const [id, j] of latest) showJob(cards.get(id), j);
}
chrome.storage.session.onChanged.addListener(c => { if (c.jobs) render(c.jobs.newValue); });

async function start(url, format, card) {
  setState(card, "running", `Starting ${format.toUpperCase()}…`, null);
  try {
    await helper("download", { url, format });
    msg.textContent = "";
  } catch (e) {
    setState(card, "error", e.message);
    checkHelper();
  }
}

(async () => {
  checkHelper();
  const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
  const tabs = await chrome.tabs.query({ url: ["*://www.youtube.com/watch*", "*://youtu.be/*"] });
  tabs.sort((a, b) => (b.id === active?.id) - (a.id === active?.id));
  if (!tabs.length) msg.textContent = "No open YouTube video tabs.";
  for (const t of tabs) {
    const card = document.createElement("div");
    card.className = "tab" + (t.id === active?.id ? " active" : "");
    card.innerHTML = `<img class="thumb" alt="">
      <div class="info">
        <div class="title"></div>
        <div class="btns"><button data-f="mp3">MP3</button><button data-f="mp4">MP4</button></div>
        <div class="bar"><div></div></div>
        <div class="st"></div>
      </div>`;
    const id = videoId(t.url);
    const thumb = card.querySelector(".thumb");
    thumb.onerror = () => thumb.removeAttribute("src");
    if (id) thumb.src = `https://i.ytimg.com/vi/${id}/mqdefault.jpg`;
    const title = card.querySelector(".title");
    title.textContent = cleanTitle(t.title);
    title.title = cleanTitle(t.title);
    if (t.id === active?.id) title.insertAdjacentHTML("beforebegin", `<span class="badge">Current tab</span>`);
    // Clicking the thumbnail or title switches to that tab.
    const focus = () => { chrome.tabs.update(t.id, { active: true }); chrome.windows.update(t.windowId, { focused: true }); };
    thumb.onclick = title.onclick = focus;
    card.querySelectorAll("button").forEach(b => b.onclick = () => start(t.url, b.dataset.f, card));
    if (id) cards.set(id, card);
    list.appendChild(card);
  }
  render((await chrome.storage.session.get("jobs")).jobs);
})();

document.getElementById("open").onclick = () => helper("open").catch(e => { msg.textContent = e.message; });

document.getElementById("settings").onclick = () => chrome.runtime.openOptionsPage();
