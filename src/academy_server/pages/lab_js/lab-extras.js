// The lesson: guided steps, each with its checks, experiment card or quiz.
(function () {
  var STEP = LAB.step;
  var $ = function (id) { return document.getElementById(id); };
  var base = "/api/steps/" + encodeURIComponent(STEP), saved = "academy-guide:" + STEP;
  var guide = [], runId = null, cards = [], quiz = [], at = 0, redo = {};

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function api(path, body) {
    var opts = body === undefined ? {} : {method: "POST", headers: {"content-type": "application/json"},
                                         body: JSON.stringify(body)};
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));
        return j;
      });
    });
  }
  function html(cls, markup) {   // lesson markdown, rendered by the server with raw HTML disabled
    var d = el("div", cls);
    d.innerHTML = markup;
    return d;
  }
  // Card text: paragraphs, `code` and *emphasis*, built as DOM nodes (no HTML parsing).
  function rich(text) {
    var box = el("div", "stack");
    text.trim().split(/\n\s*\n/).forEach(function (para) {
      var p = el("p");
      p.style.margin = "0";
      para.replace(/\s*\n\s*/g, " ").split(/(`[^`]+`)/).forEach(function (part) {
        if (/^`[^`]+`$/.test(part)) { p.append(el("code", null, part.slice(1, -1))); return; }
        part.split(/(\*[^*\s][^*]*\*)/).forEach(function (bit) {
          if (/^\*[^*\s][^*]*\*$/.test(bit)) p.append(el("em", null, bit.slice(1, -1)));
          else if (bit) p.append(document.createTextNode(bit));
        });
      });
      box.append(p);
    });
    return box;
  }
  function label(option) { return typeof option === "string" ? option : option.label; }
  function shown(item, answer) {
    if (item.type === "mcq") return label(item.options[answer]);
    if (item.type === "numeric") return String(answer) + (item.unit ? " " + item.unit : "");
    return String(answer);
  }
  function verdictPill(correct) {
    return correct === true ? el("span", "pill pill-good", "Right")
         : correct === false ? el("span", "pill pill-critical", "Surprise")
         : el("span", "pill pill-plain", "Not graded");
  }
  function phase(text) { return el("p", "exp-phase", text); }
  function value(key, v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "yes" : "no";
    if (/cost_usd$/.test(key) && typeof v === "number") return "$" + v.toFixed(6);
    if (/_ms$/.test(key)) return v + " ms";
    return String(v);
  }
  function cardOf(id) { return cards.find(function (c) { return c.card.id === id; }); }

  // ----------------------------------------------------------- loading, navigation
  function load() {
    return Promise.all([api(base + "/guide"), api(base + "/experiments"), api(base + "/quiz")]).then(function (r) {
      guide = r[0].steps; runId = r[0].run_id; cards = r[1].experiments; quiz = r[2].items;
      render();
    }).catch(function (e) { $("guide-step").textContent = "Could not load the lesson: " + e.message; });
  }
  function refresh() {   // after a run: new values for the steps, new state for the cards
    return Promise.all([api(base + "/guide"), api(base + "/experiments")]).then(function (r) {
      guide = r[0].steps; runId = r[0].run_id; cards = r[1].experiments;
      render(true);
    });
  }
  function fromHash() {
    var h = location.hash.slice(1);
    if (!h) return -1;
    return guide.findIndex(function (g) { return g.id === h || g.experiment === h || (h === "quiz" && g.quiz); });
  }
  function done(g) {
    if (g.experiment) { var c = cardOf(g.experiment); return !!c && c.status === "explained"; }
    if (g.quiz) return quiz.length > 0 && quiz.every(function (q) { return q.last && q.last.correct; });
    if (g.check.length) return g.check.every(function (c) { return g.answers[c.id] && g.answers[c.id].correct; });
    return false;
  }
  function go(i) {
    at = Math.max(0, Math.min(guide.length - 1, i));
    try { localStorage.setItem(saved, guide[at].id); } catch (e) {}
    history.replaceState(null, "", "#" + guide[at].id);
    render();
    $("guide").scrollIntoView({behavior: "smooth", block: "start"});
  }

  function render(keepScroll) {
    if (!guide.length) { $("guide-step").textContent = "This step has no guided lesson yet."; return; }
    if (!keepScroll && render.first !== false) {
      render.first = false;
      var h = fromHash(), stored = null;
      try { stored = localStorage.getItem(saved); } catch (e) {}
      at = h >= 0 ? h : Math.max(0, guide.findIndex(function (g) { return g.id === stored; }));
    }
    var nav = $("guide-nav");
    nav.textContent = "";
    guide.forEach(function (g, i) {
      var b = el("button", "btn btn-sm", (i + 1) + " " + g.title);
      b.type = "button";
      if (done(g)) b.prepend(el("span", "icon icon-check"));
      if (i === at) b.setAttribute("aria-current", "step");
      b.addEventListener("click", function () { go(i); });
      nav.append(b);
    });
    var g = guide[at], box = $("guide-step");
    box.textContent = "";
    box.append(el("p", "eyebrow", "Step " + (at + 1) + " of " + guide.length), el("h2", null, g.title));
    box.lastChild.style.margin = "0";
    box.append(html("prose guide-prose", g.teach_html));
    if (g.lines.length) {
      var row = el("div", "row"), show = el("button", "btn btn-sm", "Show in the code");
      show.type = "button";
      show.addEventListener("click", function () { window.labEditor.highlight(g.lines); });
      row.append(el("span", "small secondary", "Highlighted in your code: line" + (g.lines.length > 1 ? "s " : " ") +
                    span(g.lines) + "."), show);
      box.append(row);
    }
    if (render.lit !== g.id) { window.labEditor.highlight(g.lines); render.lit = g.id; }   // only on opening a step
    if (g.do_html) {
      var call = el("div", "callout callout-accent");
      call.append(el("span", "icon icon-info"));
      var inner = el("div");
      inner.append(el("b", null, "Do this"), html("guide-do", g.do_html));
      call.append(inner);
      box.append(call);
    }
    if (g.show.length) box.append(yourRun(g));
    if (g.check.length) box.append(checks(g));
    if (g.experiment && cardOf(g.experiment)) box.append(renderCard(cardOf(g.experiment)));
    if (g.quiz) box.append(quizBlock());
    box.append(tutorBlock(g));
    var foot = el("div", "row guide-foot");
    if (at > 0) {
      var back = el("button", "btn", "Back");
      back.type = "button"; back.addEventListener("click", function () { go(at - 1); });
      foot.append(back);
    }
    foot.append(el("span", "spacer"));
    if (at < guide.length - 1) {
      var next = el("button", "btn btn-primary", "Next: " + guide[at + 1].title);
      next.type = "button"; next.addEventListener("click", function () { go(at + 1); });
      foot.append(next);
    }
    box.append(foot);
  }
  // ----------------------------------------------------------- the tutor
  // One thread per guide step. Threads, drafts and in-flight questions live here, so a re-render
  // (after a run or a check) doesn't lose them.
  var tutor = {}, tutorDraft = {}, tutorBusy = {}, tutorInfo = null;
  function tutorBlock(g) {
    var sec = el("section", "tutor stack"), head = el("div", "row"), meta = el("span", "small muted");
    head.append(el("p", "exp-phase", "Ask the tutor"), el("span", "spacer"), meta);
    var list = el("div", "stack tutor-thread"), form = el("form", "stack"), ta = el("textarea", "textarea");
    ta.rows = 2; ta.maxLength = 4000; ta.setAttribute("aria-label", "Your question for the tutor");
    ta.placeholder = "Ask why, or ask for a hint. It answers with questions and hints, from your code and your latest run.";
    ta.value = tutorDraft[g.id] || "";
    ta.addEventListener("input", function () { tutorDraft[g.id] = ta.value; });
    ta.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask(); }
    });
    var row = el("div", "row"), btn = el("button", "btn btn-primary btn-sm", "Ask"), msg = el("span", "small muted");
    btn.type = "submit";
    row.append(btn, msg);
    form.append(ta, row);
    form.addEventListener("submit", function (e) { e.preventDefault(); ask(); });
    sec.append(head, list, form);

    function busy(on) {
      btn.disabled = on || (tutorInfo && !tutorInfo.gateway);
      msg.textContent = on ? "The tutor is answering…" : "";
    }
    function draw() {
      list.textContent = "";
      (tutor[g.id] || []).forEach(function (t) { list.append(tutorTurn(t)); });
      if (tutorBusy[g.id]) list.append(el("div", "tutor-turn tutor-q", tutorBusy[g.id]));
      busy(!!tutorBusy[g.id]);
      if (tutorInfo) {
        meta.textContent = tutorInfo.model + " · effort " + tutorInfo.effort;
        meta.title = "Its rules: " + tutorInfo.rules;
        if (!tutorInfo.gateway) msg.textContent = "No gateway credentials, so the tutor can't answer.";
      }
    }
    function ask() {
      var text = ta.value.trim();
      if (!text || btn.disabled) return;
      tutorBusy[g.id] = text;
      draw();
      api(base + "/tutor/" + g.id, {text: text}).then(function (j) {
        tutor[g.id] = (tutor[g.id] || []).concat([{role: "user", text: text}, j.turn]);
        tutorDraft[g.id] = "";
        delete tutorBusy[g.id];
        if (sec.isConnected) { ta.value = ""; draw(); ta.focus(); } else if (guide[at].id === g.id) render(true);
      }).catch(function (e) {
        delete tutorBusy[g.id];
        draw();
        msg.textContent = e.message;
      });
    }
    if (tutor[g.id]) draw();
    else api(base + "/tutor/" + g.id).then(function (j) { tutorInfo = j; tutor[g.id] = j.turns; draw(); })
      .catch(function (e) { msg.textContent = "Could not load the tutor: " + e.message; });
    return sec;
  }
  function tutorTurn(t) {
    if (t.role === "user") return el("div", "tutor-turn tutor-q", t.text);
    var d = el("div", "tutor-turn tutor-a"), u = t.usage || {};
    d.append(html("prose guide-prose", t.html));
    d.append(el("div", "small muted tutor-meta",
      "$" + (t.cost_usd || 0).toFixed(4) + " · " + ((t.ms || 0) / 1000).toFixed(1) + " s · input " + (u.input_tokens || 0) +
      " · cache write " + (u.cache_creation_input_tokens || 0) + " · cache read " + (u.cache_read_input_tokens || 0) +
      " · output " + (u.output_tokens || 0)));
    var det = el("details", "tutor-request");
    det.append(el("summary", "small", "Show request"));
    det.addEventListener("toggle", function () {
      if (!det.open || det.dataset.loaded) return;
      det.dataset.loaded = "1";
      api("/api/tutor/turns/" + t.id).then(function (j) {
        det.append(el("p", "small secondary", "The exact request body this answer came from:"),
                   el("pre", "json-view", JSON.stringify(j.request, null, 2)),
                   el("p", "small secondary", "Its usage:"), el("pre", "json-view", JSON.stringify(j.usage, null, 2)));
      }).catch(function (e) { det.append(el("p", "small", e.message)); });
    });
    d.append(det);
    return d;
  }
  function span(lines) {   // [5,6,7,9] -> "5–7, 9"
    var out = [], start = lines[0], prev = lines[0];
    lines.slice(1).concat([null]).forEach(function (n) {
      if (n === prev + 1) { prev = n; return; }
      out.push(start === prev ? String(start) : start + "–" + prev);
      start = prev = n;
    });
    return out.join(", ");
  }

  // ----------------------------------------------------------- your run, checks
  function yourRun(g) {
    var box = el("div", "well stack");
    box.append(el("p", "exp-phase", "Your latest run" + (runId ? " · " + runId : "")));
    if (!runId) {
      box.append(el("p", "secondary", "No run yet. Press Run above your code, and your values appear here."));
      return box;
    }
    var t = el("table", "table facts-table"), body = el("tbody");
    g.show.forEach(function (f) {
      var tr = el("tr"), k = el("td"), v = el("td", "num");
      k.append(el("code", null, f.key), el("div", "small muted", f.label));
      v.textContent = value(f.key, f.value);
      if (v.textContent.length > 24) v.classList.add("is-long");   // e.g. several tool inputs: wrap, don't overflow
      tr.append(k, v); body.append(tr);
    });
    t.append(body); box.append(t);
    if (g.notice_html) box.append(el("p", "exp-phase", "What to notice"), html("prose guide-prose", g.notice_html));
    return box;
  }
  function checks(g) {
    var box = el("div", "stack");
    box.append(el("p", "exp-phase", "Check your understanding"));
    g.check.forEach(function (item, i) { box.append(checkItem(g, item, i)); });
    return box;
  }
  function checkItem(g, item, i) {
    var form = el("form", "predict-item stack"), name = g.id + "-" + item.id;
    form.addEventListener("submit", function (e) { e.preventDefault(); });
    form.append(el("p", "quiz-q", item.prompt));
    if (item.hint) form.append(el("p", "small muted", item.hint));
    var fs = null, input = null;
    if (item.type === "mcq") {
      fs = el("fieldset", "quiz-options");
      fs.append(el("legend", "sr-only", "Options"));
      item.options.forEach(function (o, k) {
        var lab = el("label", "quiz-option"), r = el("input");
        r.type = "radio"; r.name = name; r.value = String(k);
        lab.append(r, el("span", null, label(o)), el("span", "verdict"));
        fs.append(lab);
      });
      form.append(fs);
    } else {
      var aff = el("span", "input-affix");
      input = el("input", "input num");
      input.inputMode = "decimal"; input.style.width = "14ch"; input.setAttribute("aria-label", item.prompt);
      aff.append(input);
      if (item.unit) aff.append(el("span", "secondary small", item.unit));
      form.append(aff);
    }
    var row = el("div", "row"), btn = el("button", "btn btn-primary", "Check"), msg = el("span", "small error-text"),
        fb = el("div");
    btn.type = "submit";
    row.append(btn, msg);
    form.append(row, fb);
    function feedback(res) {
      fb.textContent = "";
      var f = el("div", "quiz-feedback " + (res.correct ? "is-correct" : "is-wrong"));
      f.append(el("div", "fb-title", res.correct ? "Right." : "Not quite. It comes back in your review until you get it."));
      if (item.answer_from && res.actual_display) f.append(el("p", "small", "Your run: " + res.actual_display));
      if (res.explanation) f.append(el("p", null, res.explanation));
      [].forEach.call(f.querySelectorAll("p"), function (p) { p.style.margin = "4px 0 0"; });
      fb.append(f);
      if (fs) fs.querySelectorAll("input").forEach(function (r) { r.checked = Number(r.value) === res.answer; });
      else input.value = String(res.answer);
      btn.textContent = "Check again";
    }
    btn.addEventListener("click", function () {
      var answer;
      if (fs) {
        var c = fs.querySelector("input:checked");
        if (!c) { msg.textContent = "Pick an answer."; return; }
        answer = Number(c.value);
      } else {
        answer = Number(input.value);
        if (input.value.trim() === "" || !isFinite(answer)) { msg.textContent = "Enter a number."; return; }
      }
      msg.textContent = ""; btn.disabled = true;
      var body = {answers: {}};
      body.answers[item.id] = answer;
      api(base + "/guide/" + g.id + "/check", body).then(function (j) {
        var res = j.results[item.id];
        g.answers[item.id] = {answer: res.answer, correct: res.correct, explanation: res.explanation,
                              correct_answer: res.actual_display};
        feedback(res);
        renderNav();
      }).catch(function (e) { msg.textContent = e.message; }).finally(function () { btn.disabled = false; });
    });
    var last = g.answers[item.id];
    if (last) feedback({correct: last.correct, answer: last.answer, explanation: last.explanation,
                        actual_display: last.correct_answer});
    return form;
  }
  function renderNav() {
    var buttons = $("guide-nav").querySelectorAll("button");
    guide.forEach(function (g, i) {
      var b = buttons[i];
      if (b && done(g) && !b.querySelector(".icon-check")) b.prepend(el("span", "icon icon-check"));
    });
  }

  // ----------------------------------------------------------- experiment cards
  function renderCard(s) {
    var c = s.card, wrap = el("div", "card card-pad exp-card stack");
    wrap.append(el("p", "eyebrow", "Experiment" + (s.attempt ? " · attempt " + s.attempt.attempt : "")),
                el("h3", null, c.title), el("p", "lede", c.question));
    var predicting = s.status === "predict" || redo[c.id];
    wrap.append(phase("1 · Predict"));
    if (predicting) {
      wrap.append(el("p", "small secondary", "Before you change anything: what do you expect? Commit your predictions, " +
                     "then the card tells you what to change and gives you a Run button."));
      wrap.append(predictForm(s));
      return wrap;
    }
    if (s.status === "committed" || s.status === "running") wrap.append(yourPredictions(s));
    else wrap.append(el("p", "small secondary", "Your " + s.attempt.predictions.length +
                        " predictions are compared with the run below."));
    wrap.append(change(c));
    if (s.status === "committed") {
      wrap.append(phase("3 · Run"));
      var row = el("div", "row"), run = el("button", "btn btn-primary", "Run for this experiment");
      run.type = "button";
      run.disabled = window.labRun.isRunning();
      run.addEventListener("click", function () { window.labRun.run(c.id); });
      row.append(run, el("span", "small secondary", "Saves your code, then runs it on " + window.labRun.model() +
                         ". This run is graded against your predictions."));
      wrap.append(row);
      if (c.tools.indexOf("count_tokens") >= 0) wrap.append(tokenTool());
      return wrap;
    }
    if (s.status === "running") {
      wrap.append(phase("3 · Run"), el("p", "secondary", "Running. The comparison appears here when the run ends."));
      return wrap;
    }
    wrap.append(phase("3 · Run"), runLine(s));
    wrap.append(phase("4 · Compare"), compare(s));
    if (c.tools.indexOf("count_tokens") >= 0) wrap.append(tokenTool());
    wrap.append(phase("5 · Explain"), explain(s));
    return wrap;
  }

  function predictForm(s) {
    var c = s.card, form = el("form", "stack");
    form.addEventListener("submit", function (e) { e.preventDefault(); });
    c.predict.forEach(function (item, i) {
      var box = el("div", "predict-item stack");
      box.append(el("p", "quiz-q", (i + 1) + ". " + item.prompt));
      if (item.hint) box.append(el("p", "small muted", item.hint));
      var name = c.id + "-" + item.id;
      if (item.type === "mcq") {
        var fs = el("fieldset", "quiz-options");
        fs.append(el("legend", "sr-only", "Options"));
        item.options.forEach(function (o, k) {
          var lab = el("label", "quiz-option"), input = el("input");
          input.type = "radio"; input.name = name; input.value = String(k);
          lab.append(input, el("span", null, label(o)), el("span", "verdict"));
          fs.append(lab);
        });
        box.append(fs);
      } else if (item.type === "numeric") {
        var aff = el("span", "input-affix"), input = el("input", "input num");
        input.name = name; input.inputMode = "decimal"; input.style.width = "12ch"; input.setAttribute("aria-label", item.prompt);
        aff.append(input);
        if (item.unit) aff.append(el("span", "secondary small", item.unit));
        box.append(aff);
      } else {
        var ta = el("textarea", "textarea");
        ta.name = name; ta.rows = 2; ta.maxLength = 2000; ta.setAttribute("aria-label", item.prompt);
        box.append(ta);
      }
      form.append(box);
    });
    var row = el("div", "row"), commit = el("button", "btn btn-primary", "Commit predictions"), msg = el("span", "small");
    commit.type = "submit";
    row.append(commit, msg);
    if (redo[c.id]) {
      var cancel = el("button", "btn btn-ghost", "Cancel the redo");
      cancel.type = "button";
      cancel.addEventListener("click", function () { delete redo[c.id]; render(true); });
      row.append(cancel);
    }
    form.append(row);
    commit.addEventListener("click", function () {
      var answers = {}, missing = [];
      c.predict.forEach(function (item) {
        var name = c.id + "-" + item.id, v = null;
        if (item.type === "mcq") {
          var checked = form.querySelector('input[name="' + name + '"]:checked');
          v = checked ? Number(checked.value) : null;
        } else {
          var f = form.elements[name];
          v = f.value.trim() === "" ? null : (item.type === "numeric" ? Number(f.value) : f.value.trim());
          if (item.type === "numeric" && v !== null && !isFinite(v)) v = null;
        }
        if (v === null) missing.push(item.id); else answers[item.id] = v;
      });
      if (missing.length) { msg.className = "small error-text"; msg.textContent = "Answer every question first."; return; }
      commit.disabled = true;
      api(base + "/experiments/" + c.id + "/predictions", {answers: answers}).then(function (state) {
        delete redo[c.id];
        cards[cards.indexOf(cardOf(c.id))] = state;
        render(true);
      }).catch(function (e) { commit.disabled = false; msg.className = "small error-text"; msg.textContent = e.message; });
    });
    return form;
  }

  function change(c) {
    var box = el("div", "stack");
    box.append(phase("2 · Change"));
    var call = el("div", "callout callout-accent");
    call.append(el("span", "icon icon-info"));
    var inner = el("div");
    inner.append(rich(c.change));
    call.append(inner);
    box.append(call);
    if (c.observe.length) {
      var ul = el("ul", "small secondary");
      ul.style.margin = "0";
      c.observe.forEach(function (o) { ul.append(el("li", null, o)); });
      box.append(el("p", "small", "Where to look after the run:"), ul);
    }
    return box;
  }

  function yourPredictions(s) {
    var c = s.card, t = el("table", "table"), head = el("tr"), body = el("tbody");
    ["Prediction", "You said"].forEach(function (h) { head.append(el("th", null, h)); });
    var thead = el("thead"); thead.append(head); t.append(thead, body);
    var answers = {};
    s.attempt.predictions.forEach(function (p) { answers[p.item_id] = p.answer; });
    c.predict.forEach(function (item) {
      var tr = el("tr");
      tr.append(el("td", null, item.prompt), el("td", null, item.id in answers ? shown(item, answers[item.id]) : "—"));
      body.append(tr);
    });
    var box = el("div", "stack");
    box.append(el("p", "small secondary", "Your predictions are committed."), t);
    if (s.earlier.length) box.append(earlier(s));
    return box;
  }

  function earlier(s) {
    var d = el("details", "disclosure"), sum = el("summary", null, "Your earlier attempts (" + s.earlier.length + ")");
    d.append(sum);
    s.earlier.forEach(function (a) {
      var ul = el("ul", "small");
      a.predictions.forEach(function (p) {
        var item = s.card.predict.find(function (i) { return i.id === p.item_id; });
        if (!item) return;
        var li = el("li", null, item.prompt + " You said: " + shown(item, p.answer) +
                    (p.actual_display ? "; the run: " + p.actual_display : "") + " ");
        li.append(verdictPill(p.correct));
        ul.append(li);
      });
      d.append(el("p", "small secondary", "Attempt " + a.attempt), ul);
    });
    return d;
  }

  function runLine(s) {
    var row = el("div", "row"), reopen = el("button", "btn btn-sm", "Show this run");
    reopen.type = "button";
    reopen.addEventListener("click", function () { window.labRun.watch(s.attempt.run_id, false); });
    row.append(el("span", "small secondary", "Graded against run " + s.attempt.run_id + "."), reopen);
    return row;
  }

  function compare(s) {
    var c = s.card, box = el("div", "stack"), t = el("table", "table"), thead = el("thead"), head = el("tr"), body = el("tbody");
    ["Prediction", "You said", "The run measured", ""].forEach(function (h) { head.append(el("th", null, h)); });
    thead.append(head); t.append(thead, body);
    var right = 0, wrong = 0, byId = {};
    s.attempt.predictions.forEach(function (p) { byId[p.item_id] = p; });
    c.predict.forEach(function (item) {
      var p = byId[item.id];
      if (!p) return;
      if (p.correct === true) right++; else if (p.correct === false) wrong++;
      var tr = el("tr"), measured = el("td");
      measured.append(el("div", null, p.actual_display || "—"));
      if (p.note) measured.append(el("div", "small muted", p.note));
      var v = el("td"); v.append(verdictPill(p.correct));
      tr.append(el("td", null, item.prompt), el("td", null, shown(item, p.answer)), measured, v);
      body.append(tr);
    });
    box.append(el("p", "secondary", right + " right, " + wrong + " surprise" + (wrong === 1 ? "" : "s") +
                  (wrong ? ": explain each one below." : ".")), t);
    var diff = el("div");
    box.append(diff);
    window.labRun.loadDiff(s.attempt.run_id, diff, true);
    if (s.earlier.length) box.append(earlier(s));
    return box;
  }

  function explain(s) {
    var c = s.card, box = el("div", "stack");
    if (s.status === "graded") {
      box.append(el("p", "secondary", "Why did the run do what it did? Write it in your own words first, " +
                    "then read the explanation."));
      var ta = el("textarea", "textarea"), row = el("div", "row"), go = el("button", "btn btn-primary", "Show the explanation"),
          msg = el("span", "small");
      ta.rows = 4; ta.maxLength = 4000; ta.setAttribute("aria-label", "Your explanation");
      go.type = "button";
      row.append(go, msg);
      box.append(ta, row);
      go.addEventListener("click", function () {
        if (!ta.value.trim()) { msg.className = "small error-text"; msg.textContent = "Write your explanation first."; return; }
        go.disabled = true;
        api(base + "/experiments/" + c.id + "/explain", {text: ta.value}).then(function (state) {
          cards[cards.indexOf(cardOf(c.id))] = state; render(true);
        }).catch(function (e) { go.disabled = false; msg.className = "small error-text"; msg.textContent = e.message; });
      });
      return box;
    }
    var mine = el("div", "well stack");
    mine.append(el("p", "small secondary", "Your explanation"), el("p", null, s.attempt.explanation));
    mine.lastChild.style.margin = "0"; mine.lastChild.style.whiteSpace = "pre-wrap";
    var theirs = el("div", "quiz-feedback is-correct stack");
    theirs.append(el("div", "fb-title", "The explanation"), rich(s.explain || ""));
    var row = el("div", "row"), again = el("button", "btn", "Redo this experiment");
    again.type = "button";
    again.addEventListener("click", function () { redo[c.id] = true; render(true); });
    row.append(again);
    box.append(mine, theirs, row);
    return box;
  }

  // In-lab tool: count tokens (free; count_tokens isn't billed).
  function tokenTool() {
    var box = el("div", "well stack"), ta = el("textarea", "textarea"), row = el("div", "row"),
        use = el("button", "btn btn-sm", "Use the last answer"), go = el("button", "btn btn-sm btn-primary", "Count tokens (free)"),
        out = el("p", "small secondary");
    box.append(el("p", "exp-phase", "Tool · count tokens"));
    ta.rows = 3; ta.setAttribute("aria-label", "Text to count");
    ta.placeholder = "Paste any text, or use the last answer.";
    use.type = go.type = "button";
    out.style.margin = "0";
    row.append(use, go);
    box.append(ta, row, out);
    use.addEventListener("click", function () {
      ta.value = window.labRun.answerText();
      out.textContent = ta.value ? ta.value.length + " characters." : "The run shown on the right has no answer text.";
    });
    go.addEventListener("click", function () {
      if (!ta.value) { out.textContent = "Nothing to count."; return; }
      go.disabled = true; out.textContent = "Counting…";
      api("/api/tools/count_tokens", {text: ta.value, model: window.labRun.model()}).then(function (j) {
        out.textContent = j.text_tokens + " tokens of text (" + ta.value.length + " characters, " +
          (ta.value.length / Math.max(j.text_tokens, 1)).toFixed(1) + " per token) on " + j.model +
          ". As a user message it is " + j.input_tokens + ": the message wrapper adds " + j.wrapper_tokens + ".";
      }).catch(function (e) { out.textContent = e.message; }).finally(function () { go.disabled = false; });
    });
    return box;
  }

  // ----------------------------------------------------------------- quiz
  function quizBlock() {
    var box = el("div", "stack-lg");
    quiz.forEach(function (q, i) { box.append(quizCard(q, i, quiz.length)); });
    return box;
  }
  function quizCard(q, i, n) {
    var form = el("form", "card card-pad quiz-card"), meta = el("div", "quiz-meta");
    form.addEventListener("submit", function (e) { e.preventDefault(); });
    meta.append(el("span", null, "Question " + (i + 1) + " of " + n));
    if (q.concepts.length) meta.append(el("span", null, "·"), el("span", null, q.concepts.join(", ")));
    form.append(meta, el("p", "quiz-q", q.prompt));
    var input = null, fs = null;
    if (q.type === "mcq") {
      fs = el("fieldset", "quiz-options");
      fs.append(el("legend", "sr-only", "Options"));
      q.options.forEach(function (o, k) {
        var lab = el("label", "quiz-option"), r = el("input");
        r.type = "radio"; r.name = "quiz-" + q.id; r.value = String(k);
        lab.append(r, el("span", null, o), el("span", "verdict pill"));
        fs.append(lab);
      });
      form.append(fs);
    } else {
      var aff = el("span", "input-affix");
      input = el("input", "input num");
      input.inputMode = "decimal"; input.style.width = "14ch"; input.setAttribute("aria-label", "Your answer");
      aff.append(input);
      if (q.unit) aff.append(el("span", "secondary small", q.unit));
      form.append(aff);
    }
    var row = el("div", "row"), check = el("button", "btn btn-primary", "Check"), msg = el("span", "small error-text");
    check.type = "submit";
    row.append(check, msg);
    row.style.marginTop = "var(--sp-3)";
    var feedback = el("div");
    form.append(row, feedback);

    function show(result, answer) {
      feedback.textContent = "";
      var fb = el("div", "quiz-feedback " + (result.correct ? "is-correct" : "is-wrong"));
      fb.style.marginTop = "var(--sp-3)";
      fb.append(el("div", "fb-title", result.correct ? "Right." : "Not quite. Saved to your review list."),
                document.createTextNode(result.explanation || ""));
      feedback.append(fb);
      if (fs) {
        var right = [].concat(result.correct_answer);
        fs.querySelectorAll(".quiz-option").forEach(function (lab, k) {
          var v = lab.querySelector(".verdict");
          lab.classList.toggle("is-correct", right.indexOf(k) >= 0);
          lab.classList.toggle("is-wrong", k === answer && right.indexOf(k) < 0);
          v.className = "verdict pill " + (right.indexOf(k) >= 0 ? "pill-good" : "pill-critical");
          v.textContent = right.indexOf(k) >= 0 ? "Correct" : (k === answer ? "Your answer" : "");
          lab.querySelector("input").checked = k === answer;
        });
      } else {
        input.value = String(answer);
        if (!result.correct) fb.append(document.createTextNode(" Correct answer: " + result.correct_answer + (q.unit ? " " + q.unit : "") + "."));
      }
      check.textContent = "Check again";
    }
    check.addEventListener("click", function () {
      var answer;
      if (fs) {
        var c = fs.querySelector("input:checked");
        if (!c) { msg.textContent = "Pick an answer."; return; }
        answer = Number(c.value);
      } else {
        answer = Number(input.value);
        if (input.value.trim() === "" || !isFinite(answer)) { msg.textContent = "Enter a number."; return; }
      }
      msg.textContent = ""; check.disabled = true;
      api(base + "/quiz/" + q.id, {answer: answer}).then(function (r) {
        q.last = {answer: answer, correct: r.correct, correct_answer: r.correct_answer, explanation: r.explanation,
                  tries: ((q.last && q.last.tries) || 0) + 1};
        show(r, answer);
        renderNav();
      }).catch(function (e) { msg.textContent = e.message; }).finally(function () { check.disabled = false; });
    });
    if (q.last) show(q.last, q.last.answer);
    return form;
  }

  window.addEventListener("hashchange", function () { var i = fromHash(); if (i >= 0 && i !== at) go(i); });
  document.addEventListener("lab:run-start", function () { refresh(); });
  document.addEventListener("lab:run-exit", function () { refresh(); });
  load();
})();
