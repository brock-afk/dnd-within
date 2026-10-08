// Filters for choice cards (spells by name, school, and ritual).
//
// Filtering only hides cards: hidden cards stay in the form, so picks you've already made are
// kept and still submitted. Listens on the document, so forms that htmx swaps in later work too.
document.addEventListener("input", (event) => {
  const bar = event.target.closest(".option-filters");
  if (bar) applyFilters(bar);
});

function applyFilters(bar) {
  const form = bar.closest("form");
  const name = bar.querySelector('[data-filter="name"]').value.trim().toLowerCase();
  const school = bar.querySelector('[data-filter="school"]').value;
  const ritualsOnly = bar.querySelector('[data-filter="ritual"]').checked;

  let shown = 0;
  for (const card of form.querySelectorAll(".choice")) {
    const match =
      (!name || card.dataset.name.includes(name)) &&
      (!school || card.dataset.school === school) &&
      (!ritualsOnly || card.dataset.ritual === "1");
    card.hidden = !match;
    if (match) shown++;
  }
  // Hide spell-level sections with nothing left in them.
  for (const group of form.querySelectorAll(".choice-group")) {
    group.hidden = !group.querySelector(".choice:not([hidden])");
  }
  bar.querySelector(".filter-empty").hidden = shown > 0;
}
