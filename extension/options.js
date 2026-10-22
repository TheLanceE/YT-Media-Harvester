const dir = document.getElementById("dir");
const msg = document.getElementById("msg");
const buttons = [...document.querySelectorAll("button")];

function show(text, ok) { msg.textContent = text; msg.className = ok ? "ok" : "err"; }

// Runs a helper command (see helper.js). Returns the reply, or undefined after showing the error.
async function call(cmd, args) {
  buttons.forEach(b => b.disabled = true);
  try {
    const j = await helper(cmd, args);
    if (j.out_dir) dir.value = j.out_dir;
    if (j.default_out_dir) document.getElementById("def").textContent = j.default_out_dir;
    return j;
  } catch (e) {
    show(e.message === OFFLINE ? e.message : "Error: " + e.message);
  } finally {
    buttons.forEach(b => b.disabled = false);
  }
}

call("config");
document.getElementById("save").onclick = async () => {
  const j = await call("config", { out_dir: dir.value });
  if (j) show("Saved. New downloads go to " + j.out_dir, true);
};
document.getElementById("reset").onclick = async () => {
  if (await call("config", { out_dir: "" })) show("Reset to the default folder.", true);
};
// The helper shows the system folder picker (it may open behind this window).
document.getElementById("browse").onclick = async () => {
  show("Pick a folder in the window that opened…", true);
  const j = await call("choose_folder");
  if (j) show(j.cancelled ? "" : "Saved. New downloads go to " + j.out_dir, true);
};
dir.onkeydown = e => { if (e.key === "Enter") document.getElementById("save").click(); };

// yt-dlp: the installed helper can update itself; a source checkout is updated by install.bat.
const parts = v => String(v || "").split(".").map(Number);
const newer = (a, b) => { const [x, y] = [parts(a), parts(b)]; for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false; };
helper("hello").then(j => {
  document.getElementById("ytdlp").textContent = j.ytdlp_version || "unknown";
  if (j.installed) document.getElementById("update-row").hidden = false;
  else document.getElementById("update-hint").textContent = "Run install.bat again to update yt-dlp.";
}).catch(() => {});
document.getElementById("update").onclick = async () => {
  show("Checking for a new yt-dlp…", true);
  const j = await call("update_ytdlp");
  if (!j) return;
  show(newer(j.latest, j.ytdlp_version)
    ? `yt-dlp ${j.latest} is ready. It's used once the helper restarts, about a minute after downloads finish.`
    : `yt-dlp ${j.ytdlp_version} is the newest version.`, true);
};
