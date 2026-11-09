const invite = new URLSearchParams(location.hash.slice(1)).get("invite");
if (invite !== null) {
  const field = document.getElementById("invite_code");
  if (field) field.value = invite;
  history.replaceState(null, "", location.pathname + location.search);
}
