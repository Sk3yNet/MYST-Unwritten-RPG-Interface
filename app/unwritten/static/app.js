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

// ---- maps: click an area ---------------------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const hot = e.target.closest && e.target.closest("[data-hot]");
  if (!hot) return;
  const svg = hot.closest("svg.map-svg");
  const cid = document.body.dataset.cid;
  const map = svg.dataset.map, area = hot.dataset.hot;
  if (svg.classList.contains("gm")) {
    htmx.ajax("GET", `/c/${cid}/run/area/${map}/${area}`, { target: "#area-panel", swap: "innerHTML" });
  } else if (hot.classList.contains("revealed")) {
    htmx.ajax("GET", `/c/${cid}/me/area/${map}/${area}`, { target: "#area-panel", swap: "innerHTML" });
  } else if (hot.classList.contains("frontier")) {
    if (hot.classList.contains("pending")) { toast("Already asked: waiting on the GM."); return; }
    const holder = document.querySelector("[data-my-char]");
    if (!holder) { toast("Create your explorer first."); return; }
    const title = hot.querySelector("title");
    if (confirm(`Ask the GM to let you explore “${title ? title.textContent : "this area"}”?`)) {
      htmx.ajax("POST", `/c/${cid}/map/request`, { values: { map, area, character_id: holder.dataset.myChar }, swap: "none" })
        .then(() => toast("Asked the GM."));
    }
  }
});
document.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches("[data-hot]")) {
    e.preventDefault();
    e.target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  }
});

// ---- suggestions: set up the roller ----------------------------------------------------------------------------
function prefillRoll(skill, action) {
  const r = document.getElementById("roller");
  if (!r) return;
  const sk = r.querySelector("select[name=skill]");
  if (sk && [...sk.options].some((o) => o.value === skill)) sk.value = skill;
  const act = r.querySelector("select[name=action]");
  const a = action === "advantage" ? "create" : action;
  if (act && [...act.options].some((o) => o.value === a)) act.value = a;
  r.scrollIntoView({ behavior: "smooth", block: "center" });
  r.classList.remove("glow"); void r.offsetWidth; r.classList.add("glow");
  const intent = r.querySelector("input[name=intent]");
  if (intent) intent.focus();
}

// ---- handouts: the GM pushes, players see it full-screen until they close it ---------------------------------
function dismissHandout(btn) {
  const o = btn.closest(".handout-overlay");
  try { sessionStorage.setItem("handout-" + document.body.dataset.cid, o.dataset.seq); } catch (e) {}
  o.remove();
}
document.addEventListener("htmx:afterSwap", (e) => {
  if (e.detail.target.id !== "handout") return;
  const o = e.detail.target.querySelector(".handout-overlay");
  if (!o) return;
  let seen = null;
  try { seen = sessionStorage.getItem("handout-" + document.body.dataset.cid); } catch (err) {}
  if (seen === o.dataset.seq) o.remove();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { const b = document.querySelector(".handout-overlay .handout-close"); if (b) b.click(); }
});
