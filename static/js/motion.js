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
  all('.hero__photo, .page-hero img, .auth__photo').forEach(photo => play(photo, [
    {clipPath: 'inset(0 0 0 100%)', transform: 'scale(1.08)'},
    {clipPath: 'inset(0 0 0 0)', transform: 'none'},
  ], {duration: 1100, easing: 'cubic-bezier(.65, 0, .2, 1)'}));

  // The workspace stays still: it is used many times a visit, and motion on every page
  // change gets in the way. Only the checklist bar moves, because it shows a value.
  all('.meter span').forEach(bar => play(bar, [{width: '0%'}, {width: bar.style.width}],
    {delay: 150, duration: 700}));

  // Scrolling: sections arrive as they come into view; siblings follow one another.
  const onScroll = all(
    '.section-title, .occasion, .steps li, .three article, .package, .feature img, ' +
    '.gallery-grid figure, .date-chip'
  ).filter(element => !element.closest('.workspace'));
  if ('IntersectionObserver' in window && !reduced.matches && onScroll.length) {
    const observer = new IntersectionObserver(entries => {
      entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
        const element = entry.target;
        observer.unobserve(element);
        if (element.matches('.feature img')) {
          play(element, [
            {clipPath: 'inset(0 0 100% 0)', transform: 'scale(1.06)'},
            {clipPath: 'inset(0 0 0 0)', transform: 'none'},
          ], {duration: 900, easing: 'cubic-bezier(.65, 0, .2, 1)'});
        } else {
          rise(element, index * 70, 16);
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

  window.pocusMotion = {play, rise};
})();
