// Booking page: picking a date loads the request form in place (no page reload) and slides
// the page down to it. Without JavaScript, or if anything goes wrong, the date links work as
// normal page loads that jump to the form.
(() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const showForm = async (link) => {
    const url = new URL(link.href);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const page = new DOMParser().parseFromString(await response.text(), "text/html");

    // Swap in the server's calendar (with the date highlighted) and request form.
    for (const selector of [".calendar", "#request"]) {
      const fresh = page.querySelector(selector);
      const current = document.querySelector(selector);
      if (!fresh || !current) throw new Error(`Missing ${selector}`);
      current.replaceWith(fresh);
    }
    history.pushState({}, "", url);

    const request = document.getElementById("request");
    request.classList.add("request--entering");
    // Keyboard and screen-reader users continue from the form's heading.
    request.querySelector(".request__title")?.focus({ preventScroll: true });
    request.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "start" });
  };

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".calendar a.day__inner");
    const newTabClick = event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey;
    if (!link || event.defaultPrevented || newTabClick) return;
    event.preventDefault();
    showForm(link).catch(() => {
      window.location.href = link.href;
    });
  });

  // The page was updated without loading a new one, so Back reloads to show the matching state.
  window.addEventListener("popstate", () => window.location.reload());
})();
