// Talks to the local helper. Every request carries the token that the native host (install.bat) hands out.
const API = "http://127.0.0.1:8765";
const NATIVE_HOST = "com.yt_tab_downloader.helper";

// Starts the helper if it isn't running and returns its token, or null if the native host isn't installed.
let starting = null;
function startHelper() {
  return starting ??= (async () => {
    const r = await chrome.runtime.sendNativeMessage(NATIVE_HOST, { cmd: "start" }).catch(() => null);
    if (r?.ok && r.token) await chrome.storage.session.set({ token: r.token });
    starting = null;
    return r?.ok ? r.token ?? null : null;
  })();
}

// fetch() against the helper. Throws a TypeError when the helper can't be reached or started.
async function helperFetch(path, init = {}) {
  let { token } = await chrome.storage.session.get("token");
  for (let retried = false; ; retried = true) {
    token ||= await startHelper();
    if (!token) throw new TypeError("helper unavailable");
    try {
      const r = await fetch(API + path, { ...init, headers: { ...init.headers, "X-Helper-Token": token } });
      if (r.status !== 401 || retried) return r;
    } catch (e) {
      if (retried) throw e;
    }
    token = null; // helper stopped or token changed: ask the native host again
  }
}
