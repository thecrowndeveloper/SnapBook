document.addEventListener("DOMContentLoaded", () => {
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
});


// Floating page navigation: appears after scrolling and changes direction
// near the top of the page to offer a shortcut to the directory.
const pageNav = document.getElementById("page-nav");
if (pageNav) {
  const updatePageNav = () => {
    const nearTop = window.scrollY < 320;
    const goUp = !nearTop;
    pageNav.classList.toggle("is-visible", !nearTop);
    pageNav.textContent = goUp ? "↑" : "↓";
    pageNav.setAttribute("aria-label", goUp ? "Back to top" : "Explore the directory");
    pageNav.title = goUp ? "Back to top" : "Explore the directory";
    pageNav.dataset.direction = goUp ? "up" : "down";
  };
  pageNav.addEventListener("click", () => {
    if (pageNav.dataset.direction === "up") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      const target = document.getElementById("directory") || document.querySelector("main");
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
  window.addEventListener("scroll", updatePageNav, { passive: true });
  window.addEventListener("resize", updatePageNav);
  updatePageNav();
}
