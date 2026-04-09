// ---------- STATE & CONSTANTS ----------
const state = { bhk: 3, bath: 2 };
const STEPS = 4;

// ---------- PRELOADER & HERO REVEAL ----------
window.addEventListener('load', () => {
  setTimeout(() => {
    document.getElementById('preloader').classList.add('hide');
    setTimeout(() => {
      document.getElementById('preloader').style.display = 'none';
      document.getElementById('hero-content').classList.add('show');
    }, 900);
  }, 3400);
});

// ---------- PARALLAX EFFECT ----------
const parallaxLayers = [
  {
    section: document.getElementById('hero'),
    bg: document.getElementById('parallax-bg'),
    speed: 0.45,
    scale: 1,
  },
  {
    section: document.getElementById('estimator'),
    bg: document.getElementById('estimator-bg'),
    speed: 0.18,
    scale: 1.08,
  },
];

function updateParallax() {
  const scrollY = window.scrollY;

  parallaxLayers.forEach(({ section, bg, speed, scale }) => {
    if (!section || !bg) return;

    const rect = section.getBoundingClientRect();
    const sectionTop = scrollY + rect.top;
    const sectionBottom = sectionTop + section.offsetHeight;
    const isNearViewport =
      scrollY + window.innerHeight > sectionTop - 160 &&
      scrollY < sectionBottom + 160;

    if (!isNearViewport) return;

    const offset = (scrollY - sectionTop) * speed;
    bg.style.transform = `translate3d(0, ${offset}px, 0) scale(${scale})`;
  });
}

window.addEventListener('scroll', updateParallax, { passive: true });
window.addEventListener('load', updateParallax);

// ---------- TEXT INPUT GUARDS ----------
const textFieldRules = [
  {
    inputId: 'inp-location',
    errorId: 'err-location',
    emptyMessage: 'Please enter a location',
    invalidMessage: 'Numbers are not allowed in location',
  },
  {
    inputId: 'inp-city',
    errorId: 'err-city',
    emptyMessage: 'Please enter a city',
    invalidMessage: 'Numbers are not allowed in city',
  },
];

function sanitizePlaceValue(value) {
  return value.replace(/\d+/g, '');
}

function validateTextField(rule) {
  const input = document.getElementById(rule.inputId);
  const error = document.getElementById(rule.errorId);
  const value = input.value.trim();
  let message = '';

  if (!value) {
    message = rule.emptyMessage;
  } else if (/\d/.test(value)) {
    message = rule.invalidMessage;
  }

  error.textContent = message || rule.emptyMessage;
  error.classList.toggle('show', Boolean(message));
  input.classList.toggle('error', Boolean(message));
  return !message;
}

textFieldRules.forEach((rule) => {
  const input = document.getElementById(rule.inputId);
  input.addEventListener('input', () => {
    const sanitized = sanitizePlaceValue(input.value);
    if (sanitized !== input.value) input.value = sanitized;
    validateTextField(rule);
  });
});

// ---------- STEPPER CONTROLS ----------
const limits = { bhk: [1, 15], bath: [1, 20] };
function stepperChange(key, delta) {
  const [min, max] = limits[key];
  state[key] = Math.min(max, Math.max(min, state[key] + delta));
  document.getElementById('val-' + key).textContent = state[key];
}

// Attach stepper listeners
document.getElementById('bhk-dec').addEventListener('click', () => stepperChange('bhk', -1));
document.getElementById('bhk-inc').addEventListener('click', () => stepperChange('bhk', 1));
document.getElementById('bath-dec').addEventListener('click', () => stepperChange('bath', -1));
document.getElementById('bath-inc').addEventListener('click', () => stepperChange('bath', 1));

// ---------- PROGRESS BAR ----------
function updateProgress(step) {
  document.getElementById('progress-fill').style.width = (step / (STEPS - 1) * 100) + '%';
  for (let i = 0; i < STEPS; i++) {
    const dot = document.getElementById('dot-' + i);
    dot.className = 'step-dot' + (i < step ? ' done' : i === step ? ' active' : '');
    dot.textContent = i < step ? '✓' : (i + 1);
  }
}

// ---------- STEP NAVIGATION ----------
function goNext(from) {
  if (!validate(from)) return;
  if (from === 2) buildReview();
  switchStep(from, from + 1);
  updateProgress(from + 1);
}

function goBack(from) {
  switchStep(from, from - 1);
  updateProgress(from - 1);
}

