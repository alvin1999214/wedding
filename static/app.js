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
  let lastTime = 0;
  let visualScroll = window.scrollY;
  const objectSizes = new Map();
  const measureObjects = () => floatingObjects.forEach(object => {
    objectSizes.set(object, {width: object.clientWidth, height: object.clientHeight});
  });
  measureObjects();
  const clamp = value => Math.max(0, Math.min(1, value));
  const smooth = value => { const t = clamp(value); return t * t * (3 - 2 * t); };
  const bezier = (a, b, c, d, t) => (1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t*t*c + t**3*d;
  const update = timestamp => {
    frame = 0;
    const dt = lastTime ? Math.min(timestamp - lastTime, 64) : 16.67;
    lastTime = timestamp;
    visualScroll += (window.scrollY - visualScroll) * (1 - Math.exp(-dt / 110));
    if (reduceMotion.matches || Math.abs(window.scrollY - visualScroll) < .1) visualScroll = window.scrollY;
    let lettersMoving = false;
    scenes.forEach(item => {
      const rect = item.art.getBoundingClientRect();
      const viewport = window.innerHeight;
      // Reveal the personal letter early enough to read its salutation in view.
      const personal = item.art.classList.contains('personal-invitation');
      const start = Math.max(0, rect.top + window.scrollY - viewport * (personal ? .85 : .62));
      const target = reduceMotion.matches || item.manual ? 1 : clamp(
        (window.scrollY - start) / Math.min(personal ? 220 : rect.height * .85, viewport * (personal ? .28 : .5))
      );
      let progress = personal && !reduceMotion.matches
        ? item.progress + (target - item.progress) * (1 - Math.exp(-dt / 135)) : target;
      if (Math.abs(target - progress) < .001) progress = target;
      if (personal && progress !== target) lettersMoving = true;
      item.progress = progress;
      if (personal && progress >= .999) item.manual = true;
      const eased = smooth((progress - .4) / .6);
      item.art.classList.add('motion-ready');
      if (personal) {
        const letter = item.art.querySelector('.invitation-letter');
        const envelopeHeight = window.innerWidth <= 760 ? 210 : 280;
        const paperHeight = letter.offsetHeight;
        item.art.style.setProperty('--letter-space', `${envelopeHeight + eased * (paperHeight + 56 - envelopeHeight)}px`);
        item.art.style.setProperty('--envelope-opacity', 1 - smooth((eased - .35) / .65));
        item.art.style.setProperty('--letter-rise', `${(1 - eased) * envelopeHeight * .75}px`);
      }
      item.art.style.setProperty('--flap-angle', `${-Math.min(1, progress * 2) * 175}deg`);
      if (!personal) item.art.style.setProperty('--letter-rise', `${-eased * rect.height * .50}px`);
      item.art.style.setProperty('--letter-opacity', smooth((progress - .12) / .2));
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
      const top = rect.top + window.scrollY - visualScroll;
      const progress = (viewport - top) / (viewport + rect.height);
      const t = smooth((progress - .015 * order) / .96);
      const {width, height} = objectSizes.get(object);
      const w = window.innerWidth, h = viewport;
      const margin = Math.max(width, height);
      const reach = mobile ? .43 : .25;
      // Cubic paths describe centers in viewport coordinates, including offscreen endpoints.
      // Both control points are inside the viewport, so each illustration is fully visible mid-flight.
      const paths = {
        left: [[-margin,h*.60],[w*reach,h*.52],[w*reach,h*.28],[-margin,h*.16]],
        right: [[w+margin,h*.76],[w*(1-reach),h*.68],[w*(1-reach),h*.43],[w+margin,h*.30]],
        top: [[w*.80,-margin],[w*.76,h*.42],[w*.48,h*.42],[w*.34,-margin]],
        bottom: [[w*.20,h+margin],[w*.24,h*.58],[w*.52,h*.58],[w*.66,h+margin]],
      };
      const points = paths[object.dataset.edge];
      const x = bezier(...points.map(point => point[0]), t) - width / 2;
      const y = bezier(...points.map(point => point[1]), t) - height / 2;
      const angle = Math.sin(t * Math.PI * 2 + order * .6) * 9;
      const opacity = smooth(t / .16) * smooth((1-t) / .16);
      object.style.opacity = String(opacity * .92);
      object.style.transform = `translate3d(${x}px,${y}px,0) rotate(${angle}deg)`;
    });
    chapters.forEach((chapter, index) => {
      const rect = chapterRects[index];
      if (rect.bottom < 0 || rect.top > viewport) return;
      const top = rect.top + window.scrollY - visualScroll;
      const p = clamp((viewport - top) / (viewport * .7 + rect.height));
      chapter.style.setProperty('--chapter-dash', 1 - p);
      chapter.style.setProperty('--chapter-turn', `${-65 + p * 110}deg`);
      chapter.style.setProperty('--chapter-scale', .35 + p * .65);
      chapter.style.setProperty('--chapter-opacity', clamp(p * 2));
      chapter.style.setProperty('--chapter-wash', p * .5);
      chapter.style.setProperty('--chapter-wave-y', `${(1 - p) * 70}px`);
      chapter.style.setProperty('--chapter-label-y', `${(1 - p) * 20}px`);
    });
    if (visualScroll !== window.scrollY || lettersMoving) frame = requestAnimationFrame(update);
    else lastTime = 0;
  };
  const requestUpdate = () => { if (!frame) frame = requestAnimationFrame(update); };
  scenes.forEach(item => item.button.addEventListener('click', () => {
    item.art.classList.add('manually-opened');
    item.manual = true;
    requestUpdate();
  }));
  if (scenes.length) {
    window.addEventListener('scroll', requestUpdate, {passive:true});
    window.addEventListener('resize', () => { measureObjects(); requestUpdate(); }, {passive:true});
    if ('ResizeObserver' in window) {
      const letterObserver = new ResizeObserver(requestUpdate);
      document.querySelectorAll('.invitation-letter').forEach(letter => letterObserver.observe(letter));
    }
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

// Scroll releases particles; time advances gravity and drag until they leave the screen.
(() => {
  const pool = [...document.querySelectorAll('.falling-petal')];
  if (!pool.length) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const active = [];
  let frame = 0, previousTime = 0, lastScroll = window.scrollY;
  let distance = 0, credits = 0, lastActivity = -Infinity, nextRelease = 0;
  let viewportWidth = window.innerWidth;
  const random = (min, max) => min + Math.random() * (max - min);
  const clear = () => {
    cancelAnimationFrame(frame);
    frame = 0; previousTime = 0; distance = 0; credits = 0; nextRelease = 0;
    lastScroll = window.scrollY;
    active.splice(0).forEach(p => { p.element.style.opacity = '0'; });
  };
  const tick = now => {
    frame = 0;
    if (document.hidden || reduced.matches) { clear(); return; }
    const dt = previousTime ? Math.min((now - previousTime) / 1000, .04) : 1 / 60;
    previousTime = now;
    const scrolling = now - lastActivity < 180;
    if (!scrolling) credits = 0;
    if (scrolling && credits > 0 && now >= nextRelease) {
      release();
      credits--;
      nextRelease = now + random(240, 680);
    }
    for (let i = active.length - 1; i >= 0; i--) {
      const p = active[i];
      p.age += dt;
      // Gravity balanced by linear air drag gives a gentle terminal velocity.
      // A spring toward the release lane keeps neighboring trajectories separated.
      const wind = Math.sin(p.age * p.frequency + p.phase) * p.wind;
      p.vx += (wind - p.vx * 2.4 - (p.x - p.anchor) * 1.8) * dt;
      p.vy += (p.gravity - p.drag * p.vy) * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.angle += ((p.vx * 1.1 + Math.sin(p.age * 2 + p.phase) * 12) - p.angle) * dt * 2;
      if (p.y > window.innerHeight + p.size) {
        p.element.style.opacity = '0';
        active.splice(i, 1);
        continue;
      }
      p.element.style.opacity = String(Math.min(1, p.age * 2) * .88);
      p.element.style.transform = `translate3d(${p.x - p.size / 2}px,${p.y}px,0) rotate(${p.angle}deg) scaleX(${.86 + Math.sin(p.age * 1.7 + p.phase) * .14})`;
    }
    if (active.length || (scrolling && credits > 0)) frame = requestAnimationFrame(tick);
    else previousTime = 0;
  };
  const release = () => {
    const mobile = window.innerWidth <= 760;
    const lanes = mobile ? 5 : 9;
    const laneWidth = window.innerWidth / lanes;
    const cap = mobile ? 12 : 20;
    const available = Array.from({length: lanes}, (_,lane) => lane)
      .filter(lane => !active.some(p => p.lane === lane && p.y < 160));
    const count = Math.min(available.length, 1, cap - active.length);
    for (let i = 0; i < count; i++) {
      const lane = available.splice(Math.floor(random(0, available.length)), 1)[0];
      const unused = pool.filter(element => !active.some(p => p.element === element));
      if (!unused.length) break;
      const element = unused[Math.floor(random(0, unused.length))];
      const size = element.clientWidth;
      const anchor = (lane + .5) * laneWidth + random(-.16, .16) * laneWidth;
      active.push({element, lane, size, anchor, x: anchor, y: -size - random(4, 70),
        vx: random(-8, 8), vy: random(28, 44), age: 0, angle: 0,
        gravity: random(100, 125), drag: random(1.05, 1.3),
        wind: Math.min(48, laneWidth * .6), frequency: random(1.3, 2.2), phase: random(0, Math.PI * 2)});
    }
  };
  window.addEventListener('scroll', () => {
    const current = window.scrollY;
    const delta = Math.abs(current - lastScroll);
    lastScroll = current;
    if (document.hidden || reduced.matches || delta < .5) return;
    const now = performance.now();
    if (now - lastActivity > 180) {
      credits = 0;
      distance = 0;
      nextRelease = Math.max(nextRelease, now + random(60, 140));
    }
    lastActivity = now;
    distance += delta;
    if (distance >= 24) {
      credits = Math.min(3, credits + Math.floor(distance / 24));
      distance %= 24;
    }
    if (!frame && (credits || active.length)) frame = requestAnimationFrame(tick);
  }, {passive:true});
  // Mobile browser toolbars resize the viewport during scroll reversals.
  // Keep every live particle; only reposition horizontal anchors on a width change.
  window.addEventListener('resize', () => {
    const width = window.innerWidth;
    if (width === viewportWidth) return;
    const ratio = width / viewportWidth;
    active.forEach(p => {
      p.anchor *= ratio;
      p.x *= ratio;
    });
    viewportWidth = width;
  }, {passive:true});
  document.addEventListener('visibilitychange', () => { if (document.hidden) clear(); });
  reduced.addEventListener('change', clear);
})();
