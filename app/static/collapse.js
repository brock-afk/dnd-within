// Collapsible page sections that remember whether they're open, and popovers.
//
// A section is a <details data-collapse="<name>"> inside an element with
// data-collapse-scope="<key>" (e.g. "play-8": the Play sheet of character 8). Its `open`
// attribute in the template is the default; once the player opens or closes it, that choice is
// kept in localStorage and re-applied after a reload and after every htmx swap (morphing the
// page redraws sections the way the server rendered them).
//
// A popover is a <details data-popover> whose content opens over the page (the HP and AC panels,
// the long rest confirmation). It closes on a click anywhere outside it, or on Escape. With
// data-popover-stays (and an id), it also stays open after a request sent from inside it, like
// adding or ending effects one after another; the page refresh would otherwise close it.

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

// Popovers: a click outside an open one closes it (a click inside, like a form button, doesn't).
document.addEventListener("click", (event) => {
  for (const popover of document.querySelectorAll("details[data-popover][open]")) {
    if (!popover.contains(event.target)) popover.open = false;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  for (const popover of document.querySelectorAll("details[data-popover][open]")) {
    popover.open = false;
    if (popover.contains(document.activeElement)) popover.querySelector("summary").focus();
  }
});

// Popovers that stay: remember the one a request came from, and reopen it once the page has
// been refreshed.
let reopenPopover = null;
document.addEventListener("htmx:before:request", (event) => {
  const popover = event.target.closest?.("details[data-popover-stays][open]");
  reopenPopover = popover ? popover.id : null;
});
document.addEventListener("htmx:after:settle", () => {
  const popover = reopenPopover && document.getElementById(reopenPopover);
  if (popover) popover.open = true;
  reopenPopover = null;
});
