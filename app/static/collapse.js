// Collapsible page sections that remember whether they're open.
//
// A section is a <details data-collapse="<name>"> inside an element with
// data-collapse-scope="<key>" (e.g. "play-8": the Play sheet of character 8). Its `open`
// attribute in the template is the default; once the player opens or closes it, that choice is
// kept in localStorage and re-applied after a reload and after every htmx swap (morphing the
// page redraws sections the way the server rendered them).

const collapseStore = {
  get(key) {
    try {
      return JSON.parse(localStorage.getItem(key)) || {};
    } catch {
      return {}; // storage blocked or unreadable: sections use their defaults
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // storage blocked: toggling still works on the current page
    }
  },
};

const collapseKey = (scope) => `collapse:${scope.dataset.collapseScope}`;

function rememberSection(section, open) {
  const scope = section.closest("[data-collapse-scope]");
  if (!scope) return;
  const saved = collapseStore.get(collapseKey(scope));
  saved[section.dataset.collapse] = open;
  collapseStore.set(collapseKey(scope), saved);
}

// Opening or closing a section. Saved from the click (which keyboard Enter/Space also fire)
// rather than the `toggle` event, because morphing the page fires `toggle` too.
document.addEventListener("click", (event) => {
  const summary = event.target.closest("summary");
  const section = summary && summary.parentElement;
  if (section && section.matches("[data-collapse]")) {
    // The click toggles the section after this handler runs, so `!section.open` is its new state.
    rememberSection(section, !section.open);
  }
});

function restoreSections() {
  for (const scope of document.querySelectorAll("[data-collapse-scope]")) {
    const saved = collapseStore.get(collapseKey(scope));
    for (const section of scope.querySelectorAll("details[data-collapse]")) {
      const open = saved[section.dataset.collapse];
      if (open !== undefined) section.open = open;
    }
  }
}

document.addEventListener("DOMContentLoaded", restoreSections);
window.addEventListener("pageshow", restoreSections); // back/forward cache restores
document.addEventListener("htmx:after:settle", restoreSections); // after any htmx swap or morph
