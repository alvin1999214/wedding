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

// One passive listener, one animation frame; touch scrolling remains native.
(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const scenes = [...document.querySelectorAll('.art-scene')].map(scene => ({
    scene, art: scene.querySelector('.invitation-art'),
    button: scene.querySelector('.art-hint'), manual: false, progress: 0,
  }));
  const chapters = [...document.querySelectorAll('.chapter-transition')];
  const phaseSections = ['.hero', '#details', '#schedule', '#photos', '.guest-footer']
    .map(selector => document.querySelector(`.guest-page ${selector}`));
  const floatingObjects = [...document.querySelectorAll('.edge-object')];
  let frame = 0;
  const clamp = value => Math.max(0, Math.min(1, value));
  const update = () => {
    frame = 0;
    scenes.forEach(item => {
      const rect = item.art.getBoundingClientRect();
      const viewport = window.innerHeight;
      // Unfold the envelope, then lift the paper as the guest scrolls.
      const start = Math.max(0, rect.top + window.scrollY - viewport * .62);
      const progress = reduceMotion.matches || item.manual ? 1 : clamp(
        (window.scrollY - start) / Math.min(rect.height * .85, viewport * .5)
      );
      item.progress = progress;
      const eased = progress * progress * (3 - 2 * progress);
      item.art.style.setProperty('--flap-angle', `${-Math.min(1, progress * 2) * 175}deg`);
      item.art.style.setProperty('--letter-rise', `${-eased * rect.height * .30}px`);
      item.art.style.setProperty('--seal-opacity', Math.max(0, 1 - progress * 4));
      item.button.setAttribute('aria-expanded', String(progress > .7));
      item.button.firstChild.textContent = progress > .7 ? '信箋已展開' : '輕觸展開信箋';
    });
    if (reduceMotion.matches) return;
    const viewport = window.innerHeight;
    const mobile = window.innerWidth <= 760;
    // Read geometry once per frame before writing SVG transforms.
    const phaseRects = phaseSections.map(section => section?.getBoundingClientRect());
    const chapterRects = chapters.map(chapter => chapter.getBoundingClientRect());
    floatingObjects.forEach(object => {
      const rect = phaseRects[Number(object.dataset.phase)];
      if (!rect) { object.style.opacity = '0'; return; }
      const order = Number(object.dataset.order);
      const p = (viewport - rect.top) / (viewport + rect.height);
      const entrance = clamp((p - .04 - order * .025) / .27);
      const exit = clamp((p - .72) / .28);
      // A small overshoot produces a paper-cutout pop without an endless loop.
      const t = entrance - 1;
      const pop = 1 + 2.2 * t * t * t + 1.2 * t * t;
      const distance = (1 - pop + exit) * (mobile ? 130 : 260);
      const edge = object.dataset.edge;
      const dx = edge === 'left' ? -distance : edge === 'right' ? distance : Math.sin(p * Math.PI * 2 + order) * 18;
      const dy = edge === 'top' ? -distance : edge === 'bottom' ? distance : (p - .5) * (mobile ? -45 : -100);
      const angle = (p - .5) * (object.classList.contains('object-petal') ? 150 : 30) + (order % 2 ? 12 : -12);
      object.style.opacity = String(clamp(entrance * 3) * (1 - exit) * (mobile ? .55 : .85));
      object.style.transform = `translate3d(${dx}px,${dy}px,0) rotate(${angle}deg) scale(${.75 + pop * .25})`;
    });
    chapters.forEach((chapter, index) => {
      const rect = chapterRects[index];
      if (rect.bottom < 0 || rect.top > viewport) return;
      const p = clamp((viewport - rect.top) / (viewport * .7 + rect.height));
      chapter.style.setProperty('--chapter-dash', 1 - p);
      chapter.style.setProperty('--chapter-turn', `${-65 + p * 110}deg`);
      chapter.style.setProperty('--chapter-scale', .35 + p * .65);
      chapter.style.setProperty('--chapter-opacity', clamp(p * 2));
      chapter.style.setProperty('--chapter-wash', p * .5);
      chapter.style.setProperty('--chapter-wave-y', `${(1 - p) * 70}px`);
      chapter.style.setProperty('--chapter-label-y', `${(1 - p) * 20}px`);
    });
  };
  const requestUpdate = () => { if (!frame) frame = requestAnimationFrame(update); };
  scenes.forEach(item => item.button.addEventListener('click', () => {
    item.art.classList.add('manually-opened');
    item.manual = true;
    requestUpdate();
  }));
  if (scenes.length) {
    window.addEventListener('scroll', requestUpdate, {passive:true});
    window.addEventListener('resize', requestUpdate, {passive:true});
    reduceMotion.addEventListener('change', requestUpdate);
    requestUpdate();
  }

  if (!('IntersectionObserver' in window)) return;
  const elements = document.querySelectorAll('.guest-page .venue-section > div:first-child, .guest-page .venue-illustration, .guest-page .schedule-section > div, .guest-page .timeline li, .guest-page .photos-section > .eyebrow, .guest-page .photos-section > h2, .guest-page .photos-section > .muted, .guest-page .photo-card, .guest-page .section-motif, .guest-page .guest-note, .guest-page .guest-footer');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, {threshold:0.12, rootMargin:'0px 0px -24px 0px'});
  elements.forEach(element => {
    if (reduceMotion.matches) return;
    element.classList.add('reveal-ready');
    if (element.matches('.photo-card, .timeline li')) {
      const index = [...element.parentElement.children].indexOf(element);
      element.style.setProperty('--reveal-delay', `${Math.min(index % 3, 2) * 90}ms`);
    }
    observer.observe(element);
  });
  reduceMotion.addEventListener('change', () => {
    if (reduceMotion.matches) {
      elements.forEach(element => element.classList.add('is-visible'));
      observer.disconnect();
    }
  });
  const navLinks = [...document.querySelectorAll('.guest-nav a')];
  const sectionObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      navLinks.forEach(link => {
        if (link.hash === `#${entry.target.id}`) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
    });
  }, {rootMargin:'-15% 0px -55% 0px', threshold:0});
  document.querySelectorAll('.guest-main section[id]').forEach(section => sectionObserver.observe(section));
})();
