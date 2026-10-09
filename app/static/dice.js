// Dice rolling for any roll input.
//
// A button with data-roll="1d12" (and optionally data-roll-target="#input-id") rolls in the
// browser, fills the input, and shows the result next to the button. Players can still type
// their own roll for physical dice; the server validates either way. Listens on the document,
// so buttons htmx swaps in later work too.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-roll]");
  if (!button) return;
  const [count, sides] = button.dataset.roll.split("d").map(Number);
  const rolls = Array.from({ length: count }, () => rollDie(sides));
  const total = rolls.reduce((sum, n) => sum + n, 0);

  const input = button.dataset.rollTarget && document.querySelector(button.dataset.rollTarget);
  if (input) {
    input.value = total;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const result = button.parentElement.querySelector(".roll-result");
  if (result) result.textContent = count > 1 ? `rolled ${rolls.join(" + ")} = ${total}` : `rolled ${total}`;
});

// A fair roll: random 32-bit numbers from the browser's secure generator, rejecting the
// few at the top of the range that would make some faces slightly more likely.
function rollDie(sides) {
  const limit = Math.floor(0x100000000 / sides) * sides;
  const buffer = new Uint32Array(1);
  do {
    crypto.getRandomValues(buffer);
  } while (buffer[0] >= limit);
  return (buffer[0] % sides) + 1;
}
