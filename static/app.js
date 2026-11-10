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

    primaryNav.addEventListener("click", (event) => {
      if (event.target.closest("a")) closeMenu();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
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

  const pageNav = document.querySelector(".page-nav");
  if (pageNav) {
    const updatePageNav = () => {
      pageNav.classList.toggle("is-visible", window.scrollY > 240);
    };
    window.addEventListener("scroll", updatePageNav, { passive: true });
    pageNav.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    updatePageNav();
  }

  document.querySelectorAll(".showcase-track-wrap").forEach((wrap) => {
    const track = wrap.querySelector("[data-showcase-track]");
    if (!track) return;
    wrap.querySelectorAll("[data-scroll]").forEach((button) => {
      button.addEventListener("click", () => {
        const direction = button.dataset.scroll === "right" ? 1 : -1;
        track.scrollBy({ left: direction * track.clientWidth * 0.85, behavior: "smooth" });
      });
    });
  });
});

