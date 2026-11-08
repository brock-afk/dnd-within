const refresher = () => document.querySelector("[data-live-events]");
let pending = null;

function start() {
  const element = refresher();
  if (!element) return;
  const events = new EventSource(element.dataset.liveEvents);
  events.onmessage = () => {
    clearTimeout(pending);
    pending = setTimeout(() => refresher()?.dispatchEvent(new CustomEvent("refresh")), 200);
  };
}

document.addEventListener("DOMContentLoaded", start);
