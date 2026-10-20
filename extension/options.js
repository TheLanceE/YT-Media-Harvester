const API = "http://127.0.0.1:8765";
const NATIVE_HOST = "com.yt_tab_downloader.helper";
const dir = document.getElementById("dir");
const msg = document.getElementById("msg");
const buttons = [...document.querySelectorAll("button")];

function show(text, ok) { msg.textContent = text; msg.className = ok ? "ok" : "err"; }

// GET when body is undefined, otherwise POST it as JSON. Returns the reply, or undefined after showing the error.
async function call(path, body, retried) {
  buttons.forEach(b => b.disabled = true);
  try {
    const r = await fetch(API + path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    if (j.out_dir) dir.value = j.out_dir;
    if (j.default_out_dir) document.getElementById("def").textContent = j.default_out_dir;
    return j;
  } catch (e) {
    if (e instanceof TypeError && !retried) {
      // Helper not running: start it through the native host (install.bat), then try once more.
      show("Starting helper…", true);
      const r = await chrome.runtime.sendNativeMessage(NATIVE_HOST, { cmd: "start" }).catch(() => null);
      if (r?.ok) { show("", true); return call(path, body, true); }
    }
    show(e instanceof TypeError ? "Helper couldn't start. Run install.bat once (or start start.bat)." : "Error: " + e.message);
  } finally {
    buttons.forEach(b => b.disabled = false);
  }
}

call("/config");
document.getElementById("save").onclick = async () => {
  const j = await call("/config", { out_dir: dir.value });
  if (j) show("Saved. New downloads go to " + j.out_dir, true);
};
document.getElementById("reset").onclick = async () => {
  if (await call("/config", { out_dir: "" })) show("Reset to the default folder.", true);
};
// The helper shows the system folder picker (it may open behind this window).
document.getElementById("browse").onclick = async () => {
  show("Pick a folder in the window that opened…", true);
  const j = await call("/choose-folder", {});
  if (j) show(j.cancelled ? "" : "Saved. New downloads go to " + j.out_dir, true);
};
dir.onkeydown = e => { if (e.key === "Enter") document.getElementById("save").click(); };
