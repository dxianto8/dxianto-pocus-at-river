// Responsive navigation; links stay visible when JavaScript is unavailable.
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

})();
