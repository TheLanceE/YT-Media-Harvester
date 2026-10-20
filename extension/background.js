// Owns the connection to the native helper. The popup and options page talk to this worker with
// chrome.runtime.sendMessage({cmd, ...}); job progress is mirrored into chrome.storage.session so the
// popup can show it whenever it opens, even after being closed mid-download.
const HOST = "com.yt_tab_downloader.helper";
const IDLE_MS = 60_000; // let the helper exit this long after the last job finishes
const KEEP_MS = 60 * 60_000; // finished jobs stay listed this long

let port = null;
let nextId = 1;
let idleTimer = null;
const pending = new Map();

function connect() {
  if (port) return port;
  port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener(onHostMessage);
  port.onDisconnect.addListener(() => {
    const error = chrome.runtime.lastError?.message || "The helper stopped.";
    port = null;
    for (const p of pending.values()) p.reject(new Error(error));
    pending.clear();
    failRunningJobs(error);
  });
  return port;
}

function call(cmd, args = {}) {
  clearTimeout(idleTimer);
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    try {
      connect().postMessage({ id, cmd, ...args });
    } catch (e) {
      pending.delete(id);
      reject(e);
    }
  });
}

// Storage writes are chained so job events never overwrite each other.
let saving = Promise.resolve();
function updateJobs(change) {
  saving = saving.then(async () => {
    const { jobs = {} } = await chrome.storage.session.get("jobs");
    change(jobs);
    const cutoff = Date.now() - KEEP_MS;
    for (const [id, j] of Object.entries(jobs)) if (j.status !== "running" && (j.started || 0) * 1000 < cutoff) delete jobs[id];
    await chrome.storage.session.set({ jobs });
    const running = Object.values(jobs).filter(j => j.status === "running").length;
    chrome.action.setBadgeText({ text: running ? String(running) : "" });
    chrome.action.setBadgeBackgroundColor({ color: "#e62117" });
    clearTimeout(idleTimer);
    if (!running && port) idleTimer = setTimeout(() => { port?.disconnect(); port = null; }, IDLE_MS);
  });
  return saving;
}

function failRunningJobs(error) {
  return updateJobs(jobs => {
    for (const j of Object.values(jobs)) if (j.status === "running") Object.assign(j, { status: "error", error });
  });
}

function onHostMessage(m) {
  if (m.event === "job") {
    const { event, job, ...fields } = m;
    updateJobs(jobs => { jobs[job] = { ...jobs[job], ...fields }; });
    if (fields.status === "done") notify(fields);
    return;
  }
  const p = pending.get(m.id);
  if (!p) return;
  pending.delete(m.id);
  if (m.ok) p.resolve(m);
  else p.reject(new Error(m.error || "helper error"));
}

function notify(job) {
  chrome.notifications?.create({
    type: "basic", iconUrl: "icons/icon128.png",
    title: `Saved ${String(job.format || "").toUpperCase()}`,
    message: job.title || job.url || "Download finished",
  });
}

// The browser's youtube.com cookies, for the helper's last retry when YouTube asks to sign in. Reading them here
// avoids Chrome's cookie encryption and Edge's locked cookie file; they only go to the local helper.
async function youtubeCookies() {
  const all = await chrome.cookies.getAll({ domain: "youtube.com" }).catch(() => []);
  return all.map(c => ({ domain: c.hostOnly ? c.domain : "." + c.domain.replace(/^\./, ""), path: c.path,
                         secure: c.secure, expires: c.expirationDate || 0, name: c.name, value: c.value }));
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (sender.id !== chrome.runtime.id || typeof msg?.cmd !== "string") return;
  const args = msg.cmd === "download" ? youtubeCookies().then(cookies => ({ ...msg.args, cookies })) : Promise.resolve(msg.args);
  args.then(a => call(msg.cmd, a))
    .then(async r => {
      if (msg.cmd === "download") {
        await updateJobs(jobs => {
          jobs[r.job] = { status: "running", progress: "0%", url: msg.args.url, format: msg.args.format,
                          started: Date.now() / 1000, ...jobs[r.job] };
        });
      }
      reply(r);
    })
    .catch(e => reply({ ok: false, error: e.message }));
  return true; // reply is async
});
