/* Upworthy readouts — SPA. All statistics come from the API (abkit);
   this file only renders. */

const $ = (sel, root = document) => root.querySelector(sel);
const main = $("#main");

const ACCENT = "#2a78d6", NAIVE = "#eb6834", MUTED = "#8b93a1",
      LINE = "#e8eaee", INK2 = "#4c5563", GOOD = "#0e9f6e";

const state = {
  meta: null,
  dataset: null,
  tests: {},          // dataset -> list
  testId: {},         // dataset -> selected test id
  view: "readout",
};

/* ---------------- helpers ---------------- */

async function api(path, params = {}) {
  const q = new URLSearchParams(params).toString();
  const res = await fetch(`/api/${path}${q ? "?" + q : ""}`);
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

const fmt = {
  pct: (x, d = 1, signed = true) =>
    x == null ? "n/a" : `${signed && x >= 0 ? "+" : ""}${(100 * x).toFixed(d)}%`,
  p: (x) => (x == null ? "n/a" : x < 0.001 ? x.toExponential(1) : x.toFixed(3)),
  int: (x) => Math.round(x).toLocaleString("en-US"),
};

function countUp(el, target, format, dur = 700) {
  const from = parseFloat(el.dataset.raw ?? "0") || 0;
  el.dataset.raw = target;
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = format(from + (target - from) * e);
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function debounce(fn, ms) {
  let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const baseLayout = (extra = {}) => ({
  font: { family: "IBM Plex Sans, sans-serif", color: INK2, size: 12.5 },
  paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
  margin: { l: 54, r: 18, t: 12, b: 44 },
  hoverlabel: { bgcolor: "#16181d", bordercolor: "#16181d",
    font: { family: "IBM Plex Mono, monospace", color: "#fbfbfa", size: 12 } },
  xaxis: { gridcolor: LINE, zerolinecolor: "#ccd1da" },
  yaxis: { gridcolor: LINE, zerolinecolor: "#ccd1da" },
  ...extra,
});
const PCONF = { displayModeBar: false, responsive: true };

/* slow-orbit a 3-D scene until the user touches it */
function autoRotate(gd) {
  let angle = Math.PI / 5, stopped = false, raf;
  const stop = () => { stopped = true; cancelAnimationFrame(raf); };
  gd.addEventListener("pointerdown", stop, { once: true });
  gd.addEventListener("wheel", stop, { once: true, passive: true });
  const spin = () => {
    if (stopped || !document.body.contains(gd)) return;
    angle += 0.0013;
    Plotly.relayout(gd, {
      "scene.camera.eye": { x: 1.9 * Math.cos(angle), y: 1.9 * Math.sin(angle), z: 0.9 },
    });
    raf = requestAnimationFrame(spin);
  };
  raf = requestAnimationFrame(spin);
}

/* ---------------- shared controls ---------------- */

function datasetSelect(onChange) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  wrap.innerHTML = `<label>dataset</label><select></select>`;
  const sel = $("select", wrap);
  for (const d of state.meta.datasets)
    sel.append(new Option(d, d, false, d === state.dataset));
  sel.onchange = () => { state.dataset = sel.value; onChange(); };
  return wrap;
}

async function loadTests(dataset) {
  if (!state.tests[dataset]) {
    state.tests[dataset] = await api("tests", { dataset });
    if (!state.testId[dataset] && state.tests[dataset].length)
      state.testId[dataset] = state.tests[dataset][0].test_id;
  }
  return state.tests[dataset];
}

function testCombo(tests, selectedId, onPick) {
  const wrap = document.createElement("div");
  wrap.className = "field combo";
  const cur = tests.find((t) => t.test_id === selectedId);
  wrap.innerHTML = `
    <label>experiment · search by headline</label>
    <input type="text" spellcheck="false" value="${esc(cur ? cur.headline : "")}">
    <div class="combo-list" role="listbox"></div>`;
  const input = $("input", wrap), list = $(".combo-list", wrap);
  const show = (q) => {
    const needle = q.trim().toLowerCase();
    const hits = (needle
      ? tests.filter((t) => t.headline.toLowerCase().includes(needle))
      : tests).slice(0, 60);
    list.innerHTML = hits.map((t) => `
      <div class="combo-item" data-id="${esc(t.test_id)}">
        <span>${esc(t.headline)}</span>
        <span class="meta">${t.n_arms} arms · ${fmt.int(t.impressions)}</span>
      </div>`).join("") || `<div class="empty">no matches</div>`;
    list.classList.add("open");
  };
  input.addEventListener("focus", () => { input.select(); show(""); });
  input.addEventListener("input", () => show(input.value));
  input.addEventListener("blur", () => setTimeout(() => list.classList.remove("open"), 160));
  list.addEventListener("mousedown", (e) => {
    const item = e.target.closest(".combo-item");
    if (!item) return;
    const t = tests.find((x) => x.test_id === item.dataset.id);
    input.value = t.headline;
    list.classList.remove("open");
    onPick(t.test_id);
  });
  return wrap;
}

/* ================= view: readout ================= */

async function viewReadout() {
  const tests = await loadTests(state.dataset);
  const view = document.createElement("div");
  view.className = "view";
  view.innerHTML = `
    <h1>Experiment readout</h1>
    <p class="lede">The verdict applies, in order: health checks → minimum sample →
      Holm-corrected comparison vs the baseline → power against corpus-realistic
      lifts. Baseline = earliest-created package (re-pickable; the archive
      designates no control).</p>
    <div class="controls"></div>
    <div id="ro-body"></div>`;
  const controls = $(".controls", view);
  controls.append(datasetSelect(render));
  controls.append(testCombo(tests, state.testId[state.dataset], (id) => {
    state.testId[state.dataset] = id; loadBody();
  }));
  const baseField = document.createElement("div");
  baseField.className = "field";
  baseField.innerHTML = `<label>baseline arm</label><select id="ro-base"></select>`;
  controls.append(baseField);
  mount(view);

  let baseline = 0;
  async function loadBody() {
    baseline = 0;
    await draw();
  }
  async function draw() {
    const body = $("#ro-body", view);
    main.classList.add("loading");
    try {
      const r = await api("readout", {
        dataset: state.dataset, test_id: state.testId[state.dataset], baseline,
      });
      main.classList.remove("loading");
      renderReadout(body, r);
      const baseSel = $("#ro-base", view);
      baseSel.innerHTML = "";
      const arms = [...r.arms].sort((a, b) => a.arm - b.arm);
      for (const a of arms)
        baseSel.append(new Option(
          `arm ${a.arm}${a.arm === 0 ? " · earliest-created" : ""}`,
          a.arm, false, a.arm === r.baseline_arm));
      baseSel.onchange = () => { baseline = +baseSel.value; draw(); };
    } catch (err) {
      main.classList.remove("loading");
      body.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    }
  }
  await loadBody();

  function renderReadout(body, r) {
    const h = r.health;
    body.innerHTML = `
      <div class="verdict ${r.verdict.kind}">
        <div class="v-body">
          <div class="v-title">${esc(r.verdict.headline)}</div>
          ${r.verdict.notes.map((n) => `<div class="v-note">${esc(n)}</div>`).join("")}
        </div>
      </div>
      <div class="stats">
        <div class="stat"><div class="k"><span class="dot ${h.srm_failed ? "fail" : "ok"}"></span>SRM · traffic split</div>
          <div class="v ${h.srm_failed ? "bad" : ""}">${h.srm_failed ? "FAIL" : "pass"}</div>
          <div class="s">chi-square p = ${fmt.p(h.srm_p)} vs an even split</div></div>
        <div class="stat"><div class="k"><span class="dot ${h.gated ? "fail" : "ok"}"></span>minimum sample</div>
          <div class="v ${h.gated ? "bad" : ""}">${h.gated ? "FAIL" : "pass"}</div>
          <div class="s">${h.gate_reasons.length ? esc(h.gate_reasons[0]) : "per-arm and total impression gates"}</div></div>
        <div class="stat"><div class="k"><span class="dot ${h.zero_click_arms.length ? "warn" : "ok"}"></span>zero-click arms</div>
          <div class="v">${h.zero_click_arms.length}</div>
          <div class="s">relative lift undefined for these arms</div></div>
        <div class="stat"><div class="k"><span class="dot ${h.achieved_power >= 0.5 ? "ok" : "warn"}"></span>achieved power</div>
          <div class="v" id="ro-power">0%</div>
          <div class="s">vs a corpus-typical lift (${fmt.pct(h.benchmark_rel_lift)})</div></div>
      </div>
      <div class="section">Lift vs baseline — naive and corrected</div>
      <p class="hint">Orange = raw estimate (what a naive readout reports). Blue =
        empirical-Bayes corrected under the corpus prior — the number to plan
        around. Noisy tests get pulled hard toward the corpus mean; that pull is
        the winner's-curse correction. Intervals are 95%.</p>
      <div class="chart"><div id="ro-lift" style="height:${110 + 74 * r.comparisons.length}px"></div></div>
      <div class="section">Arms</div>
      <p class="hint">CTR with 95% Wilson intervals. P(best) and expected loss are
        Bayesian decision aids under the corpus prior — never significance.</p>
      ${armsTable(r)}
      <div class="section">Comparisons vs baseline · Holm-corrected family</div>
      <p class="hint">Omnibus chi-square across all ${r.arms.length} arms:
        p = ${fmt.p(r.omnibus_p)}. A variant only counts as a winner on the
        Holm-adjusted value.</p>
      ${compTable(r)}`;
    countUp($("#ro-power", body), h.achieved_power, (x) => `${Math.round(100 * x)}%`);
    liftChart($("#ro-lift", body), r);
  }

  function armsTable(r) {
    return `<table><thead><tr>
      <th>arm</th><th>headline</th><th>impressions</th><th>clicks</th>
      <th>CTR</th><th>95% CI</th><th>P(best)</th><th>expected loss (pp)</th>
    </tr></thead><tbody>${r.arms.map((a) => `
      <tr>
        <td>${a.arm === r.baseline_arm ? `<span class="tag base">arm ${a.arm} · baseline</span>` : `arm ${a.arm}`}</td>
        <td class="hl">${esc(a.headline)}</td>
        <td class="num">${fmt.int(a.impressions)}</td>
        <td class="num">${fmt.int(a.clicks)}</td>
        <td class="num">${(100 * a.ctr).toFixed(2)}%</td>
        <td class="num">[${(100 * a.ctr_lo).toFixed(2)}, ${(100 * a.ctr_hi).toFixed(2)}]</td>
        <td class="num"><span class="pbar"><i style="width:${Math.round(100 * a.p_best)}%"></i></span>${Math.round(100 * a.p_best)}%</td>
        <td class="num">${(100 * a.expected_loss).toFixed(3)}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  function compTable(r) {
    return `<table><thead><tr>
      <th>variant</th><th>abs lift (pp)</th><th>abs 95% CI</th><th>raw p</th>
      <th>Holm p</th><th>significant</th>
    </tr></thead><tbody>${r.comparisons.map((c) => `
      <tr>
        <td>arm ${c.arm}</td>
        <td class="num">${c.abs_lift >= 0 ? "+" : ""}${(100 * c.abs_lift).toFixed(2)}</td>
        <td class="num">[${(100 * c.abs_lo).toFixed(2)}, ${(100 * c.abs_hi).toFixed(2)}]</td>
        <td class="num">${fmt.p(c.raw_p)}</td>
        <td class="num">${fmt.p(c.holm_p)}</td>
        <td>${c.significant ? `<span class="tag yes">yes</span>` : `<span class="tag no">no</span>`}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  function liftChart(el, r) {
    const cs = r.comparisons;
    const y = cs.map((c) => `arm ${c.arm}`);
    const mk = (xs, los, his, color, name, dy) => ({
      x: xs.map((x) => (x == null ? null : 100 * x)),
      y: y.map((_, i) => i + dy),
      error_x: {
        type: "data",
        array: his.map((h, i) => (h == null ? 0 : 100 * (h - xs[i]))),
        arrayminus: los.map((l, i) => (l == null ? 0 : 100 * (xs[i] - l))),
        color, thickness: 2, width: 5,
      },
      mode: "markers", marker: { color, size: 9 }, name,
      hovertemplate: "%{x:.1f}%<extra>" + name + "</extra>",
    });
    const traces = [
      mk(cs.map((c) => c.rel_lift), cs.map((c) => c.rel_lo), cs.map((c) => c.rel_hi),
         NAIVE, "naive", -0.16),
      mk(cs.map((c) => c.shrunk_rel), cs.map((c) => c.shrunk_lo), cs.map((c) => c.shrunk_hi),
         ACCENT, "corrected", 0.16),
    ];
    const layout = baseLayout({
      height: 110 + 74 * cs.length,
      xaxis: { title: { text: "relative lift vs baseline (%)" }, gridcolor: LINE, zeroline: true, zerolinecolor: "#ccd1da" },
      yaxis: { tickvals: y.map((_, i) => i), ticktext: y, autorange: "reversed", gridcolor: LINE },
      legend: { orientation: "h", y: 1.12 },
      shapes: [{ type: "line", x0: 0, x1: 0, y0: -0.5, y1: cs.length - 0.5,
                 line: { color: MUTED, width: 1, dash: "dot" } }],
    });
    // no data-tween here: Plotly.animate does not interpolate error bars, and a
    // half-animated interval misleads. The card-level fade covers the entrance.
    Plotly.newPlot(el, traces, layout, PCONF);
  }
}

/* ================= view: sequential ================= */

async function viewSequential() {
  const tests = await loadTests(state.dataset);
  const view = document.createElement("div");
  view.className = "view";
  view.innerHTML = `
    <h1>Sequential monitoring</h1>
    <p class="lede">The archive stores only final counts, so this is a
      <b>conditional-permutation replay</b> — the arm's actual clicks streamed in
      random order, exact given the observed totals. The band is a 95%
      <b>confidence sequence</b> (mSPRT): valid at every look simultaneously, so
      watching it daily is safe. Orange × marks: where a naive repeated z-test
      would have called a winner.</p>
    <div class="controls"></div>
    <div id="sq-body"></div>`;
  const controls = $(".controls", view);
  controls.append(datasetSelect(render));
  controls.append(testCombo(tests, state.testId[state.dataset], (id) => {
    state.testId[state.dataset] = id; drawVariants();
  }));
  const vf = document.createElement("div");
  vf.className = "field";
  vf.innerHTML = `<label>variant · vs arm 0</label><select id="sq-var"></select>`;
  controls.append(vf);
  mount(view);

  async function drawVariants() {
    const t = tests.find((x) => x.test_id === state.testId[state.dataset]);
    const sel = $("#sq-var", view);
    sel.innerHTML = "";
    for (let i = 1; i < t.n_arms; i++) sel.append(new Option(`arm ${i}`, i));
    sel.onchange = draw;
    await draw();
  }

  async function draw() {
    const body = $("#sq-body", view);
    main.classList.add("loading");
    try {
      const d = await api("sequential", {
        dataset: state.dataset, test_id: state.testId[state.dataset],
        variant: $("#sq-var", view).value || 1,
      });
      main.classList.remove("loading");
      renderSeq(body, d);
    } catch (err) {
      main.classList.remove("loading");
      body.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    }
  }
  await drawVariants();

  function renderSeq(body, d) {
    const stopped = d.first_rejection != null;
    const phantom = !stopped && d.naive_first != null;
    body.innerHTML = `
      <div class="replay-bar">
        <button class="play" id="sq-play">▶ replay the test</button>
        <div class="legend">
          <span><span class="sw" style="background:rgba(42,120,214,.25);height:10px"></span>95% confidence sequence</span>
          <span><span class="sw" style="background:${ACCENT}"></span>estimated lift</span>
          <span><span style="color:${NAIVE};font-weight:700">×</span> naive "significant!" (uncorrected)</span>
        </div>
      </div>
      <div class="chart"><div id="sq-chart" style="height:440px"></div></div>
      <div class="stats">
        <div class="stat"><div class="k"><span class="dot ${stopped ? "ok" : "warn"}"></span>mSPRT verdict</div>
          <div class="v ${stopped ? "good" : ""}">${stopped ? "significant" : "no rejection"}</div>
          <div class="s">${stopped
            ? `could stop safely at ${Math.round(100 * d.frac[d.first_rejection])}% of traffic`
            : "never crossed — cannot call a winner at any look"}</div></div>
        <div class="stat"><div class="k">always-valid p · final</div>
          <div class="v">${fmt.p(d.always_valid_p[d.always_valid_p.length - 1])}</div>
          <div class="s">valid despite continuous monitoring</div></div>
        <div class="stat"><div class="k"><span class="dot ${phantom ? "fail" : d.naive_first != null ? "warn" : "ok"}"></span>naive peeking</div>
          <div class="v ${phantom ? "bad" : ""}">${d.naive_first == null ? "never fired"
            : phantom ? "phantom win" : `${Math.round(100 * d.frac[d.naive_first])}% traffic`}</div>
          <div class="s">${d.naive_first == null ? "no look reached p < 0.05 even uncorrected"
            : phantom ? `declared a "winner" at ${Math.round(100 * d.frac[d.naive_first])}% of traffic; the honest analysis never confirms it`
            : "first uncorrected rejection — trust only the anytime-valid call"}</div></div>
      </div>
      <p class="footnote">Replays are seeded and deterministic per experiment; they
        illustrate monitoring behavior, not new evidence beyond the final counts.</p>`;

    const el = $("#sq-chart", body);
    const X = d.frac.map((f) => 100 * f);
    const up = d.theta.map((t, i) => 100 * (t + d.radius[i]));
    const lo = d.theta.map((t, i) => 100 * (t - d.radius[i]));
    const mid = d.theta.map((t) => 100 * t);
    const settle = d.radius[Math.floor(d.radius.length / 6)] * 100;
    const yLim = Math.min(Math.max(3 * settle, 0.5), 25);

    const makeTraces = (n) => {
      const xs = X.slice(0, n), naive = [];
      for (let i = 0; i < n; i++) if (d.naive_sig[i]) naive.push(i);
      return [
        { x: xs, y: up.slice(0, n), mode: "lines", line: { width: 0 },
          hoverinfo: "skip", showlegend: false },
        { x: xs, y: lo.slice(0, n), mode: "lines", line: { width: 0 },
          fill: "tonexty", fillcolor: "rgba(42,120,214,.16)",
          hoverinfo: "skip", showlegend: false },
        { x: xs, y: mid.slice(0, n), mode: "lines",
          line: { color: ACCENT, width: 2.2 }, showlegend: false,
          hovertemplate: "%{x:.0f}% traffic · lift %{y:+.3f} pp<extra></extra>" },
        { x: naive.map((i) => X[i]), y: naive.map((i) => mid[i]),
          mode: "markers", marker: { symbol: "x", size: 8, color: NAIVE },
          showlegend: false, hovertemplate: "naive p<.05 at %{x:.0f}% traffic<extra></extra>" },
      ];
    };
    const layout = baseLayout({
      height: 440,
      xaxis: { title: { text: "% of total traffic observed" }, range: [0, 102], gridcolor: LINE },
      yaxis: { title: { text: "lift · percentage points of CTR" }, range: [-yLim, yLim], gridcolor: LINE },
      shapes: [
        { type: "line", x0: 0, x1: 102, y0: 0, y1: 0, line: { color: MUTED, width: 1, dash: "dot" } },
        ...(stopped ? [{ type: "line", x0: X[d.first_rejection], x1: X[d.first_rejection],
          y0: -yLim, y1: yLim, line: { color: GOOD, width: 1.6, dash: "dash" } }] : []),
      ],
      annotations: stopped ? [{
        x: X[d.first_rejection], y: yLim, yanchor: "top", xanchor: "left",
        text: ` safe stop · ${Math.round(X[d.first_rejection])}%`, showarrow: false,
        font: { color: GOOD, size: 12, family: "IBM Plex Mono, monospace" },
      }] : [],
    });
    Plotly.newPlot(el, makeTraces(X.length), layout, PCONF);

    $("#sq-play", body).onclick = () => {
      let i = 3;
      const step = () => {
        Plotly.react(el, makeTraces(i), layout, PCONF);
        if (i++ < X.length && document.body.contains(el)) setTimeout(step, 34);
      };
      step();
    };
  }
}

/* ================= view: design ================= */

async function viewDesign() {
  const m = state.meta;
  const view = document.createElement("div");
  view.className = "view";
  view.innerHTML = `
    <h1>Design a test</h1>
    <p class="lede">Anchored to reality: a typical true lift in this corpus is
      <b>${fmt.pct(m.typical_rel_lift)} relative</b> (one sd of the fitted prior)
      around a mean CTR of <b>${(100 * m.ctr_prior_mean).toFixed(1)}%</b>.
      Plan for effects that actually occur.</p>
    <div class="controls">
      <div class="field"><label>baseline CTR %</label>
        <input id="dg-p0" type="number" min="0.1" max="50" step="0.1"
               value="${(100 * m.ctr_prior_mean).toFixed(2)}"></div>
      <div class="field"><label>alpha · two-sided</label>
        <select id="dg-alpha"><option>0.05</option><option>0.01</option><option>0.10</option></select></div>
      <div class="field"><label>target power</label>
        <select id="dg-power"><option>0.8</option><option>0.9</option><option>0.95</option></select></div>
      <div class="field"><label>lift to detect · <span id="dg-rel-lab"></span></label>
        <input id="dg-rel" type="range" min="2" max="100" step="0.5"></div>
      <div class="field"><label>impressions per arm you have</label>
        <input id="dg-n" type="number" min="100" max="10000000" step="100"
               value="${m.median_arm_impressions}"></div>
    </div>
    <div class="stats">
      <div class="stat"><div class="k">impressions per arm needed</div>
        <div class="v accent" id="dg-need">0</div>
        <div class="s" id="dg-need-sub"></div></div>
      <div class="stat"><div class="k">minimum detectable lift · your n</div>
        <div class="v" id="dg-mde">0%</div>
        <div class="s" id="dg-mde-sub"></div></div>
      <div class="stat"><div class="k">power vs a corpus-typical lift</div>
        <div class="v" id="dg-pow">0%</div>
        <div class="s">chance of detecting a ${fmt.pct(m.typical_rel_lift)} lift if truly there</div></div>
    </div>
    <div class="section">The whole trade-off, in one surface</div>
    <p class="hint">Power as a function of impressions per arm × relative lift, at
      your baseline CTR and alpha. The marker is your current plan; the ridge at
      80% is the planning bar. Drag to rotate, scroll to zoom.</p>
    <div class="chart"><div id="dg-surface" style="height:520px"></div></div>`;
  mount(view);

  const rel = $("#dg-rel", view);
  rel.value = (100 * m.typical_rel_lift).toFixed(1);
  const relLab = $("#dg-rel-lab", view);
  relLab.textContent = `${rel.value}% relative`;

  let firstSurface = true;
  async function recalc() {
    relLab.textContent = `${rel.value}% relative`;
    main.classList.add("loading");
    try {
      const d = await api("design", {
        p0: (+$("#dg-p0", view).value / 100).toString(),
        rel: (+rel.value / 100).toString(),
        n: $("#dg-n", view).value,
        alpha: $("#dg-alpha", view).value,
        power: $("#dg-power", view).value,
      });
      main.classList.remove("loading");
      countUp($("#dg-need", view), d.n_needed, fmt.int);
      const ratio = d.n_needed / m.median_arm_impressions;
      $("#dg-need-sub", view).textContent =
        `for ${Math.round(100 * +$("#dg-power", view).value)}% power vs a ${rel.value}% lift` +
        (ratio > 1 ? ` · ${ratio.toFixed(1)}× the median archived arm (${fmt.int(m.median_arm_impressions)})` : "");
      countUp($("#dg-mde", view), d.mde_rel, (x) => `${(100 * x).toFixed(1)}%`);
      $("#dg-mde-sub", view).textContent =
        `${(100 * d.mde_abs).toFixed(2)} pp absolute on your baseline`;
      const powEl = $("#dg-pow", view);
      countUp(powEl, d.achieved_power_vs_typical, (x) => `${Math.round(100 * x)}%`);
      powEl.className = "v " + (d.achieved_power_vs_typical >= 0.5 ? "good" : "warn");
      surface(d);
    } catch (err) {
      main.classList.remove("loading");
      console.error(err);
    }
  }
  const recalcD = debounce(recalc, 320);
  for (const id of ["dg-p0", "dg-alpha", "dg-power", "dg-n"])
    $("#" + id, view).addEventListener("change", recalcD);
  rel.addEventListener("input", recalcD);
  await recalc();

  function surface(d) {
    const el = $("#dg-surface", view);
    const logN = d.surface.n_grid.map((n) => Math.log10(n));
    const ticks = [500, 2000, 10000, 50000, 200000].filter(
      (t) => t >= d.surface.n_grid[0] && t <= d.surface.n_grid.at(-1));
    const data = [
      {
        type: "surface", x: logN, y: d.surface.rel_grid.map((r) => 100 * r),
        z: d.surface.power,
        colorscale: [[0, "#e8f0fb"], [0.5, "#86b6ef"], [1, "#16305e"]],
        cmin: 0, cmax: 1, opacity: 0.96,
        contours: { z: { show: true, start: 0.8, end: 0.8, size: 1,
                         color: "#eb6834", width: 3 } },
        colorbar: { title: { text: "power" }, thickness: 12, len: 0.6, tickformat: ".0%" },
        hovertemplate: "n/arm 10^%{x:.2f} · lift %{y:.0f}%<br>power %{z:.0%}<extra></extra>",
      },
      {
        type: "scatter3d", mode: "markers",
        x: [Math.log10(+$("#dg-n", view).value)], y: [+rel.value], z: [0],
        marker: { size: 6, color: NAIVE, symbol: "diamond" },
        name: "your plan", showlegend: false,
        hovertemplate: "your plan<extra></extra>",
      },
    ];
    // pin the plan marker onto the surface at the nearest grid point
    const gi = nearest(logN, Math.log10(+$("#dg-n", view).value));
    const gj = nearest(d.surface.rel_grid.map((r) => 100 * r), +rel.value);
    data[1].z = [d.surface.power[gj][gi]];
    const layout = baseLayout({
      height: 520, margin: { l: 0, r: 0, t: 0, b: 0 },
      scene: {
        xaxis: { title: "impressions / arm", tickvals: ticks.map((t) => Math.log10(t)),
                 ticktext: ticks.map((t) => t.toLocaleString()), gridcolor: LINE },
        yaxis: { title: "relative lift %", gridcolor: LINE },
        zaxis: { title: "power", range: [0, 1], tickformat: ".0%", gridcolor: LINE },
        camera: { eye: { x: 1.7, y: -1.5, z: 0.7 } },
      },
    });
    if (firstSurface) {
      Plotly.newPlot(el, data, layout, PCONF).then(() => autoRotate(el));
      firstSurface = false;
    } else {
      Plotly.react(el, data, layout, PCONF);
    }
  }
  function nearest(arr, x) {
    let best = 0;
    arr.forEach((v, i) => { if (Math.abs(v - x) < Math.abs(arr[best] - x)) best = i; });
    return best;
  }
}

/* ================= view: corpus ================= */

async function viewCorpus() {
  const view = document.createElement("div");
  view.className = "view";
  view.innerHTML = `
    <h1>Corpus explorer</h1>
    <p class="lede">The meta-analysis, interactive. Win counts exclude SRM-failing
      tests and apply within-test Holm + corpus-level BH correction.</p>
    <div class="controls"></div>
    <div id="cx-body"></div>`;
  $(".controls", view).append(datasetSelect(render));
  mount(view);

  const body = $("#cx-body", view);
  main.classList.add("loading");
  let d;
  try {
    d = await api("corpus", { dataset: state.dataset });
  } catch (err) {
    main.classList.remove("loading");
    body.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    return;
  }
  main.classList.remove("loading");
  const s = d.summary, wc = s.winners_curse ?? {}, fdr = s.fdr ?? {},
        pw = s.power ?? {}, srm = s.srm ?? {}, ua = s.upworthy_audit ?? {};

  body.innerHTML = `
    <div class="stats">
      <div class="stat"><div class="k">median winner exaggeration</div>
        <div class="v accent" id="cx-ex">×1.00</div>
        <div class="s">naive winning-arm lift ÷ corrected lift</div></div>
      <div class="stat"><div class="k">naive wins that evaporate</div>
        <div class="v" id="cx-ev">0%</div>
        <div class="s">fail Holm + BH correction</div></div>
      <div class="stat"><div class="k">tests with ≥80% power</div>
        <div class="v" id="cx-pw">0%</div>
        <div class="s">vs a corpus-typical true lift</div></div>
      <div class="stat"><div class="k"><span class="dot fail"></span>SRM failures</div>
        <div class="v" id="cx-srm">0%</div>
        <div class="s">excluded from every win count</div></div>
    </div>
    <div class="section">Winner's curse — every corrected winner, in 3-D</div>
    <p class="hint">Each point is an experiment with a corrected significant winner:
      naive lift × corrected lift × achieved power. The gap between a point and
      the diagonal wall is selection-bias exaggeration — watch it widen as power
      falls. Drag to rotate; hover for the headline.</p>
    <div class="chart"><div id="cx-3d" style="height:560px"></div></div>
    <div class="section">Achieved power across the corpus</div>
    <div class="chart"><div id="cx-hist" style="height:320px"></div></div>
    <div class="section">Verdicts, and Upworthy's own calls</div>
    <p class="hint">${ua.n_declared ? `Upworthy's tooling declared a winner in
      ${fmt.int(ua.n_declared)} tests (${Math.round(100 * ua.frac_of_tests)}%).
      Re-analyzed: <b>${Math.round(100 * ua.frac_confirmed_by_corrected_analysis)}%
      confirmed</b>; ${Math.round(100 * ua.frac_underpowered_verdict)}% came from
      underpowered tests; ${Math.round(100 * ua.frac_srm_failed)}% from tests
      failing SRM.` : ""}</p>
    <div class="chart"><div id="cx-verdicts" style="height:280px"></div></div>`;

  if (wc.median_exaggeration_ratio)
    countUp($("#cx-ex", body), wc.median_exaggeration_ratio, (x) => `×${x.toFixed(2)}`, 900);
  if (fdr.frac_naive_wins_evaporating != null)
    countUp($("#cx-ev", body), fdr.frac_naive_wins_evaporating, (x) => `${Math.round(100 * x)}%`, 900);
  if (pw.frac_tests_power_ge_80 != null)
    countUp($("#cx-pw", body), pw.frac_tests_power_ge_80, (x) => `${(100 * x).toFixed(1)}%`, 900);
  if (srm.rate != null)
    countUp($("#cx-srm", body), srm.rate, (x) => `${(100 * x).toFixed(1)}%`, 900);

  // ---- 3-D winner's curse ----
  const w = d.winners;
  if (w.naive.length) {
    const el3 = $("#cx-3d", body);
    const lim = Math.ceil((percentile(w.naive, 0.95) * 100) / 25) * 25;
    Plotly.newPlot(el3, [
      {
        type: "scatter3d", mode: "markers",
        x: w.naive.map((v) => Math.min(100 * v, lim)),
        y: w.shrunk.map((v) => Math.min(100 * v, lim)),
        z: w.power,
        text: w.headline,
        marker: { size: 3.4, color: w.power, colorscale: [[0, "#9ec5f4"], [1, "#16305e"]],
                  cmin: 0, cmax: 1, opacity: 0.8 },
        hovertemplate: "naive %{x:.0f}% → corrected %{y:.0f}%<br>power %{z:.0%}" +
                       "<br>%{text}<extra></extra>",
      },
      { // the "no exaggeration" wall: the vertical plane through naive == corrected
        type: "surface",
        x: [[0, lim], [0, lim]], y: [[0, lim], [0, lim]], z: [[0, 0], [1, 1]],
        surfacecolor: [[0, 0], [0, 0]],
        colorscale: [[0, "rgba(139,147,161,.15)"], [1, "rgba(139,147,161,.15)"]],
        showscale: false, hoverinfo: "skip",
      },
    ], baseLayout({
      height: 560, margin: { l: 0, r: 0, t: 0, b: 0 },
      scene: {
        xaxis: { title: "naive lift %", range: [0, lim], gridcolor: LINE },
        yaxis: { title: "corrected lift %", range: [0, lim], gridcolor: LINE },
        zaxis: { title: "achieved power", range: [0, 1], tickformat: ".0%", gridcolor: LINE },
        camera: { eye: { x: 1.75, y: -1.6, z: 0.75 } },
      },
    }), PCONF).then(() => autoRotate(el3));
  } else {
    $("#cx-3d", body).outerHTML = `<div class="empty">no corrected winners in this dataset</div>`;
  }

  // ---- power histogram ----
  Plotly.newPlot($("#cx-hist", body), [{
    type: "histogram", x: d.power_hist, nbinsx: 40,
    marker: { color: ACCENT, line: { color: "#fff", width: 0.5 } },
    hovertemplate: "power %{x:.2f} · %{y} tests<extra></extra>",
  }], baseLayout({
    height: 320,
    xaxis: { title: { text: "power to detect a corpus-typical lift" }, range: [0, 1], gridcolor: LINE },
    yaxis: { title: { text: "experiments" }, gridcolor: LINE },
    shapes: [{ type: "line", x0: 0.8, x1: 0.8, y0: 0, y1: 1, yref: "paper",
               line: { color: MUTED, width: 1.4, dash: "dash" } }],
    annotations: [{ x: 0.8, y: 1, yref: "paper", xanchor: "left", yanchor: "top",
      text: " 80% planning bar", showarrow: false,
      font: { size: 11.5, color: INK2, family: "IBM Plex Mono, monospace" } }],
  }), PCONF);

  // ---- verdicts ----
  const NAMES = {
    underpowered: "underpowered — don't conclude", keep_baseline: "keep baseline",
    invalid_srm: "invalid (SRM)", ship_variant: "ship a variant",
    insufficient_data: "insufficient data",
  };
  const entries = Object.entries(d.verdicts).sort((a, b) => a[1] - b[1]);
  Plotly.newPlot($("#cx-verdicts", body), [{
    type: "bar", orientation: "h",
    y: entries.map(([k]) => NAMES[k] ?? k), x: entries.map(([, v]) => v),
    marker: { color: entries.map(([k]) =>
      k === "ship_variant" ? GOOD : k === "invalid_srm" ? "#d03b3b" : ACCENT) },
    text: entries.map(([, v]) => fmt.int(v)), textposition: "outside",
    textfont: { family: "IBM Plex Mono, monospace", size: 11.5 },
    hovertemplate: "%{y}: %{x:,} tests<extra></extra>",
  }], baseLayout({
    height: 280, margin: { l: 210, r: 60, t: 6, b: 40 },
    xaxis: { title: { text: "experiments" }, gridcolor: LINE },
    yaxis: { gridcolor: "rgba(0,0,0,0)" },
  }), PCONF);

  function percentile(arr, q) {
    const a = [...arr].sort((x, y) => x - y);
    return a[Math.min(a.length - 1, Math.floor(q * a.length))];
  }
}

/* ================= router ================= */

const VIEWS = { readout: viewReadout, sequential: viewSequential,
                design: viewDesign, corpus: viewCorpus };

function mount(view) {
  main.replaceChildren(view);
  main.focus({ preventScroll: true });
}

async function render() {
  const name = (location.hash.replace("#/", "") || "readout");
  state.view = VIEWS[name] ? name : "readout";
  document.querySelectorAll(".rail a").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === state.view));
  main.classList.add("loading");
  try {
    if (!state.meta) {
      state.meta = await api("meta");
      state.dataset = state.dataset ?? state.meta.datasets[0];
    }
    await VIEWS[state.view]();
  } catch (err) {
    main.replaceChildren(Object.assign(document.createElement("div"),
      { className: "empty", textContent: err.message }));
  } finally {
    main.classList.remove("loading");
  }
}

window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", render);
