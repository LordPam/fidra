const revealTargets = document.querySelectorAll(
  '.hero-copy, .hero-panel, .download-card, .feature-card, .cta-card, .faq details'
);

revealTargets.forEach((el) => el.classList.add('reveal'));

const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.2 }
);

revealTargets.forEach((el) => observer.observe(el));

const downloadCards = document.querySelectorAll('.download-card');

downloadCards.forEach((card) => {
  card.addEventListener('mousemove', (event) => {
    const rect = card.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    card.style.background = `radial-gradient(circle at ${x}% 20%, rgba(74, 111, 165, 0.2), rgba(39, 42, 40, 0.95))`;
  });

  card.addEventListener('mouseleave', () => {
    card.style.background = '';
  });
});
