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

function parseDice(notation) {
  const [, count, sides, bonus] = notation.match(/^(\d+)d(\d+)([+-]\d+)?$/);
  return { count: Number(count), sides: Number(sides), bonus: Number(bonus || 0) };
}

function describe(rolls, bonus, total) {
  const parts = rolls.join(" + ") + (bonus > 0 ? ` + ${bonus}` : bonus < 0 ? ` − ${-bonus}` : "");
  return rolls.length > 1 || bonus ? `rolled ${parts} = ${total}` : `rolled ${total}`;
}

function rollDie(sides) {
  const limit = Math.floor(0x100000000 / sides) * sides;
  const buffer = new Uint32Array(1);
  do {
    crypto.getRandomValues(buffer);
  } while (buffer[0] >= limit);
  return (buffer[0] % sides) + 1;
}
