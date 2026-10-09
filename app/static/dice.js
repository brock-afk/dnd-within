// Dice rolling for any roll input.
//
// A button with data-roll="1d12" (and optionally data-roll-target="#input-id") rolls in the
// browser, fills the input, and shows the result next to the button. Players can still type
// their own roll for physical dice; the server validates either way. Listens on the document,
// so buttons htmx swaps in later work too.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-roll]");
  if (!button) return;
  const { count, sides, bonus } = parseDice(button.dataset.roll);
  const rolls = Array.from({ length: count }, () => rollDie(sides));
  const total = rolls.reduce((sum, n) => sum + n, 0) + bonus;

  const input = button.dataset.rollTarget && document.querySelector(button.dataset.rollTarget);
  if (input) {
    input.value = total;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const result = button.parentElement.querySelector(".roll-result");
  if (result) result.textContent = describe(rolls, bonus, total);
});

// "2d6", "1d20+3" or "1d20-1" -> { count, sides, bonus }.
function parseDice(notation) {
  const [, count, sides, bonus] = notation.match(/^(\d+)d(\d+)([+-]\d+)?$/);
  return { count: Number(count), sides: Number(sides), bonus: Number(bonus || 0) };
}

// "rolled 7", "rolled 3 + 4 = 7", "rolled 14 + 3 = 17", "rolled 9 − 1 = 8".
function describe(rolls, bonus, total) {
  const parts = rolls.join(" + ") + (bonus > 0 ? ` + ${bonus}` : bonus < 0 ? ` − ${-bonus}` : "");
  return rolls.length > 1 || bonus ? `rolled ${parts} = ${total}` : `rolled ${total}`;
}

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
