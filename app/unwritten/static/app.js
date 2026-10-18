// Unwritten Table: small client helpers on top of htmx.

function toggleTheme() {
  const root = document.documentElement;
  const next = root.dataset.theme === "cavern" ? "" : "cavern";
  if (next) root.dataset.theme = next; else delete root.dataset.theme;
  try { localStorage.setItem("theme", next); } catch (e) {}
}

function toast(msg, kind) {
  const box = document.getElementById("toasts");
  if (!box) return;
  const t = document.createElement("div");
  t.className = "toast" + (kind ? " " + kind : "");
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 6000 : 3000);
}

function copyText(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.select();
  (navigator.clipboard ? navigator.clipboard.writeText(el.value) : Promise.reject()).then(
    () => toast("Copied."), () => { document.execCommand("copy"); toast("Copied."); });
}

// Server errors arrive as plain text: show them as a toast instead of swapping them in.
document.addEventListener("htmx:responseError", (e) => {
  toast(e.detail.xhr.responseText || ("Error " + e.detail.xhr.status), "error");
});
document.addEventListener("htmx:sendError", () => toast("Can't reach the server.", "error"));

// Don't redraw a panel under someone's pen: while someone is typing inside a [data-keep-focus] element, a refresh
// (both the request and a response already in flight) waits until focus leaves the element.
function deferWhileTyping(elt) {
  if (!elt || !elt.matches || !elt.matches("[data-keep-focus]")) return false;
  const a = document.activeElement;
  const typing = a && a.matches && a.matches("input:not([type=checkbox]):not([type=submit]), textarea, select");
  if (!typing || !elt.contains(a)) return false;
  if (!elt.dataset.pending) {
    elt.dataset.pending = "1";
    elt.addEventListener("focusout", function later(ev) {
      if (elt.contains(ev.relatedTarget)) return;
      elt.removeEventListener("focusout", later);
      delete elt.dataset.pending;
      // Let the field's own change request go out first.
      setTimeout(() => htmx.trigger(elt, "refresh"), 150);
    });
  }
  return true;
}
document.addEventListener("htmx:beforeRequest", (e) => {
  if (e.detail.requestConfig && e.detail.requestConfig.verb !== "get") return;
  if (deferWhileTyping(e.detail.elt)) e.preventDefault();
});
document.addEventListener("htmx:beforeSwap", (e) => {
  if (e.detail.requestConfig && e.detail.requestConfig.verb !== "get") return;
  if (deferWhileTyping(e.detail.elt)) e.detail.shouldSwap = false;
});

// Freshly rolled dice tumble once.
document.addEventListener("htmx:afterSwap", (e) => {
  const first = e.detail.target.querySelector && e.detail.target.querySelector(".log li:first-child .die");
  if (first) e.detail.target.querySelectorAll(".log li:first-child .die").forEach((d) => d.classList.add("fresh"));
});

// The SSE stream reconnects by itself; when it does, catch up on anything missed.
document.addEventListener("htmx:sseOpen", () => {
  if (window.__sseOpened) {
    ["scene", "log", "party", "deduction", "timeline"].forEach((t) => htmx.trigger(document.body, t));
  }
  window.__sseOpened = true;
});
