// Filters and collapsible sections for spell lists and spell choice cards.
//
// A filter scope is an element with data-filter-scope="<key>" containing a filter bar
// (.option-filters), filterable items ([data-filter-item]) and collapsible sections
// (details[data-filter-group="<label>"]). Filtering only hides items: hidden choice cards stay
// in their form, so picks you've already made are kept and still submitted.
//
// Each scope's filters are remembered for the browser session (sessionStorage), and which
// sections are open for good (localStorage); both are re-applied after a reload and after every
// htmx swap (like the in-place refresh after casting a spell), which would otherwise redraw
// everything unfiltered and the way the server rendered it. A section's `open` attribute is its
// default until the player toggles it.

function storage(area) {
  return {
    get(key) {
      try {
        return JSON.parse(area().getItem(key));
      } catch {
        return null; // storage blocked or unreadable: just don't remember
      }
    },
    set(key, value) {
      try {
        area().setItem(key, JSON.stringify(value));
      } catch {
        // storage blocked: filtering still works on the current page
      }
    },
  };
}
const store = storage(() => sessionStorage);
const groupStore = storage(() => localStorage);

const FIELDS = ["name", "school", "ritual"];
const filtersKey = (scope) => `filters:${scope.dataset.filterScope}`;
const groupsKey = (scope) => `groups:${scope.dataset.filterScope}`;
const control = (bar, field) => bar.querySelector(`[data-filter="${field}"]`);

// Typing or choosing in a filter: remember it and apply it.
document.addEventListener("input", (event) => {
  const bar = event.target.closest(".option-filters");
  const scope = bar && bar.closest("[data-filter-scope]");
  if (!scope) return;
  store.set(filtersKey(scope), Object.fromEntries(FIELDS.map((f) => [f, control(bar, f).value])));
  applyFilters(scope);
});

// Opening or closing a section. Saved from the click (which keyboard Enter/Space also fire)
// rather than the `toggle` event, because morphing the page fires `toggle` too.
document.addEventListener("click", (event) => {
  const summary = event.target.closest("summary");
  const group = summary && summary.parentElement;
  if (!group || !group.matches("[data-filter-group]")) return;
  const scope = group.closest("[data-filter-scope]");
  if (!scope) return;
  // The click toggles the section after this handler runs, so `!group.open` is its new state.
  const saved = groupStore.get(groupsKey(scope)) || {};
  saved[group.dataset.filterGroup] = !group.open;
  groupStore.set(groupsKey(scope), saved);
});

function applyFilters(scope) {
  const bar = scope.querySelector(".option-filters");
  if (!bar) return;
  const name = control(bar, "name").value.trim().toLowerCase();
  const school = control(bar, "school").value;
  const ritual = control(bar, "ritual").value; // "", "only" or "hide"

  let shown = 0;
  for (const item of scope.querySelectorAll("[data-filter-item]")) {
    const isRitual = item.dataset.ritual === "1";
    const match =
      (!name || item.dataset.name.includes(name)) &&
      (!school || item.dataset.school === school) &&
      (ritual !== "only" || isRitual) &&
      (ritual !== "hide" || !isRitual);
    item.hidden = !match;
    if (match) shown++;
  }
  for (const group of scope.querySelectorAll("[data-filter-group]")) {
    group.hidden = !group.querySelector("[data-filter-item]:not([hidden])");
  }
  bar.querySelector(".filter-empty").hidden = shown > 0;
}

// Put every scope on the page back the way the player left it.
function restoreAll() {
  for (const scope of document.querySelectorAll("[data-filter-scope]")) {
    const bar = scope.querySelector(".option-filters");
    const saved = store.get(filtersKey(scope));
    if (bar && saved) {
      for (const field of FIELDS) control(bar, field).value = saved[field] ?? "";
    }
    applyFilters(scope);
    const openGroups = groupStore.get(groupsKey(scope)) || {};
    for (const group of scope.querySelectorAll("[data-filter-group]")) {
      const open = openGroups[group.dataset.filterGroup];
      if (typeof open === "boolean") group.open = open;
    }
  }
}

document.addEventListener("DOMContentLoaded", restoreAll);
window.addEventListener("pageshow", restoreAll); // back/forward cache restores
document.addEventListener("htmx:after:settle", restoreAll); // after any htmx swap or morph
