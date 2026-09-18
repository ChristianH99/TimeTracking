/* The month-end page: one tick for everybody.
 *
 * The whole page is "everybody, this month", and making somebody tick eleven
 * boxes to say so is a page that has missed its own point. Nothing else here —
 * the locking is a form post, because it is a thing that happens once a month
 * and a reload is the clearest possible confirmation that it happened.
 */
(function () {
  const all = document.querySelector("[data-tick-all]");
  if (!all) return;
  const ticks = Array.from(document.querySelectorAll("[data-tick]"));

  all.addEventListener("change", () => {
    ticks.forEach((tick) => { tick.checked = all.checked; });
  });

  /* And back the other way: unticking one person must not leave the header box
     claiming everybody is chosen. `indeterminate` is the honest third state —
     some, which is neither of the two the box can be clicked into. */
  ticks.forEach((tick) => {
    tick.addEventListener("change", () => {
      const chosen = ticks.filter((one) => one.checked).length;
      all.checked = chosen === ticks.length;
      all.indeterminate = chosen > 0 && chosen < ticks.length;
    });
  });
})();
