// Motion is additive: content remains visible from its first paint.
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const EASE = 'cubic-bezier(.22, .61, .36, 1)';
  const running = new Set();

  const play = (element, keyframes, options = {}) => {
    if (!element || reduced.matches || typeof element.animate !== 'function') return null;
    const animation = element.animate(keyframes, {
      duration: 380, easing: EASE, fill: 'backwards', ...options,
    });
    running.add(animation);
    const forget = () => running.delete(animation);
    animation.addEventListener('finish', forget, {once: true});
    animation.addEventListener('cancel', forget, {once: true});
    return animation;
  };
  reduced.addEventListener('change', () => {
    if (reduced.matches) for (const animation of [...running]) animation.cancel();
  });

  // Never reset opacity or clip a photo after the browser has already painted it.
  const rise = (element, delay = 0, distance = 6) => play(element, [
    {transform: `translateY(${distance}px)`},
    {transform: 'none'},
  ], {delay});
  const all = selector => [...document.querySelectorAll(selector)];
  window.pocusMotion = {play, rise};

  all('.hero__text, .page-hero__text, .page-head, .auth__form, .auth-simple')
    .forEach(element => rise(element));

  // A small settling movement in the product. The rail and headings stay still.
  all('.workspace .next, .workspace .event-grid, .workspace .calendar, .workspace .panel--narrow')
    .forEach(element => rise(element, 0, 4));
  all('.meter span').forEach(bar => play(bar, [
    {transform: 'scaleX(.96)', transformOrigin: 'left'},
    {transform: 'scaleX(1)', transformOrigin: 'left'},
  ], {duration: 320}));

  // Only animate sections that start below the fold, once, with no delayed hiding.
  const onScroll = all(
    '[data-motion], .three article, .package, .feature > img, .gallery-grid figure'
  ).filter(element => !element.closest('.workspace') &&
    element.getBoundingClientRect().top >= window.innerHeight);
  if ('IntersectionObserver' in window && !reduced.matches && onScroll.length) {
    const observer = new IntersectionObserver(entries => {
      entries.filter(entry => entry.isIntersecting).forEach(entry => {
        observer.unobserve(entry.target);
        rise(entry.target, 0, 10);
      });
    }, {threshold: 0.08});
    onScroll.forEach(element => observer.observe(element));
  }

  const header = document.querySelector('.site-header');
  if (header) {
    const mark = () => header.classList.toggle('site-header--scrolled', window.scrollY > 8);
    mark();
    window.addEventListener('scroll', mark, {passive: true});
  }
})();
