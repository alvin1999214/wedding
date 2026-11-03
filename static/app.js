const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
document.querySelectorAll('.invitation-art').forEach(art => {
  art.addEventListener('pointermove', event => {
    if (reduceMotion.matches || event.pointerType === 'touch') return;
    const rect = art.getBoundingClientRect();
    art.style.transform = `rotateY(${(event.clientX - rect.left - rect.width / 2) / 24}deg) rotateX(${-(event.clientY - rect.top - rect.height / 2) / 24}deg)`;
  });
  art.addEventListener('pointerleave', () => { art.style.transform = ''; });
  const bloom = () => {
    if (reduceMotion.matches) return;
    art.classList.remove('bloom');
    requestAnimationFrame(() => requestAnimationFrame(() => art.classList.add('bloom')));
  };
  art.addEventListener('click', bloom);
  art.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); bloom(); }
  });
});
document.querySelectorAll('form[data-confirm]').forEach(form => {
  form.addEventListener('submit', event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); });
});
const search = document.querySelector('#guest-search');
search?.addEventListener('input', () => {
  let count = 0;
  document.querySelectorAll('[data-search]').forEach(row => {
    row.hidden = !row.dataset.search.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase());
    if (!row.hidden) count++;
  });
  document.querySelector('#no-results').hidden = count > 0;
});
