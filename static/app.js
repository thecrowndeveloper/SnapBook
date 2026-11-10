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

  const pageNav = document.querySelector(".page-nav");
  if (pageNav) {
    const updatePageNav = () => {
      pageNav.classList.toggle("is-visible", window.scrollY > 240);
    };
    window.addEventListener("scroll", updatePageNav, { passive: true });
    pageNav.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
    updatePageNav();
  }
});

