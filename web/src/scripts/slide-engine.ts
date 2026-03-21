/**
 * Shared slide-deck engine for EDPA presentations.
 * Renders an array of HTML slide strings into the #deck container,
 * wires up dot indicators, prev/next buttons, and keyboard navigation.
 */
export function initSlideDeck(slides: string[]): void {
  const deck = document.getElementById('deck');
  const dots = document.getElementById('dots');
  if (!deck || !dots) return;

  let cur = 0;

  slides.forEach((html, i) => {
    const el = document.createElement('div');
    el.className = 'slide' + (i === 0 ? ' active' : '');
    el.innerHTML = html;
    deck.appendChild(el);

    const dot = document.createElement('div');
    dot.className = 'dot' + (i === 0 ? ' on' : '');
    dot.onclick = () => goTo(i);
    dots.appendChild(dot);
  });

  function goTo(n: number): void {
    if (n < 0 || n >= slides.length) return;
    const allSlides = document.querySelectorAll('.slide');
    allSlides[cur].className = n > cur ? 'slide prev' : 'slide';
    cur = n;
    allSlides[cur].className = 'slide active';
    document.querySelectorAll('.dot').forEach((d, i) => {
      d.className = i === cur ? 'dot on' : 'dot';
    });
    const pgEl = document.getElementById('pgN');
    if (pgEl) pgEl.textContent = `${cur + 1}/${slides.length}`;
  }

  function go(delta: number): void {
    goTo(cur + delta);
  }

  document.getElementById('btnPrev')?.addEventListener('click', () => go(-1));
  document.getElementById('btnNext')?.addEventListener('click', () => go(1));

  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); go(1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
  });
}
