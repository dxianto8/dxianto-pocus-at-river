// Catering order: minus/plus buttons beside each quantity, and a running estimated total.
// Without JavaScript the quantity boxes work on their own and the server works out the total.
(() => {
  const form = document.querySelector("[data-catering-order]");
  if (!form) return;
  const inputs = [...form.querySelectorAll(".qty__input")];
  const total = form.querySelector("[data-order-total]");
  const count = form.querySelector("[data-order-count]");
  const quoted = form.querySelector("[data-order-quoted]");
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const quantity = (input) => Math.max(0, Math.min(1000, parseInt(input.value, 10) || 0));

  const update = () => {
    let sum = 0;
    let items = 0;
    let unpriced = false;
    for (const input of inputs) {
      const n = quantity(input);
      if (!n) continue;
      items += n;
      if (input.dataset.price) sum += n * Number(input.dataset.price);
      else unpriced = true;
    }
    total.textContent = money.format(sum);
    count.textContent = items ? `${items} item${items === 1 ? "" : "s"} chosen` : "No items yet";
    quoted.hidden = !unpriced;
  };

  for (const input of inputs) {
    const name = input.closest(".order-item")?.querySelector("h3")?.textContent.trim() || "item";
    const step = (delta, symbol, label) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "qty__step";
      button.textContent = symbol;
      button.setAttribute("aria-label", `${label} ${name}`);
      button.addEventListener("click", () => {
        input.value = Math.max(0, Math.min(1000, quantity(input) + delta)) || "";
        update();
      });
      return button;
    };
    input.before(step(-1, "\u2212", "One fewer"));
    input.after(step(1, "+", "One more"));
  }
  form.addEventListener("input", update);
  update();
})();
