document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy]");
  if (button) {
    const copying = navigator.clipboard?.writeText(button.dataset.copy) ?? Promise.reject();
    copying.then(
      () => {
        button.textContent = "Copied";
      },
      () => {
        button.closest(".share-link")?.querySelector("input")?.select();
        button.textContent = "Copy the selected text";
      },
    );
  }
  const field = event.target.closest("input[data-select-all]");
  if (field) field.select();
});
