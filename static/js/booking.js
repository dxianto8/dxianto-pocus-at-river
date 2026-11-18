// Booking page. Picking a date and time of day (AM, PM or the whole day) updates the calendar
// and the "Your date" card in place, without a page load; "Continue to your details" then
// slides down to the request form. Without JavaScript, or if anything goes wrong, the links
// work as ordinary page loads.
(() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const behavior = () => (reducedMotion.matches ? "auto" : "smooth");

  const pick = async (link) => {
    const url = new URL(link.href);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const page = new DOMParser().parseFromString(await response.text(), "text/html");

    // Swap in the server's calendar (with the choice marked) and the matching request form.
    for (const selector of [".calendar", "#request"]) {
      const fresh = page.querySelector(selector);
      const current = document.querySelector(selector);
      if (!fresh || !current) throw new Error(`Missing ${selector}`);
      current.replaceWith(fresh);
    }
    window.pocusQuestionnaire?.();
    history.pushState({}, "", url);

    // The card answers the click: it rises into place and keyboard users continue from it.
    const card = document.querySelector(".pick");
    window.pocusMotion?.rise(card, 0, 10);
    document.querySelector(".pick__when")?.focus({ preventScroll: true });
    // On narrow screens the card sits under the month; scroll to it only if its top is out of
    // sight. Beside the month on wide screens it already shows, and the page stays put.
    const aside = document.querySelector(".calendar__aside");
    const top = aside?.getBoundingClientRect().top ?? 0;
    if (aside && (top < 0 || top > window.innerHeight * 0.5)) {
      aside.scrollIntoView({ behavior: behavior(), block: "start" });
    }
  };

  const goToForm = () => {
    const request = document.getElementById("request");
    if (!request) return;
    request.scrollIntoView({ behavior: behavior(), block: "start" });
    request.querySelector(".request__title")?.focus({ preventScroll: true });
  };

  document.addEventListener("click", (event) => {
    const newTabClick = event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey;
    if (event.defaultPrevented || newTabClick) return;
    if (event.target.closest(".pick__go")) {
      event.preventDefault();
      goToForm();
      return;
    }
    const link = event.target.closest("a[data-pick]");
    if (!link) return;
    event.preventDefault();
    pick(link).catch(() => {
      window.location.href = link.href;
    });
  });

  // Choosing a month from the list goes straight there; the Go button is for no-JavaScript.
  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-autosubmit]")) event.target.form.submit();
  });

  // The page was updated without loading a new one, so Back reloads to show the matching state.
  window.addEventListener("popstate", () => window.location.reload());
})();
