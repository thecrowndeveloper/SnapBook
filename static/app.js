document.addEventListener("DOMContentLoaded", () => {
  const menuButton = document.querySelector(".mobile-menu-toggle");
  const primaryNav = document.getElementById("primary-navigation");

  if (menuButton && primaryNav) {
    const closeMenu = () => {
      menuButton.setAttribute("aria-expanded", "false");
      menuButton.setAttribute("aria-label", "Open navigation menu");
      primaryNav.classList.remove("is-open");
    };

    menuButton.addEventListener("click", () => {
      const isOpen = menuButton.getAttribute("aria-expanded") === "true";
      menuButton.setAttribute("aria-expanded", String(!isOpen));
      menuButton.setAttribute(
        "aria-label",
        isOpen ? "Open navigation menu" : "Close navigation menu"
      );
      primaryNav.classList.toggle("is-open", !isOpen);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" &&
          menuButton.getAttribute("aria-expanded") === "true") {
        closeMenu();
        menuButton.focus();
      }
    });

    document.addEventListener("click", (event) => {
      if (!primaryNav.contains(event.target) &&
          !menuButton.contains(event.target)) closeMenu();
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 700) closeMenu();
    });
  }


  const date = document.getElementById("date");
  if (date) {
    const today = new Date();
    const local = new Date(today.getTime() - today.getTimezoneOffset() * 60000);
    date.min = local.toISOString().slice(0, 10);
  }
  const sessions = document.getElementById("sessions");
  const total = document.getElementById("total");
  if (sessions && total && window.snapbookPrice) {
    const update = () => {
      const amount = Number(sessions.value) * Number(window.snapbookPrice);
      total.textContent = "₦" + amount.toLocaleString("en-NG");
    };
    sessions.addEventListener("change", update);
    update();
  }

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const pageNav = document.querySelector(".page-nav");
  if (pageNav) {
    const updatePageNav = () => {
      pageNav.classList.toggle("is-visible", window.scrollY > 240);
    };
    window.addEventListener("scroll", updatePageNav, { passive: true });
    pageNav.addEventListener("click", () => window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" }));
    updatePageNav();
  }

  document.querySelectorAll(".showcase-track-wrap").forEach((wrap) => {
    const track = wrap.querySelector("[data-showcase-track]");
    if (!track) return;
    wrap.querySelectorAll("[data-scroll]").forEach((button) => {
      button.addEventListener("click", () => {
        const direction = button.dataset.scroll === "right" ? 1 : -1;
        track.scrollBy({ left: direction * track.clientWidth * 0.85, behavior: reduceMotion ? "auto" : "smooth" });
      });
    });
  });

  // Keep carousel arrows in sync with the actual scroll position.
  document.querySelectorAll(".showcase-track-wrap").forEach((wrap) => {
    const track = wrap.querySelector("[data-showcase-track]");
    const previous = wrap.querySelector(".showcase-prev");
    const next = wrap.querySelector(".showcase-next");
    if (!track || !previous || !next) return;
    const updateArrows = () => {
      const maxScroll = Math.max(0, track.scrollWidth - track.clientWidth);
      const atStart = track.scrollLeft <= 2;
      const atEnd = track.scrollLeft >= maxScroll - 2;
      previous.classList.toggle("is-hidden", atStart || maxScroll <= 2);
      next.classList.toggle("is-hidden", atEnd || maxScroll <= 2);
      previous.setAttribute("aria-hidden", String(atStart || maxScroll <= 2));
      next.setAttribute("aria-hidden", String(atEnd || maxScroll <= 2));
      previous.disabled = atStart || maxScroll <= 2;
      next.disabled = atEnd || maxScroll <= 2;
    };
    track.addEventListener("scroll", updateArrows, { passive: true });
    window.addEventListener("resize", updateArrows);
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(updateArrows);
      observer.observe(track);
      observer.observe(wrap);
    }
    requestAnimationFrame(updateArrows);
  });

});
