const collapseStore = {
  get(key) {
    try {
      return JSON.parse(localStorage.getItem(key)) || {};
    } catch {
      return {};
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
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

document.addEventListener("click", (event) => {
  const summary = event.target.closest("summary");
  const section = summary && summary.parentElement;
  if (section && event.target.closest("[data-summary-action]")) {
    event.preventDefault();
    section.open = true;
    return;
  }
  if (section && section.matches("[data-collapse]")) {
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
window.addEventListener("pageshow", restoreSections);
document.addEventListener("htmx:after:settle", restoreSections);

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
