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

document.addEventListener("htmx:before:request", (event) => {
  if (event.target?.matches?.("form[data-unsaved-guard]")) saving = true;
});
document.addEventListener("htmx:after:settle", () => {
  saving = false;
});

window.addEventListener("beforeunload", (event) => {
  if (edited && !saving) {
    event.preventDefault();
    event.returnValue = "";
  }
});
