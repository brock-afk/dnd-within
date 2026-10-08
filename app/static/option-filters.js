// Filters for spell lists and spell choice cards: by name, school, and ritual.
//
// Works on any [data-filter-item] inside the filter bar's nearest [data-filter-scope], and
// hides [data-filter-group] sections left empty. Filtering only hides items: hidden choice
// cards stay in their form, so picks you've already made are kept and still submitted.
// Listens on the document, so content htmx swaps in later works too.
document.addEventListener("input", (event) => {
  const bar = event.target.closest(".option-filters");
  if (bar) applyFilters(bar);
});

function applyFilters(bar) {
  const scope = bar.closest("[data-filter-scope]");
  const name = bar.querySelector('[data-filter="name"]').value.trim().toLowerCase();
  const school = bar.querySelector('[data-filter="school"]').value;
  const ritual = bar.querySelector('[data-filter="ritual"]').value; // "", "only" or "hide"

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
