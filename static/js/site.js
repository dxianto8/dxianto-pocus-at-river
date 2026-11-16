// Public site: the mobile menu and the gallery lightbox. Everything works without this file;
// the menu is simply always open and photos open as plain links.
(() => {
  document.documentElement.classList.add('js');

  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  if (menu && nav) {
    menu.hidden = false;
    const close = () => menu.setAttribute('aria-expanded', 'false');
    menu.addEventListener('click', () => {
      const opening = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(opening));
    });
    // Keep the outgoing layout still while a new page loads. Only local anchors close it here.
    nav.addEventListener('click', event => {
      const link = event.target.closest('a');
      if (link && new URL(link.href).pathname === location.pathname && link.hash) close();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { close(); menu.focus(); }
    });
    window.matchMedia('(min-width:84.01rem)').addEventListener('change', close);
  }

  const photos = [...document.querySelectorAll('[data-gallery]')];
  const dialog = document.querySelector('.lightbox');
  if (photos.length && dialog && typeof dialog.showModal === 'function') {
    let current = 0;
    let opener;
    let selection = 0;
    let photoTransition;
    const show = async index => {
      current = (index + photos.length) % photos.length;
      const photo = photos[current];
      const count = current + 1;
      const request = ++selection;
      const prepared = new Image();
      prepared.src = photo.href;
      dialog.setAttribute('aria-busy', 'true');
      try { await prepared.decode(); } catch {
        if (request === selection) {
          dialog.setAttribute('aria-busy', 'false');
          dialog.querySelector('#photo-caption').textContent = 'This photo could not load. Try another.';
        }
        return;
      }
      if (request !== selection) return;
      const image = dialog.querySelector('[data-gallery-image]');
      photoTransition?.cancel();
      let previous;
      if (image.naturalWidth && image.src !== prepared.src) {
        previous = document.createElement('div');
        previous.className = 'lightbox-previous';
        previous.setAttribute('aria-hidden', 'true');
        previous.style.backgroundImage = `url(${JSON.stringify(image.src)})`;
        image.before(previous);
      }
      image.src = prepared.src;
      image.alt = photo.querySelector('img').alt;
      dialog.querySelector('#photo-caption').textContent = photo.dataset.caption;
      dialog.querySelector('[data-gallery-count]').textContent = `${count} of ${photos.length}`;
      dialog.setAttribute('aria-busy', 'false');
      if (previous) {
        photoTransition = window.pocusMotion?.play(image, [{opacity: 0}, {opacity: 1}], {duration: 180});
        if (photoTransition) {
          const removePrevious = () => previous.remove();
          photoTransition.addEventListener('finish', removePrevious, {once: true});
          photoTransition.addEventListener('cancel', removePrevious, {once: true});
        } else previous.remove();
      }
    };
    photos.forEach((photo, index) => photo.addEventListener('click', event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = photo;
      show(index);
      dialog.showModal();
      document.body.classList.add('modal-open');
    }));
    dialog.querySelector('[data-gallery-close]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-gallery-prev]').addEventListener('click', () => show(current - 1));
    dialog.querySelector('[data-gallery-next]').addEventListener('click', () => show(current + 1));
    dialog.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        show(current + (event.key === 'ArrowRight' ? 1 : -1));
      }
    });
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('close', () => {
      selection += 1;
      photoTransition?.cancel();
      dialog.setAttribute('aria-busy', 'false');
      document.body.classList.remove('modal-open');
      opener?.focus({preventScroll: true});
    });
  }
})();
