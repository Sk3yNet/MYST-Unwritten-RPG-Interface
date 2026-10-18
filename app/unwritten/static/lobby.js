// The lobby: curtains, choosing a Book, and the shared launch every screen plays together.
(function () {
  const $ = (id) => document.getElementById(id);
  const theater = () => $("theater");
  const cid = () => document.body.dataset.cid;
  let chosen = null;
  let audio = null;

  // ---- sound: browsers stay silent until the page is clicked, so any click unlocks it --------------------------
  // The linking sound is a fan-made recording (static/sounds/linking.mp3), decoded once and played through Web Audio.
  const LINK_SOUND = "/static/sounds/linking.mp3";
  const LINK_SOUND_MS = 4300;  // until its tail has faded
  let linkBuffer = null;

  function loadLinkSound() {
    if (!audio || linkBuffer) return;
    fetch(LINK_SOUND).then((r) => r.arrayBuffer())
      .then((b) => new Promise((ok, bad) => audio.decodeAudioData(b, ok, bad)))
      .then((buf) => { linkBuffer = buf; }).catch(() => {});
  }

  window.unlockAudio = function (test) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      loadLinkSound();
      if (test === true) setTimeout(() => linkSound(0.6), linkBuffer ? 0 : 400);
    } catch (e) {}
  };
  document.addEventListener("pointerdown", () => window.unlockAudio(), { once: true });

  function linkSound(volume = 1) {
    if (!audio || !linkBuffer) return;
    const src = audio.createBufferSource();
    src.buffer = linkBuffer;
    const gain = audio.createGain();
    gain.gain.value = volume;
    src.connect(gain).connect(audio.destination);
    src.start();
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

    // 5. The link: the sound swells as we fall into the panel, the light peaks with it, and we arrive as it fades.
    linkSound();
    book.classList.add("linking");
    stage.classList.add("linking");
    await wait(LINK_SOUND_MS);
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
