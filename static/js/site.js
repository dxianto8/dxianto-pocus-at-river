(() => {
  document.documentElement.classList.add('js');
  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  if (menu && nav) {
    menu.hidden = false;
    nav.classList.add('site-nav--enhanced');
    const close = () => menu.setAttribute('aria-expanded', 'false');
    menu.addEventListener('click', () => menu.setAttribute('aria-expanded', String(menu.getAttribute('aria-expanded') !== 'true')));
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
