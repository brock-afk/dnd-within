// Live shared view: listens for "changed" from the server (GET <view>/events, server-sent
// events) and refreshes the page in place through the hidden refresher element
// (sharing/partials/auto_refresh.html), which morphs in the latest version. EventSource
// reconnects by itself; the refresher's slow poll covers anything missed meanwhile.

const refresher = () => document.querySelector("[data-live-events]");
let pending = null;

function start() {
  const element = refresher();
  if (!element) return;
  const events = new EventSource(element.dataset.liveEvents);
  events.onmessage = () => {
    // A burst of changes (several pips clicked) becomes one refresh.
    clearTimeout(pending);
    pending = setTimeout(() => refresher()?.dispatchEvent(new CustomEvent("refresh")), 200);
  };
}

document.addEventListener("DOMContentLoaded", start);
