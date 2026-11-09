document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-copy]");
  if (button) {
    navigator.clipboard.writeText(button.dataset.copy).then(() => {
      button.textContent = "Copied";
    });
  }
  const field = event.target.closest("input[data-select-all]");
  if (field) field.select();
});
