// D'ni numbers, calendar and script, mirroring unwritten/dni.py (keep the two in step).
(function () {
  const KEYS = "0123456789)!@#$%^&*([]\\{}";
  const VAILEETEE = ["Leefo", "Leebro", "Leesahn", "Leetar", "Leevot", "Leevofo", "Leevobro", "Leevosahn", "Leevotar", "Leenovoo"];
  const HAHR = 31556925.216, YAHR = HAHR / 290;
  const EPOCH = Date.UTC(1998, 3, 21, 16, 54, 16) / 1000, EPOCH_HAHR = 9654;

  function base25(n) {
    const d = [n % 25];
    n = Math.floor(n / 25);
    while (n) { d.unshift(n % 25); n = Math.floor(n / 25); }
    return d;
  }
  const toFont = (n) => base25(n).map((d) => KEYS[d]).join("");

  function toDni(date) {
    const secs = date.getTime() / 1000 - EPOCH;
    const off = Math.floor(secs / HAHR);
    const into = secs - off * HAHR;
    const yi = Math.floor(into / YAHR);
    const frac = (into - yi * YAHR) / YAHR;
    let pro = Math.floor(frac * 78125);
    const gahr = Math.floor(pro / 15625); pro %= 15625;
    const pahr = Math.floor(pro / 3125); pro %= 3125;
    const tahvo = Math.floor(pro / 625); pro %= 625;
    const gorahn = Math.floor(pro / 25), prorahn = pro % 25;
    const v = Math.floor(yi / 29);
    return { hahr: EPOCH_HAHR + off, vailee: v + 1, name: VAILEETEE[v], yahr: (yi % 29) + 1,
             gahr, pahr, tahvo, gorahn, prorahn, bell: gahr * 5 + pahr + 1 };
  }
  function fromDni(hahr, vailee, yahr, bell) {
    const secs = (hahr - EPOCH_HAHR) * HAHR + ((vailee - 1) * 29 + yahr - 1) * YAHR + (bell - 1) / 25 * YAHR;
    return new Date((EPOCH + secs) * 1000);
  }
  const pad = (n) => String(n).padStart(2, "0");
  const fmt = (d) => `${d.name} ${d.yahr}, ${d.hahr} DE`;
  const fmtTime = (d) => `${d.gahr}:${pad(d.pahr)}:${pad(d.tahvo)}:${pad(d.gorahn)}`;

  const DIGRAPHS = [["sh", "S"], ["kh", "k"], ["th", "T"], ["dh", "d"], ["ch", "c"], ["ts", "x"], ["ah", "a"],
                    ["ee", "E"], ["eh", "e"], ["ai", "A"], ["oy", "O"], ["uh", "u"], ["oo", "U"], ["í", "I"]];
  const SINGLE = { k: "K", d: "D", "’": "'" };
  const ALLOWED = new Set("vbtsSjgykKaIfpiEeArmTdDhoOcwuUxlzn.-' ");
  function transcribe(text) {
    const s = text.toLowerCase();
    let out = "", i = 0;
    outer: while (i < s.length) {
      for (const [src, key] of DIGRAPHS) {
        if (s.startsWith(src, i)) { out += key; i += src.length; continue outer; }
      }
      const key = SINGLE[s[i]] || s[i];
      out += ALLOWED.has(key) ? key : "";
      i++;
    }
    return out.replace(/ +/g, " ");
  }

  const $ = (id) => document.getElementById(id);
  function on(id, ev, fn) { const el = $(id); if (el) { el.addEventListener(ev, fn); fn(); } }

  function tick() {
    const d = toDni(new Date());
    if ($("dni-now")) {
      $("dni-now").innerHTML = `${fmt(d)} · bell ${d.bell} <span class="dni">${toFont(d.bell)}</span>`;
      $("dni-now-detail").textContent = `Time ${fmtTime(d)} (gahrtahvo:pahrtahvo:tahvo:gorahn) · hahr ${toFont(d.hahr)} in D’ni digits is ${d.hahr}`;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    tick();
    setInterval(tick, 5000);

    on("num-in", "input", () => {
      const n = Math.max(0, Math.floor(Number($("num-in").value) || 0));
      const d = base25(n);
      $("num-out").textContent = toFont(n);
      $("num-explain").textContent = d.map((x, i) => `${x} × 25^${d.length - 1 - i}`).join(" + ") + ` = ${n}`;
    });
    on("num-keys", "input", () => {
      const v = $("num-keys").value;
      const digits = [...v].filter((c) => KEYS.includes(c)).map((c) => KEYS.indexOf(c));
      $("num-back").innerHTML = digits.length
        ? `<span class="dni">${digits.map((x) => KEYS[x]).join("")}</span> = ${digits.reduce((a, x) => a * 25 + x, 0)}` : "";
    });

    const g = $("greg-in");
    if (g) {
      const now = new Date();
      g.value = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
      on("greg-in", "input", () => {
        const t = new Date(g.value);
        if (isNaN(t)) { $("greg-out").textContent = ""; return; }
        const d = toDni(t);
        $("greg-out").innerHTML = `${fmt(d)} · bell ${d.bell} <span class="dni">${toFont(d.hahr)}</span>`;
      });
    }
    const back = () => {
      const t = fromDni(+$("d-hahr").value, +$("d-vailee").value, +$("d-yahr").value, +$("d-bell").value || 1);
      $("dni-back").textContent = isNaN(t) ? "" : t.toLocaleString(undefined, { dateStyle: "full", timeStyle: "short" });
    };
    ["d-hahr", "d-vailee", "d-yahr", "d-bell"].forEach((id) => on(id, "input", back));

    on("script-in", "input", () => {
      const k = transcribe($("script-in").value);
      $("script-out").textContent = k;
      $("script-keys").textContent = k;
    });
  });
})();
