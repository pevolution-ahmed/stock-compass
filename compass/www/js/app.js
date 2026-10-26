// Search box: Enter opens the highlighted (or first) hit, or the typed text as a ticker.
document.addEventListener("keydown", (event) => {
  const input = event.target.closest(".c-search input[type='text']");
  if (!input) return;
  const search = input.closest(".c-search");
  const hits = [...search.querySelectorAll(".c-search-hit")];

  if (event.key === "ArrowDown" && hits.length) {
    event.preventDefault();
    hits[0].focus();
  } else if (event.key === "Enter") {
    event.preventDefault();
    const symbol = hits.length ? hits[0].dataset.symbol : input.value.trim().toUpperCase();
    if (symbol) pick(search, symbol);
  } else if (event.key === "Escape") {
    input.blur();
  }
});

// Arrow keys move between hits once one has focus.
document.addEventListener("keydown", (event) => {
  const hit = event.target.closest(".c-search-hit");
  if (!hit || !["ArrowDown", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  const hits = [...hit.closest(".c-search").querySelectorAll(".c-search-hit")];
  const next = hits[hits.indexOf(hit) + (event.key === "ArrowDown" ? 1 : -1)];
  (next || hit.closest(".c-search").querySelector("input")).focus();
});

// Keep focus inside the search while pressing a hit so the panel doesn't close first.
document.addEventListener("mousedown", (event) => {
  if (event.target.closest(".c-search-panel")) event.preventDefault();
});

document.addEventListener("click", (event) => {
  const hit = event.target.closest(".c-search-hit, [data-pick-symbol]");
  if (!hit) return;
  const search = hit.closest(".c-search") || document.querySelector(".c-search");
  pick(search, hit.dataset.symbol || hit.dataset.pickSymbol);
});

function pick(search, symbol) {
  Shiny.setInputValue(search.dataset.pickInput, symbol, { priority: "event" });
  const input = search.querySelector("input[type='text']");
  input.value = "";
  input.dispatchEvent(new Event("change", { bubbles: true }));
  document.activeElement && document.activeElement.blur();
}

// Keep ?symbol= in the address bar in step with the selected ticker, without reloading.
Shiny.addCustomMessageHandler("compass-url", ({ symbol }) => {
  const url = new URL(window.location.href);
  document.title = `${symbol} · Stock Compass`;
  if (url.searchParams.get("symbol") === symbol) return;
  url.searchParams.set("symbol", symbol);
  window.history.replaceState(null, "", url);
});

// Scorecard parallax: tilt the hovered pillar toward the pointer; CSS layers it by depth.
// Mouse/pen only, and off when the visitor prefers reduced motion.
(() => {
  const MAX_TILT = 9; // degrees
  const canTilt = window.matchMedia("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)");
  let active = null;
  let frame = 0;

  const reset = (card) => {
    card.classList.remove("is-tilting");
    for (const name of ["--rx", "--ry", "--mx", "--my"]) card.style.removeProperty(name);
  };

  document.addEventListener("pointermove", (event) => {
    if (!canTilt.matches) return;
    const card = event.target.closest(".pillar");
    if (active && active !== card) reset(active);
    active = card;
    if (!card) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const box = card.getBoundingClientRect();
      const x = Math.min(Math.max((event.clientX - box.left) / box.width - 0.5, -0.5), 0.5);
      const y = Math.min(Math.max((event.clientY - box.top) / box.height - 0.5, -0.5), 0.5);
      card.style.setProperty("--rx", `${(-y * MAX_TILT).toFixed(2)}deg`);
      card.style.setProperty("--ry", `${(x * MAX_TILT).toFixed(2)}deg`);
      card.style.setProperty("--mx", x.toFixed(3));
      card.style.setProperty("--my", y.toFixed(3));
      card.classList.add("is-tilting");
    });
  });

  document.addEventListener("pointerleave", () => active && reset(active));
})();


// Any element with data-shiny-event="<input id>" sends its data-value to that input when clicked.
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-shiny-event]");
  if (!el) return;
  Shiny.setInputValue(el.dataset.shinyEvent, el.dataset.value, { priority: "event" });
});

// Watchlist persistence in this browser (no server storage).
const WATCHLIST_KEY = "compass.watchlist";
$(document).on("shiny:connected", () => {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(WATCHLIST_KEY)); } catch (e) { saved = null; }
  Shiny.setInputValue("watchlist-saved", Array.isArray(saved) ? saved : null);
});
Shiny.addCustomMessageHandler("compass-watchlist", (symbols) => {
  try { localStorage.setItem(WATCHLIST_KEY, JSON.stringify(symbols)); } catch (e) { /* storage blocked */ }
});
