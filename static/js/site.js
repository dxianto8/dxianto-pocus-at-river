// Navigation, photo viewing, and guest stories progressively enhance ordinary links/content.
(() => {
  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  if (menu && nav) {
    menu.hidden = false;
    nav.classList.add('site-nav--enhanced');
    const closeMenu = () => menu.setAttribute('aria-expanded', 'false');
    menu.addEventListener('click', () => {
      menu.setAttribute('aria-expanded', String(menu.getAttribute('aria-expanded') !== 'true'));
    });
    nav.addEventListener('click', (event) => {
      if (event.target.closest('a')) closeMenu();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
        closeMenu();
        menu.focus();
      }
    });
    const wide = window.matchMedia('(min-width: 64rem)');
    wide.addEventListener('change', closeMenu);
  }

  const photos = [...document.querySelectorAll('a[data-gallery]')];
  const dialog = document.querySelector('.lightbox');
  if (photos.length && dialog && typeof dialog.showModal === 'function') {
    const image = dialog.querySelector('[data-gallery-image]');
    let active = 0;
    let opener;
    const showPhoto = (index) => {
      active = (index + photos.length) % photos.length;
      image.src = photos[active].href;
      image.alt = photos[active].querySelector('img').alt;
      dialog.querySelector('#lightbox-caption').textContent = photos[active].dataset.caption;
      dialog.querySelector('[data-gallery-count]').textContent = `${active + 1} / ${photos.length}`;
    };
    photos.forEach((photo, index) => photo.addEventListener('click', (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = photo;
      showPhoto(index);
      dialog.showModal();
      document.body.classList.add('modal-open');
    }));
    dialog.querySelector('[data-gallery-close]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-gallery-prev]').addEventListener('click', () => showPhoto(active - 1));
    dialog.querySelector('[data-gallery-next]').addEventListener('click', () => showPhoto(active + 1));
    dialog.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        showPhoto(active + (event.key === 'ArrowRight' ? 1 : -1));
      }
    });
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
      document.body.classList.remove('modal-open');
      opener?.focus({ preventScroll: true });
    });
  }

  const reviews = document.querySelector('[data-testimonials]');
  if (reviews) {
    const slides = [...reviews.querySelectorAll('[data-testimonial]')];
    const controls = reviews.querySelector('[data-testimonial-controls]');
    if (slides.length > 1) {
      let active = 0;
      const showReview = (index) => {
        active = (index + slides.length) % slides.length;
        slides.forEach((slide, i) => { slide.hidden = i !== active; });
        reviews.querySelector('[data-review-count]').textContent = `${active + 1} / ${slides.length}`;
      };
      controls.hidden = false;
      reviews.querySelector('[data-review-prev]').addEventListener('click', () => showReview(active - 1));
      reviews.querySelector('[data-review-next]').addEventListener('click', () => showReview(active + 1));
      showReview(0);
    }
  }

  const copy = document.querySelector('[data-copy-address]');
  if (copy && navigator.clipboard) {
    copy.hidden = false;
    copy.addEventListener('click', async () => {
      const status = document.querySelector('[data-copy-status]');
      try {
        await navigator.clipboard.writeText('Pocus at River, 100 S. River Street, Aurora, IL');
        status.textContent = 'Address copied.';
      } catch {
        status.textContent = 'Select and copy the address above, or use Get Directions.';
      }
    });
  }
})();
