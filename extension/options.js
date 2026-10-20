const dir = document.getElementById("dir");
const msg = document.getElementById("msg");
const buttons = [...document.querySelectorAll("button")];

function show(text, ok) { msg.textContent = text; msg.className = ok ? "ok" : "err"; }

// GET when body is undefined, otherwise POST it as JSON. Starts the helper if needed (see helper.js).
// Returns the reply, or undefined after showing the error.
async function call(path, body) {
  buttons.forEach(b => b.disabled = true);
  try {
    const r = await helperFetch(path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    if (j.out_dir) dir.value = j.out_dir;
    if (j.default_out_dir) document.getElementById("def").textContent = j.default_out_dir;
    return j;
  } catch (e) {
    show(e instanceof TypeError ? "Helper couldn't start. Run install.bat once, then reload the extension." : "Error: " + e.message);
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
