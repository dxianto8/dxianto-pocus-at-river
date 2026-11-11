// Hero photo parallax, copied from the original site: the photo moves down 0.8px for every
// pixel scrolled, so on screen it travels at 20% of the page's speed. Off for reduced motion.
(() => {
  const layer = document.querySelector("[data-parallax]");
  if (!layer) return;

  const lag = Number(layer.dataset.parallax) || 0.8;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let frame = 0;

  const update = () => {
    frame = 0;
    if (reducedMotion.matches) {
      layer.style.transform = "";
      return;
    }
    // Past two screens the hero is long gone, so stop moving it.
    const scrolled = Math.min(window.scrollY, window.innerHeight * 2);
    layer.style.transform = `translate3d(0, ${scrolled * lag}px, 0)`;
  };

  window.addEventListener("scroll", () => {
    if (!frame) frame = requestAnimationFrame(update);
  }, { passive: true });
  reducedMotion.addEventListener("change", update);
  update();
})();
