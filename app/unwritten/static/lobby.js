// The lobby: curtains, choosing a Book, and the shared launch every screen plays together.
(function () {
  const $ = (id) => document.getElementById(id);
  const theater = () => $("theater");
  const cid = () => document.body.dataset.cid;
  let chosen = null;
  let audio = null;

  // ---- sound: browsers stay silent until the page is clicked, so any click unlocks it --------------------------
  window.unlockAudio = function (test) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      if (test === true) linkSound(0.5);
    } catch (e) {}
  };
  document.addEventListener("pointerdown", () => window.unlockAudio(), { once: true });

  // An original linking sound: a breathy rush that rises and falls, a shimmer gliding up, and a soft low thump.
  function linkSound(volume = 1) {
    if (!audio) return;
    const t = audio.currentTime;
    const out = audio.createGain();
    out.gain.value = 0.9 * volume;
    out.connect(audio.destination);

    const len = 2.8;
    const buf = audio.createBuffer(1, Math.floor(audio.sampleRate * len), audio.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const noise = audio.createBufferSource();
    noise.buffer = buf;
    const band = audio.createBiquadFilter();
    band.type = "bandpass"; band.Q.value = 1.4;
    band.frequency.setValueAtTime(260, t);
    band.frequency.exponentialRampToValueAtTime(2600, t + 0.9);
    band.frequency.exponentialRampToValueAtTime(180, t + 2.6);
    const ng = audio.createGain();
    ng.gain.setValueAtTime(0.0001, t);
    ng.gain.exponentialRampToValueAtTime(0.55, t + 0.6);
    ng.gain.exponentialRampToValueAtTime(0.0001, t + 2.7);
    noise.connect(band).connect(ng).connect(out);
    noise.start(t); noise.stop(t + len);

    [[220, 0], [331, 0.05], [440, 0.1]].forEach(([f, d]) => {
      const o = audio.createOscillator();
      o.type = "sine";
      o.frequency.setValueAtTime(f, t + d);
      o.frequency.exponentialRampToValueAtTime(f * 3.2, t + 1.0);
      o.frequency.exponentialRampToValueAtTime(f * 0.6, t + 2.4);
      const g = audio.createGain();
      g.gain.setValueAtTime(0.0001, t + d);
      g.gain.exponentialRampToValueAtTime(0.09, t + 0.5);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 2.4);
      o.connect(g).connect(out);
      o.start(t + d); o.stop(t + 2.5);
    });

    const thump = audio.createOscillator();
    thump.type = "sine";
    thump.frequency.setValueAtTime(90, t + 1.9);
    thump.frequency.exponentialRampToValueAtTime(38, t + 2.6);
    const tg = audio.createGain();
    tg.gain.setValueAtTime(0.0001, t + 1.9);
    tg.gain.exponentialRampToValueAtTime(0.7, t + 1.95);
    tg.gain.exponentialRampToValueAtTime(0.0001, t + 2.7);
    thump.connect(tg).connect(out);
    thump.start(t + 1.9); thump.stop(t + 2.8);
  }

  // ---- choosing a book ------------------------------------------------------------------------------------------
  window.pickBook = function (el) {
    document.querySelectorAll(".bk.live.peek").forEach((b) => b.classList.remove("peek"));
    el.classList.add("peek");
    chosen = el;
    const card = $("book-card");
    $("card-title").textContent = el.dataset.title;
    $("card-summary").textContent = el.dataset.summary;
    $("card-players").textContent = [el.dataset.volume, el.dataset.players].filter(Boolean).join(" · ");
    const cover = $("card-cover");
    cover.style.setProperty("--c", el.style.getPropertyValue("--c"));
    cover.innerHTML = el.dataset.cover ? `<img src="${el.dataset.cover}" alt="">` : "";
    card.hidden = false;
  };
  window.closeCard = function () {
    $("book-card").hidden = true;
    document.querySelectorAll(".bk.live.peek").forEach((b) => b.classList.remove("peek"));
  };
  window.openChosen = function () {
    if (!chosen) return;
    window.unlockAudio();
    const c = document.querySelector(".candles");
    const ready = +(c && c.dataset.ready), total = +(c && c.dataset.total);
    if (c && ready < total && !confirm(`Only ${ready} of ${total} candles are lit. Open the Book anyway?`)) return;
    htmx.ajax("POST", `/c/${cid()}/lobby/launch`, { values: { slug: chosen.dataset.slug }, swap: "none" });
  };

  // ---- the launch, played on every screen at once ---------------------------------------------------------------
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  let launching = false;

  document.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target.id !== "launch-watch") return;
    const d = e.detail.target.querySelector(".launch-data");
    if (!d || launching) return;
    if (+d.dataset.seq <= +theater().dataset.seenSeq) return;  // never replay an old launch on reload
    theater().dataset.seenSeq = d.dataset.seq;
    runLaunch(d.dataset);
  });

  async function runLaunch(d) {
    launching = true;
    $("book-card").hidden = true;
    const shelfBook = document.querySelector(`.bk.live[data-slug="${CSS.escape(d.slug)}"]`);
    const stage = $("stage"), book = $("book3d");
    book.style.setProperty("--c", d.color);
    $("b3-cover").style.setProperty("--c", d.color);
    $("b3-title").textContent = d.title;
    $("b3-cover-title").textContent = d.title;
    $("b3-logo").innerHTML = d.cover ? `<img src="${d.cover}" alt="">` : "";
    $("b3-panel").innerHTML = d.preview ? `<img src="${d.preview}" alt="">` : "";
    $("b3-panel").classList.remove("playing");

    // 1. The book slides out of the shelf.
    if (shelfBook) { shelfBook.classList.add("pulled"); await wait(800); }

    // 2. It flies from the shelf to the middle of the stage, turning its cover to us.
    stage.hidden = false;
    let from = "translateX(-25%) translateY(30vh) scale(.3) rotateY(80deg)";
    if (shelfBook) {
      const r = shelfBook.getBoundingClientRect();
      const dx = r.left + r.width / 2 - window.innerWidth / 2;
      const dy = r.top + r.height / 2 - window.innerHeight / 2;
      from = `translate(${dx}px, ${dy}px) scale(.25) rotateY(80deg)`;
      shelfBook.classList.add("gone");
    }
    book.className = "book3d";
    book.style.transform = from;
    void book.offsetWidth;
    book.classList.add("fly");
    book.style.transform = "";
    stage.classList.add("dim");
    await wait(1500);

    // 3. A moment on the cover, then it opens to the Linking page.
    await wait(900);
    book.classList.remove("fly");
    book.classList.add("open");
    await wait(1500);

    // 4. The panel comes alive and lingers.
    $("b3-panel").classList.add("playing");
    await wait(4500);

    // 5. The link: the sound, the rush of light, the curtains close.
    linkSound();
    book.classList.add("linking");
    stage.classList.add("linking");
    await wait(2600);
    window.location.href = d.dest;
  }

  // ---- curtains open when the page arrives ----------------------------------------------------------------------
  // Spine titles shrink until they fit their spine.
  function fitSpines() {
    document.querySelectorAll(".spine-title").forEach((t) => {
      let size = 0.9;
      t.style.fontSize = size + "rem";
      while (t.scrollHeight > t.clientHeight + 1 && size > 0.55) {
        size -= 0.05;
        t.style.fontSize = size + "rem";
      }
    });
  }
  document.addEventListener("DOMContentLoaded", () => {
    fitSpines();
    if (document.fonts) document.fonts.ready.then(fitSpines);
    setTimeout(() => theater() && theater().classList.add("open"), 250);
  });
})();
