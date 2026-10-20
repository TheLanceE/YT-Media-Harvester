const API = "http://127.0.0.1:8765";
const list = document.getElementById("list");
const msg = document.getElementById("msg");
const NATIVE_HOST = "com.yt_tab_downloader.helper";
const OFFLINE = "Helper couldn't start. Run install.bat once (or start start.bat).";

function cleanTitle(t) { return t.replace(/^\(\d+\)\s*/, "").replace(/\s*-\s*YouTube$/, ""); }

function videoId(url) {
  const u = new URL(url);
  return u.hostname === "youtu.be" ? u.pathname.slice(1) : u.searchParams.get("v");
}

async function ping() {
  try { return await (await fetch(`${API}/`)).json(); } catch { return null; }
}

// Returns the helper's info, starting it through the native host (install.bat) if it isn't running.
let launching = null;
function ensureHelper() {
  return launching ??= (async () => {
    let j = await ping();
    if (!j) {
      document.getElementById("dot").className = "dot";
      document.getElementById("helper").textContent = "Starting helper…";
      try {
        const r = await chrome.runtime.sendNativeMessage(NATIVE_HOST, { cmd: "start" });
        if (r?.ok) j = await ping();
      } catch { /* native host not installed */ }
    }
    launching = null;
    return j;
  })();
}

// Helper status dot in the header, plus the save folder in the footer.
async function checkHelper() {
  const dot = document.getElementById("dot"), label = document.getElementById("helper");
  const j = await ensureHelper();
  if (!j) {
    dot.className = "dot off"; label.textContent = "Helper offline";
    return false;
  }
  dot.className = "dot on"; label.textContent = "Helper online";
  if (j.out_dir) { const o = document.getElementById("outdir"); o.textContent = `Saving to ${j.out_dir}`; o.title = j.out_dir; }
  return true;
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

async function start(url, format, card) {
  setState(card, "running", `Starting ${format.toUpperCase()}…`, null);
  if (!(await checkHelper())) return setState(card, "error", OFFLINE);
  try {
    const r = await fetch(`${API}/download`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format }),
    });
    const j = await r.json();
    if (!r.ok) return setState(card, "error", j.error);
    const timer = setInterval(async () => {
      let s;
      try { s = await (await fetch(`${API}/status/${j.job}`)).json(); }
      catch { clearInterval(timer); return setState(card, "error", OFFLINE); }
      if (s.status === "done") { clearInterval(timer); return setState(card, "done", `✔ Saved ${format.toUpperCase()} to ${s.out_dir}`); }
      if (s.status === "error") { clearInterval(timer); return setState(card, "error", "Error: " + s.error); }
      const pct = parseFloat(s.progress);
      if (s.progress === "converting") setState(card, "running", "Converting and tagging…", null);
      else setState(card, "running", `Downloading ${s.progress || ""}`, isNaN(pct) ? null : pct);
    }, 700);
  } catch {
    setState(card, "error", OFFLINE);
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
    list.appendChild(card);
  }
})();

document.getElementById("open").onclick = async () => {
  if (await checkHelper()) fetch(`${API}/open`).catch(() => { msg.textContent = OFFLINE; });
  else msg.textContent = OFFLINE;
};

document.getElementById("settings").onclick = () => chrome.runtime.openOptionsPage();
