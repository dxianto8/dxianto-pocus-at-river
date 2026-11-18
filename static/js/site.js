// Public site: navigation menus and the gallery lightbox. Everything works without this file:
// menus open on hover and focus, and photos open as plain links.
(() => {
  // Navigation groups. On a mouse they open on hover, with a short grace period so moving
  // from the label into the panel never closes it; clicks and the keyboard work everywhere.
  const header = document.querySelector('.site-header');
  const groups = [...document.querySelectorAll('.nav-group')];
  const hoverable = window.matchMedia('(hover: hover) and (min-width: 60.01rem)');
  const toggleOf = group => group.querySelector('.nav-group__toggle');
  const setOpen = (group, open) => {
    toggleOf(group).setAttribute('aria-expanded', String(open));
    if (open) groups.forEach(other => { if (other !== group) setOpen(other, false); });
    if (!open) group.openedByHover = false;
  };
  const isOpen = group => toggleOf(group).getAttribute('aria-expanded') === 'true';

  groups.forEach(group => {
    const toggle = toggleOf(group);
    let closeTimer;
    toggle.addEventListener('click', () => {
      // A click right after hover opened it should keep it open, not close it again.
      if (isOpen(group) && group.openedByHover) { group.openedByHover = false; return; }
      setOpen(group, !isOpen(group));
    });
    group.addEventListener('pointerenter', event => {
      if (event.pointerType !== 'mouse' || !hoverable.matches) return;
      clearTimeout(closeTimer);
      if (!isOpen(group)) { setOpen(group, true); group.openedByHover = true; }
    });
    group.addEventListener('pointerleave', event => {
      if (event.pointerType !== 'mouse' || !hoverable.matches) return;
      closeTimer = setTimeout(() => setOpen(group, false), 180);
    });
    group.addEventListener('focusout', event => {
      if (hoverable.matches && !group.contains(event.relatedTarget)) setOpen(group, false);
    });
    group.addEventListener('keydown', event => {
      if (event.key === 'Escape' && isOpen(group)) {
        setOpen(group, false);
        toggle.focus();
      } else if (event.key === 'ArrowDown' && event.target === toggle) {
        event.preventDefault();
        setOpen(group, true);
        group.querySelector('.nav-group__menu a')?.focus();
      }
    });
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.nav-group')) groups.forEach(group => setOpen(group, false));
  });

  // Small screens: the whole navigation folds into a panel under the header.
  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  if (menu && nav && header) {
    const openMenu = open => {
      menu.setAttribute('aria-expanded', String(open));
      header.classList.toggle('is-menu-open', open);
      document.body.classList.toggle('nav-open', open);
      if (!open) groups.forEach(group => setOpen(group, false));
    };
    menu.addEventListener('click', () => openMenu(menu.getAttribute('aria-expanded') !== 'true'));
    nav.addEventListener('click', event => { if (event.target.closest('a')) openMenu(false); });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { openMenu(false); menu.focus(); }
    });
    window.matchMedia('(min-width: 60.01rem)').addEventListener('change', () => openMenu(false));
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
      dialog.querySelector('[data-gallery-count]').textContent = `${current + 1} of ${photos.length}`;
      window.pocusMotion?.play(image, [{opacity: 0}, {opacity: 1}], {duration: 260});
    };
    photos.forEach((photo, index) => photo.addEventListener('click', event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      opener = photo;
      show(index);
      dialog.showModal();
      document.body.classList.add('modal-open');
      window.pocusMotion?.play(dialog.querySelector('.lightbox-inner'), [
        {opacity: 0, transform: 'scale(.96)'},
        {opacity: 1, transform: 'none'},
      ], {duration: 300});
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
      document.body.classList.remove('modal-open');
      opener?.focus({preventScroll: true});
    });
  }
})();
