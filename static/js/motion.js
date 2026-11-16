// Motion for the whole site, built on the Web Animations API.
// Nothing is ever hidden in CSS: each animation starts from its own first keyframe, so with
// no JavaScript, an old browser, or "reduce motion" switched on, every page is simply still.
(() => {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const EASE = 'cubic-bezier(.2, .7, .2, 1)';
  const running = new Set();

  const play = (element, keyframes, options = {}) => {
    if (!element || reduced.matches || typeof element.animate !== 'function') return null;
    const animation = element.animate(keyframes, {
      duration: 600, easing: EASE, fill: 'backwards', ...options,
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

  const rise = (element, delay = 0, distance = 18) => play(element, [
    {opacity: 0, transform: `translateY(${distance}px)`},
    {opacity: 1, transform: 'none'},
  ], {delay});

  const all = selector => [...document.querySelectorAll(selector)];

  // Page load: the opening block of each page arrives in order.
  all('.hero__text > *, .page-hero__text > *, .page-head > *, .auth__form > *, .auth-simple > *')
    .forEach((element, index) => rise(element, 80 + index * 90, 22));
  all('.hero__photo, .page-hero > img, .auth__photo').forEach(photo => play(photo, [
    {clipPath: 'inset(0 0 0 100%)', transform: 'scale(1.08)'},
    {clipPath: 'inset(0 0 0 0)', transform: 'none'},
  ], {duration: 1100, easing: 'cubic-bezier(.65, 0, .2, 1)'}));

  // Workspace: the page settles from the top down.
  all('.ws-main > *, .booking > *').forEach((element, index) => {
    if (element.classList.contains('booking')) return;
    rise(element, Math.min(index, 6) * 70, 12);
  });
  all('.ws-nav a').forEach((link, index) => play(link, [
    {opacity: 0, transform: 'translateX(-10px)'},
    {opacity: 1, transform: 'none'},
  ], {delay: 60 + index * 45, duration: 420}));

  // Calendar days fall into place in a diagonal wave. Reused after the calendar is swapped.
  const calendarWave = (root = document) => {
    root.querySelectorAll('.calendar__grid tbody tr').forEach((row, rowIndex) => {
      [...row.children].forEach((cell, column) => {
        const inner = cell.querySelector('.day__inner');
        if (inner) play(inner, [
          {opacity: 0, transform: 'translateY(8px) scale(.9)'},
          {opacity: 1, transform: 'none'},
        ], {delay: 160 + (rowIndex + column) * 28, duration: 380});
      });
    });
  };
  calendarWave();

  // Bars grow to their value; numbers count up to theirs.
  all('.meter span').forEach(bar => play(bar, [{width: '0%'}, {width: bar.style.width}],
    {delay: 350, duration: 900}));
  all('.progress__step').forEach((step, index) => play(step, [
    {opacity: 0, clipPath: 'inset(0 100% 0 0)'},
    {opacity: 1, clipPath: 'inset(0 0 0 0)'},
  ], {delay: 200 + index * 160, duration: 520}));
  all('[data-count]').forEach(node => {
    const target = Number(node.textContent);
    if (reduced.matches || !Number.isFinite(target) || target < 2) return;
    const started = performance.now();
    const duration = Math.min(1100, 400 + target * 8);
    const tick = now => {
      const progress = Math.min((now - started) / duration, 1);
      node.textContent = Math.round(target * (1 - (1 - progress) ** 3));
      if (progress < 1 && !reduced.matches) requestAnimationFrame(tick);
      else node.textContent = target;
    };
    node.textContent = 0;
    requestAnimationFrame(tick);
  });
  all('.plate--xl .plate__day, .plate--lg .plate__day').forEach(day => play(day, [
    {opacity: 0, transform: 'translateY(40%)'},
    {opacity: 1, transform: 'none'},
  ], {delay: 220, duration: 700}));

  // Scrolling: sections arrive as they come into view; siblings follow one another.
  const onScroll = all(
    '.section-title, .lede, .occasion, .steps li, .facts > div, .three article, .package, ' +
    '.feature > img, .topics > div, .gallery-grid figure, .faq-list details, .date-chip, ' +
    '.split .prose, .footer-grid > div'
  ).filter(element => !element.closest('.hero__text, .page-hero__text, .page-head, .ws-head'));
  if ('IntersectionObserver' in window && !reduced.matches && onScroll.length) {
    const observer = new IntersectionObserver(entries => {
      entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
        const element = entry.target;
        observer.unobserve(element);
        if (element.matches('.feature > img')) {
          play(element, [
            {clipPath: 'inset(0 0 100% 0)', transform: 'scale(1.06)'},
            {clipPath: 'inset(0 0 0 0)', transform: 'none'},
          ], {duration: 900, easing: 'cubic-bezier(.65, 0, .2, 1)'});
        } else {
          rise(element, index * 80, 24);
        }
      });
    }, {threshold: 0.15, rootMargin: '0px 0px -40px 0px'});
    onScroll.forEach(element => observer.observe(element));
  }

  // The public header gains a shadow once the page has moved under it.
  const header = document.querySelector('.site-header');
  if (header) {
    const mark = () => header.classList.toggle('site-header--scrolled', window.scrollY > 8);
    mark();
    window.addEventListener('scroll', mark, {passive: true});
  }

  window.pocusMotion = {play, rise, calendarWave};
})();