function switchStep(from, to) {
  const fromEl = document.getElementById('step-' + from);
  const toEl = document.getElementById('step-' + to);
  fromEl.classList.add('exit');
  setTimeout(() => {
    fromEl.classList.remove('active', 'exit');
    toEl.style.display = 'block';
    requestAnimationFrame(() => {
      toEl.classList.add('active');
      toEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, 400);
}

// Attach navigation listeners
document.getElementById('btn-next-0').addEventListener('click', () => goNext(0));
document.getElementById('btn-back-1').addEventListener('click', () => goBack(1));
document.getElementById('btn-next-1').addEventListener('click', () => goNext(1));
document.getElementById('btn-back-2').addEventListener('click', () => goBack(2));
document.getElementById('btn-next-2').addEventListener('click', () => goNext(2));
document.getElementById('btn-back-3').addEventListener('click', () => goBack(3));

// ---------- VALIDATION ----------
function validate(step) {
  let ok = true;
  const showError = (errId, inputId, condition) => {
    const errEl = document.getElementById(errId);
    const inpEl = document.getElementById(inputId);
    const shouldShow = condition;
    errEl.classList.toggle('show', shouldShow);
    inpEl.classList.toggle('error', shouldShow);
    if (shouldShow) ok = false;
  };

  if (step === 0) {
    ok = validateTextField(textFieldRules[0]) && ok;
    ok = validateTextField(textFieldRules[1]) && ok;
  }

  if (step === 1) {
    const area = parseFloat(document.getElementById('inp-area').value);
    const floors = parseFloat(document.getElementById('inp-floors').value);
    const road = parseFloat(document.getElementById('inp-road').value);
    showError('err-area', 'inp-area', !area || area < 0.1 || area > 50);
    showError('err-floors', 'inp-floors', !floors || floors < 0.5 || floors > 10);
    showError('err-road', 'inp-road', !road || road < 4 || road > 100);
  }
  return ok;
}

// ---------- REVIEW PAGE ----------
function buildReview() {
  const fields = [
    ['Location', document.getElementById('inp-location').value.trim()],
    ['City', document.getElementById('inp-city').value.trim()],
    ['Area', document.getElementById('inp-area').value + ' Anna'],
    ['Floors', document.getElementById('inp-floors').value],
    ['Bedrooms', state.bhk],
    ['Bathrooms', state.bath],
    ['Road', document.getElementById('inp-road').value + ' ft'],
  ];
  const html = fields.map(([label, value]) => `
    <div style="background:var(--paper);border-radius:8px;padding:14px 16px">
      <div style="font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--ink-3);margin-bottom:4px">${label}</div>
      <div style="font-size:15px;color:var(--ink)">${value}</div>
    </div>
  `).join('');
  document.getElementById('review-grid').innerHTML = html;
}

// ---------- SUBMIT ESTIMATE ----------
async function submitEstimate() {
  document.getElementById('loading-overlay').classList.add('show');
  const payload = {
    location: document.getElementById('inp-location').value.trim(),
    city: document.getElementById('inp-city').value.trim(),
    area: parseFloat(document.getElementById('inp-area').value),
    bhk: state.bhk,
    bath: state.bath,
    floors: parseFloat(document.getElementById('inp-floors').value),
    road: parseFloat(document.getElementById('inp-road').value),
  };
  try {
    const res = await fetch('/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Could not submit your estimate.');
    }
    showResult(data, payload);
  } catch (e) {
    alert(e.message || 'Could not connect to the prediction server. Make sure Flask is running.');
  } finally {
    document.getElementById('loading-overlay').classList.remove('show');
  }
}
document.getElementById('btn-submit').addEventListener('click', submitEstimate);

// ---------- DISPLAY RESULT ----------
function showResult(data, payload) {
  document.getElementById('estimator').style.display = 'none';
  const resultSection = document.getElementById('result-section');
  resultSection.classList.add('show');
  resultSection.scrollIntoView({ behavior: 'smooth' });

  document.getElementById('res-location').textContent =
    (data.location || payload.location).toUpperCase() + ', ' + payload.city.toUpperCase();

  setTimeout(() => {
    const priceEl = document.getElementById('res-price');
    priceEl.textContent = data.display || '—';
    priceEl.classList.add('show');
    const rangeEl = document.getElementById('res-range');
    rangeEl.textContent = `Range: ${data.low} — ${data.high}`;
    rangeEl.classList.add('show');
  }, 300);

  document.getElementById('res-area').textContent = payload.area;
  document.getElementById('res-bhk').textContent = payload.bhk;
  document.getElementById('res-road').textContent = payload.road + ' ft';

  if (data.note) {
    document.getElementById('res-note').innerHTML =
      `<strong>${data.note}</strong> — Estimate based on recent Nepal property data. Actual prices may vary. <strong>±12% typical range.</strong>`;
  }
}

// ---------- RESTART ----------
function restart() {
  document.getElementById('result-section').classList.remove('show');
  document.getElementById('estimator').style.display = 'flex';

  // Reset step cards
  for (let i = 0; i < STEPS; i++) {
    const card = document.getElementById('step-' + i);
    card.classList.remove('active', 'exit');
    card.style.display = '';
  }
  document.getElementById('step-0').classList.add('active');
  updateProgress(0);

  // Clear inputs and errors
  ['inp-location', 'inp-city', 'inp-area', 'inp-floors', 'inp-road'].forEach(id => {
    const inp = document.getElementById(id);
    inp.value = '';
    inp.classList.remove('error');
  });
  document.querySelectorAll('.error-msg').forEach(el => el.classList.remove('show'));

  // Reset steppers
  state.bhk = 3;
  state.bath = 2;
  document.getElementById('val-bhk').textContent = 3;
  document.getElementById('val-bath').textContent = 2;

  document.getElementById('estimator').scrollIntoView({ behavior: 'smooth' });
}
document.getElementById('btn-restart').addEventListener('click', restart);
