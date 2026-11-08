function storage(area) {
  return {
    get(key) {
      try {
        return JSON.parse(area().getItem(key));
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        area().setItem(key, JSON.stringify(value));
      } catch {
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

document.addEventListener("input", (event) => {
  const bar = event.target.closest(".option-filters");
  const scope = bar && bar.closest("[data-filter-scope]");
  if (!scope) return;
  store.set(filtersKey(scope), Object.fromEntries(FIELDS.map((f) => [f, control(bar, f).value])));
  applyFilters(scope);
});

document.addEventListener("click", (event) => {
  const summary = event.target.closest("summary");
  const group = summary && summary.parentElement;
  if (!group || !group.matches("[data-filter-group]")) return;
  const scope = group.closest("[data-filter-scope]");
  if (!scope) return;
  const saved = groupStore.get(groupsKey(scope)) || {};
  saved[group.dataset.filterGroup] = !group.open;
  groupStore.set(groupsKey(scope), saved);
});

function applyFilters(scope) {
  const bar = scope.querySelector(".option-filters");
  if (!bar) return;
  const name = control(bar, "name").value.trim().toLowerCase();
  const school = control(bar, "school").value;
  const ritual = control(bar, "ritual").value;

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
window.addEventListener("pageshow", restoreAll);
document.addEventListener("htmx:after:settle", restoreAll);
