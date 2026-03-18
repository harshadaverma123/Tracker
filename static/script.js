// Deadline alert - highlight deadlines within 3 days
document.addEventListener('DOMContentLoaded', function () {
  const deadlineEls = document.querySelectorAll('.deadline[data-date]');

  deadlineEls.forEach(el => {
    const dateStr = el.getAttribute('data-date');
    if (!dateStr) return;

    const deadline = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const diff = Math.ceil((deadline - today) / (1000 * 60 * 60 * 24));

    if (diff < 0) {
      el.textContent = '❌ Deadline passed';
      el.style.color = '#94a3b8';
    } else if (diff === 0) {
      el.textContent = '🔴 Deadline TODAY!';
      el.classList.add('soon');
    } else if (diff <= 3) {
      el.textContent = `⚠️ ${diff} day(s) left!`;
      el.classList.add('soon');
    }
  });
});
