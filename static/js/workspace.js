// The customer workspace has its own navigation, independent of the venue website.
(() => {
  document.documentElement.classList.add('js');
  const toggle = document.querySelector('[data-workspace-menu]');
  const sidebar = document.getElementById('workspace-sidebar');
  const scrim = document.querySelector('[data-workspace-close]');
  const content = document.getElementById('workspace-content');
  if (!toggle || !sidebar || !scrim) return;
  const setOpen = open => {
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close workspace navigation' : 'Open workspace navigation');
    document.body.classList.toggle('workspace-nav-open', open);
    scrim.hidden = !open;
    if (content) content.inert = open;
  };
  toggle.hidden = false;
  toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  scrim.addEventListener('click', () => { setOpen(false); toggle.focus(); });
  sidebar.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link) return;
    const destination = new URL(link.href);
    // A new document starts with a closed drawer; keep the outgoing snapshot stationary.
    if (destination.origin !== location.origin ||
        (destination.pathname === location.pathname && destination.hash)) setOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      setOpen(false); toggle.focus();
    }
  });
  window.matchMedia('(min-width:64.01rem)').addEventListener('change', () => setOpen(false));
})();
