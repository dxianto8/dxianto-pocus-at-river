// Motion for the public site.
//
// The rules that keep it tidy:
//  - Starting states live in CSS under html.motion, which is set before the first paint
//    (includes/motion_flag.html). Nothing is shown and then hidden again.
//  - Anything already on screen when the page opens is left alone, except the opening block
//    of each page, which arrives in order once the fonts are ready.
//  - Photographs only move once they have loaded, so a wipe never reveals an empty frame.
//  - When an entrance finishes, its markers are removed, so hover effects work untouched.
//  - Without JavaScript, or with reduced motion, html.motion is never set and pages are still.
(() => {
  const root = document.documentElement;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const EASE = 'cubic-bezier(.2, .7, .2, 1)';
  const running = new Set();
  const all = (selector, scope = document) => [...scope.querySelectorAll(selector)];

  // Short animations for things people do: opening a photo, picking a date.
  const play = (element, keyframes, options = {}) => {
    if (!element || reduced.matches || typeof element.animate !== 'function') return null;
    const animation = element.animate(keyframes, {duration: 600, easing: EASE, fill: 'backwards', ...options});
    running.add(animation);
    const forget = () => running.delete(animation);
    animation.addEventListener('finish', forget, {once: true});
    animation.addEventListener('cancel', forget, {once: true});
    return animation;
  };
  const rise = (element, delay = 0, distance = 16) => play(element, [
    {opacity: 0, transform: `translateY(${distance}px)`},
    {opacity: 1, transform: 'none'},
  ], {delay});
  window.pocusMotion = {play, rise};

  const stopAll = () => {
    root.classList.remove('motion');
    for (const animation of [...running]) animation.cancel();
  };
  reduced.addEventListener('change', () => { if (reduced.matches) stopAll(); });

  // The public header gains a shadow once the page has moved under it.
  const header = document.querySelector('.site-header');
  if (header) {
    const mark = () => header.classList.toggle('site-header--scrolled', window.scrollY > 8);
    mark();
    window.addEventListener('scroll', mark, {passive: true});
  }

  if (!root.classList.contains('motion')) return;
  try {

  const later = ms => new Promise(resolve => setTimeout(resolve, ms));
  const nextFrame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  // Wait for a photograph to be ready to draw, but never longer than `cap` milliseconds.
  const decoded = (img, cap = 2500) => {
    if (!img) return Promise.resolve();
    const loaded = img.complete && img.naturalWidth ? Promise.resolve() : new Promise(resolve => {
      img.addEventListener('load', resolve, {once: true});
      img.addEventListener('error', resolve, {once: true});
    });
    const ready = loaded.then(() => (img.decode ? img.decode().catch(() => {}) : undefined));
    return Promise.race([ready, later(cap)]);
  };
  // Remove the entrance markers once it has played, so CSS is back to its resting rules.
  const settle = (element, ms) => setTimeout(() => {
    element.classList.remove('is-in');
    element.removeAttribute('data-reveal');
    element.style.removeProperty('--d');
  }, ms);

  // 1. The opening block of the page: label, heading, text, buttons, one after another.
  const openers = all('.hero__text, .page-hero__text, .page-head, .auth__form, .auth-simple');
  openers.forEach(block => [...block.children].forEach((child, index) => child.style.setProperty('--i', index)));
  const fonts = document.fonts ? Promise.race([document.fonts.ready, later(600)]) : Promise.resolve();
  fonts.then(nextFrame).then(() => openers.forEach(block => {
    block.classList.add('is-in');
    // Once everything has arrived, step aside so links and buttons keep their own transitions.
    setTimeout(() => block.classList.add('is-settled'), block.children.length * 90 + 1200);
  }));

  // 2. The page's lead photograph: the home page's settles into place, side photos wipe in.
  all('.hero__media, .page-hero__media, .auth__media').forEach(frame => {
    decoded(frame.querySelector('img')).then(nextFrame).then(() => frame.classList.add('is-in'));
  });

  // 3. Further down the page, things arrive as they come into view. The signed-in
  //    workspace is used many times a visit, so it stays still.
  if (document.body.classList.contains('workspace')) return;
  const photoSelector = '.feature__media, .cat__photo, .intro__photo, .event-journal__media';
  const textSelector = [
    '.section-label', '.section-title', '.lede', '.prose', '.intro__text > p', '.cat__text',
    '.three article', '.topics > div', '.facts > div', '.visit address', '.package',
    '.faq-list details', '.menu-category', '.event-journal__media + div', '.gallery-grid figure',
    '.service-aside', '.service-layout > .panel', '.photo-credits p',
  ].join(', ');
  const exclude = '.hero__text, .page-hero__text, .page-head, .auth__form, .auth-simple, .site-header, .site-footer';
  const fold = window.innerHeight;
  const below = element => element.getBoundingClientRect().top > fold * 0.92;
  const targets = [
    ...all(photoSelector).map(element => [element, 'photo']),
    ...all(textSelector).map(element => [element, 'rise']),
  ].filter(([element]) => !element.closest(exclude) && below(element));
  // A nested target would be hidden twice; keep only the outermost one.
  const outermost = targets.filter(([element]) => !targets.some(([other]) => other !== element && other.contains(element)));
  outermost.forEach(([element, kind]) => element.setAttribute('data-reveal', kind));

  const reveal = (element, delay) => {
    element.style.setProperty('--d', `${delay}ms`);
    element.classList.add('is-in');
    settle(element, delay + (element.dataset.reveal === 'photo' ? 1700 : 1000));
  };
  const observer = new IntersectionObserver(entries => {
    // Siblings that arrive together follow one another; unrelated blocks start together.
    const counts = new Map();
    entries.filter(entry => entry.isIntersecting).forEach(entry => {
      const element = entry.target;
      observer.unobserve(element);
      const n = counts.get(element.parentElement) || 0;
      counts.set(element.parentElement, n + 1);
      const delay = Math.min(n, 4) * 90;
      if (element.dataset.reveal === 'photo') {
        decoded(element.querySelector('img')).then(() => reveal(element, delay));
      } else {
        reveal(element, delay);
      }
    });
  }, {threshold: 0.12, rootMargin: '0px 0px -8% 0px'});
  outermost.forEach(([element]) => observer.observe(element));
  } catch (error) {
    stopAll();  // Never leave anything held back because of a script error.
    throw error;
  }
})();
