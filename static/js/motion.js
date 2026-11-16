// Quiet movement: one page dissolve, stationary text, and a one-time photograph glide.
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const running = new Set();
  const play = (element, keyframes, options = {}) => {
    if (!element || reduced.matches || typeof element.animate !== 'function') return null;
    const animation = element.animate(keyframes, {
      duration: 240, easing: 'cubic-bezier(.22, .61, .36, 1)', ...options,
    });
    running.add(animation);
    const forget = () => running.delete(animation);
    animation.addEventListener('finish', forget, {once: true});
    animation.addEventListener('cancel', forget, {once: true});
    return animation;
  };
  window.pocusMotion = {play};

  const frames = [...document.querySelectorAll('.photo-frame[data-photo-motion]')];
  const started = new WeakSet();
  const settle = frame => { frame.dataset.photoSettled = ''; };
  const glide = async frame => {
    if (started.has(frame)) return;
    started.add(frame);
    const photo = frame.querySelector('img');
    if (!photo) return;
    if (reduced.matches || typeof photo.animate !== 'function') { settle(frame); return; }
    try {
      // Move only real pixels, after the page dissolve. Never animate a loading placeholder.
      await Promise.all([photo.decode?.(), window.pocusPageTransition]);
    } catch {
      settle(frame);
      return;
    }
    if (reduced.matches || document.visibilityState === 'hidden') { settle(frame); return; }
    const animation = play(photo, [
      {transform: 'translateX(-3%) scale(1.08)'},
      {transform: 'translateX(0) scale(1)'},
    ], {duration: 850, easing: 'cubic-bezier(.4, 0, .2, 1)', fill: 'forwards'});
    if (!animation) { settle(frame); return; }
    animation.addEventListener('finish', () => { settle(frame); animation.cancel(); }, {once: true});
    animation.addEventListener('cancel', () => settle(frame), {once: true});
  };

  if ('IntersectionObserver' in window && !reduced.matches) {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        glide(entry.target);
      }
    }, {threshold: 0.08});
    frames.forEach(frame => observer.observe(frame));
  } else {
    frames.forEach(settle);
  }
  const stop = () => {
    for (const animation of [...running]) animation.cancel();
  };
  reduced.addEventListener('change', () => {
    if (reduced.matches) { stop(); frames.forEach(settle); }
  });
  // A restored Back/Forward page should not replay an old animation half-way through.
  window.addEventListener('pagehide', stop);
  window.addEventListener('pageshow', event => {
    if (event.persisted) frames.forEach(settle);
  });
  const header = document.querySelector('.site-header');
  if (header) {
    const mark = () => header.classList.toggle('site-header--scrolled', window.scrollY > 8);
    mark();
    window.addEventListener('scroll', mark, {passive: true});
  }
})();
