// Asks before leaving a page with unsaved edits in a form marked data-unsaved-guard (the
// homebrew item editor). Any typing or change marks it edited; leaving by any means (a link,
// Cancel, back, closing the tab) then gets the browser's "Leave page?" confirmation.
//
// Saving is the exception: once the form itself is submitted, the redirect that follows a
// good save leaves without asking. If the save comes back with problems instead, the form is
// redrawn and the edits are unsaved again.

let edited = false;
let saving = false;

function inGuardedForm(element) {
  return element?.closest?.("[data-unsaved-guard]") != null;
}

for (const type of ["input", "change"]) {
  document.addEventListener(type, (event) => {
    if (inGuardedForm(event.target)) edited = true;
  });
}

// Only the form's own submit is a save; its Add/Remove row buttons just redraw it.
document.addEventListener("htmx:before:request", (event) => {
  if (event.target?.matches?.("form[data-unsaved-guard]")) saving = true;
});
document.addEventListener("htmx:after:settle", () => {
  saving = false; // a redraw (row added, or a save with problems): still unsaved
});

window.addEventListener("beforeunload", (event) => {
  if (edited && !saving) {
    event.preventDefault();
    event.returnValue = ""; // older browsers need this to show the prompt
  }
});
