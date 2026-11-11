// Keep the original parallax speed, with a short, frame-rate-independent ease
// so coarse wheel events don't make the hero photo jump. Native scrolling stays native.
(() => {
  const layer = document.querySelector("[data-parallax]");
  if (!layer) return;

  const lag = Number(layer.dataset.parallax) || 0.8;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const scrollTarget = () => Math.max(0, Math.min(window.scrollY, window.innerHeight * 2)) * lag;
  let target = scrollTarget();
  let current = target;
  let frame = 0;
  let lastTime = null;

  const paint = () => {
    layer.style.transform = reducedMotion.matches ? "" : `translate3d(0, ${current}px, 0)`;
  };

  const animate = (time) => {
    frame = 0;
    const elapsed = lastTime === null ? 1000 / 60 : Math.min(time - lastTime, 64);
    lastTime = time;
    current += (target - current) * (1 - Math.exp(-elapsed / 70));
    if (Math.abs(target - current) < 0.1) current = target;
    paint();
    if (current !== target) {
      frame = requestAnimationFrame(animate);
    } else {
      lastTime = null;
    }
  };

  const update = () => {
    target = scrollTarget();
    if (!reducedMotion.matches && !frame) frame = requestAnimationFrame(animate);
  };

  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update, { passive: true });
  reducedMotion.addEventListener("change", () => {
    cancelAnimationFrame(frame);
    frame = 0;
    lastTime = null;
    current = target = scrollTarget();
    paint();
  });
  paint();
})();
