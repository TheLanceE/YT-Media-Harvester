// Asks the background worker (background.js) to run a helper command. Resolves with the reply, or throws an
// Error whose message explains what went wrong. A missing native host is reported as OFFLINE.
const OFFLINE = "Helper couldn't start. Run install.bat once, then reload the extension.";

async function helper(cmd, args = {}) {
  const r = await chrome.runtime.sendMessage({ cmd, args });
  if (r?.ok) return r;
  const error = r?.error || "no reply";
  throw new Error(/native messaging host|host not found|exited|forbidden/i.test(error) ? OFFLINE : error);
}
