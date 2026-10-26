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
