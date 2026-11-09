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

