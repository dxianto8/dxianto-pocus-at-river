(() => {
  document.documentElement.classList.add('js');

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const activeAnimations = new Set();
  const play = (element, keyframes, options = {}) => {
    if (reducedMotion.matches || typeof element.animate !== 'function') return;
    const animation = element.animate(keyframes, {
      duration: 760,
      easing: 'cubic-bezier(.2,.65,.3,1)',
      ...options,
    });
    activeAnimations.add(animation);
    const forget = () => activeAnimations.delete(animation);
    animation.addEventListener('finish', forget, {once: true});
    animation.addEventListener('cancel', forget, {once: true});
    return animation;
  };
  reducedMotion.addEventListener('change', () => {
    if (reducedMotion.matches) {
      for (const animation of activeAnimations) animation.cancel();
    }
  });

  // Entrance animations never hide content in CSS, so a missing script, unsupported
  // browser, or reduced-motion preference leaves every section readable.
  document.querySelectorAll('.hero-content > *').forEach((element, index) => {
    play(element, [
      {opacity: 0, transform: 'translateY(22px)'},
      {opacity: 1, transform: 'translateY(0)'},
    ], {duration: 1000, delay: index * 110, fill: 'backwards'});
  });

  const revealElements = document.querySelectorAll(
    '[data-reveal], .page-intro > *, .page-hero .wrap > *, ' +
    '.feature-row > img, .three-columns article, .gallery-grid figure, .package-card'
  );
  if ('IntersectionObserver' in window && !reducedMotion.matches) {
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const element = entry.target;
        play(element, [
          {opacity: 0, transform: 'translateY(26px)'},
          {opacity: 1, transform: 'translateY(0)'},
        ], {delay: Number(element.dataset.revealDelay) || 0, fill: 'backwards'});
        observer.unobserve(element);
      }
    }, {threshold: 0.12, rootMargin: '0px 0px -20px 0px'});
    revealElements.forEach(element => observer.observe(element));
  }

  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  if (menu && nav) {
    menu.hidden = false;
    nav.classList.add('site-nav--enhanced');
    const close = () => menu.setAttribute('aria-expanded', 'false');
    menu.addEventListener('click', () => {
      const opening = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(opening));
      if (opening) play(nav, [
        {opacity: 0, transform: 'translateY(-8px)'},
        {opacity: 1, transform: 'translateY(0)'},
      ], {duration: 220});
    });
    nav.addEventListener('click', event => { if (event.target.closest('a')) close(); });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { close(); menu.focus(); }
    });
    window.matchMedia('(min-width:75rem)').addEventListener('change', close);
  }
  const photos = [...document.querySelectorAll('[data-gallery]')];
  const dialog = document.querySelector('.lightbox');
  if (photos.length && dialog && typeof dialog.showModal === 'function') {
    let current = 0;
    let opener;
    const show = index => {
      current = (index + photos.length) % photos.length;
      const photo = photos[current];
      const image = dialog.querySelector('[data-gallery-image]');
      image.src = photo.href;
      image.alt = photo.querySelector('img').alt;
      dialog.querySelector('#photo-caption').textContent = photo.dataset.caption;
      dialog.querySelector('[data-gallery-count]').textContent = `${current + 1} / ${photos.length}`;
    };
    photos.forEach((photo,index) => photo.addEventListener('click', event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); opener = photo; show(index); dialog.showModal(); document.body.classList.add('modal-open');
      play(dialog.querySelector('.lightbox-inner'), [
        {opacity: 0, transform: 'scale(.98)'},
        {opacity: 1, transform: 'scale(1)'},
      ], {duration: 260});
    }));
    dialog.querySelector('[data-gallery-close]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-gallery-prev]').addEventListener('click', () => show(current - 1));
    dialog.querySelector('[data-gallery-next]').addEventListener('click', () => show(current + 1));
    dialog.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); show(current + (event.key === 'ArrowRight' ? 1 : -1)); }
    });
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('close', () => { document.body.classList.remove('modal-open'); opener?.focus({preventScroll:true}); });
  }
})();
