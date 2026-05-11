if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      console.log("[PWA] Service Worker enregistré:", reg.scope);
    } catch (e) {
      console.warn("[PWA] SW non supporté:", e.message);
    }
  });
}

let deferredInstallPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  const btn = document.getElementById("btn-install-pwa");
  if (btn) {
    btn.style.display = "flex";
    btn.addEventListener("click", async () => {
      if (!deferredInstallPrompt) return;
      deferredInstallPrompt.prompt();
      await deferredInstallPrompt.userChoice;
      deferredInstallPrompt = null;
      btn.style.display = "none";
    });
  }
});

async function toggleTheme() {
  const current = document.documentElement.dataset.theme || "dark";
  const next    = current === "dark" ? "light" : "dark";
  await fetch("/api/settings/theme", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme: next }),
  });
  document.documentElement.dataset.theme = next;
  location.reload();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "t" && !e.target.matches("input, textarea, select")) toggleTheme();
});

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.style.cssText = `
    position: fixed; bottom: 5rem; right: 1.5rem;
    background: var(--bg3); color: var(--text);
    border: 1px solid var(--accent);
    padding: 0.75rem 1.25rem; border-radius: 8px;
    z-index: 9999; font-size: 0.875rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

async function apiPatch(path, body = {}) {
  const resp = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}
