// The run: start it, stream its events, show the console and every model call. Reopen past runs.
(function () {
  var STEP = LAB.step, MODEL_NOTES = LAB.modelNotes;
  var $ = function (id) { return document.getElementById(id); };
  function showModelNote() { $("model-note").textContent = MODEL_NOTES[$("model").value] || ""; }
  $("model").addEventListener("change", showModelNote);
  showModelNote();
  var es = null, current = null, calls = {}, total = 0, done = false, live = false, running = false, lastBody = null;
  var pendingApproval = null;
  var startedOver = null;   // when this lesson was last started over: older runs stay in the menu only

  function pill(cls, text) { $("status").className = "pill " + cls; $("status").textContent = text; }
  function line(text, cls) {
    var s = document.createElement("span");
    if (cls) s.className = cls;
    s.textContent = text + "\n";
    $("console").appendChild(s);
  }
  function pre(value) {
    var p = document.createElement("pre");
    p.className = "json-view";
    p.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    return p;
  }
  function details(summary, value, open) {
    var d = document.createElement("details"), s = document.createElement("summary");
    d.className = "disclosure"; d.open = !!open; s.textContent = summary;
    d.append(s, pre(value));
    return d;
  }
  function card(n) {
    if (calls[n]) return calls[n];
    var c = document.createElement("div"), head = document.createElement("div"), title = document.createElement("b"),
        meta = document.createElement("span");
    c.className = "card card-body stack"; head.className = "row"; meta.className = "small muted";
    title.textContent = "Call " + n;
    head.append(title, meta); c.append(head); $("calls").append(c);
    calls[n] = {card: c, head: head, meta: meta};
    $("calls-count").textContent = Object.keys(calls).length + " call(s)";
    return calls[n];
  }
  function usd(x) { return x == null ? "price unknown" : "$" + x.toFixed(6); }
  function badge(c, cls, text) { var p = document.createElement("span"); p.className = "pill " + cls; p.textContent = text; c.head.append(p); }
  function setRunning(on) { running = on; $("run").disabled = on; $("stop").disabled = !on; }
  // The answer text of the last response in the run being shown (for the token counter).
  function answerText() {
    if (!lastBody) return "";
    var text = "";
    if (lastBody.events) {
      lastBody.events.forEach(function (e) {
        var d = e.data || {};
        if (d.type === "content_block_delta" && d.delta && d.delta.type === "text_delta") text += d.delta.text;
      });
      return text;
    }
    (lastBody.content || []).forEach(function (b) { if (b.type === "text") text += b.text; });
    return text;
  }

  function onEvent(ev) {
    var d = ev.data, c;
    window.labViews.event(ev);
    switch (ev.type) {
      case "run.started":
        $("console").textContent = "";
        line("$ python -X utf8 -u " + d.entry + "   (model " + d.model + ", limit " + d.timeout_s + " s)", "meta");
        if (d.fixture) line("mock " + d.fixture.name + " API started for this run on " + d.fixture.url, "meta");
        break;
      case "console.out": line(d.text); break;
      case "console.err": line(d.text, "stderr"); break;
      case "console.truncated": line("[output cut at " + d.cap_bytes + " bytes]", "meta"); break;
      case "llm.request":
        c = card(d.call);
        c.meta.textContent = d.method + " " + d.path + "  ·  t=" + ev.t_ms + " ms";
        c.card.append(details("Request body: exactly what your code sent", d.body, true),
                      details("Request headers (credentials removed)", d.headers, false));
        break;
      case "llm.response":
        c = card(d.call);
        badge(c, d.status < 400 ? "pill-good" : "pill-critical", String(d.status));
        var u = d.usage || {}, info = document.createElement("span");
        info.className = "small secondary num";
        info.textContent = d.ms + " ms · in " + (u.input_tokens ?? "?") + " · out " + (u.output_tokens ?? "?") +
          " · cache write " + (u.cache_creation_input_tokens ?? 0) + " · cache read " + (u.cache_read_input_tokens ?? 0) +
          " · " + usd(d.cost_usd);
        c.head.append(info);
        c.card.append(details(d.stream ? "Response stream: every server-sent event" : "Response body: exactly what came back", d.body, true),
                      details("Response headers (the gateway's included)", d.headers, false));
        if (d.cost_usd) { total += d.cost_usd; $("cost").textContent = "spent " + usd(total); }
        if (d.status < 400) lastBody = d.body;
        break;
      case "llm.error":
        c = card(d.call); badge(c, "pill-critical", "no response"); c.card.append(pre(d.error));
        break;
      case "approval.requested":
        pendingApproval = d.id;
        $("approval-what").textContent = d.tool + "(" + JSON.stringify(d.input) + ")";
        $("approval-note").textContent = "No answer in " + d.timeout_s + " s counts as a denial.";
        $("approval").hidden = false;
        line("paused: waiting for Approve or Deny on " + d.tool, "meta");
        break;
      case "approval.answered":
        if (pendingApproval === d.id) { pendingApproval = null; $("approval").hidden = true; }
        line("answer: " + d.outcome + " (" + d.reason + ")", "meta");
        break;
      case "run.exit": $("approval").hidden = true; finish(d); break;
    }
  }
  function answerApproval(approved) {
    if (!current || !pendingApproval) return;
    fetch("/api/runs/" + encodeURIComponent(current) + "/approvals/" + pendingApproval, {
      method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({approved: approved})
    });
  }
  $("approve").addEventListener("click", function () { answerApproval(true); });
  $("deny").addEventListener("click", function () { answerApproval(false); });
  function finish(d) {
    done = true;
    var map = {ok: ["pill-good", "ok"], error: ["pill-critical", "error"], timeout: ["pill-warning", "timeout"],
               stopped: ["pill-paused", "stopped"]};
    var m = map[d.outcome] || ["pill-plain", d.outcome];
    pill(m[0], m[1] + (d.exit_code != null ? " · exit " + d.exit_code : ""));
    if (d.error) line(d.error, "stderr");
    if (live) {
      setRunning(false);
      loadHistory();
      document.dispatchEvent(new CustomEvent("lab:run-exit", {detail: {run_id: current, outcome: d.outcome}}));
    }
  }
  function diffView(text) {
    var p = document.createElement("pre");
    p.className = "diff-view";
    text.replace(/\n$/, "").split("\n").forEach(function (l) {
      var s = document.createElement("span");
      s.className = l.startsWith("+++") || l.startsWith("---") ? "diff-file" : l.startsWith("@@") ? "diff-hunk"
                  : l.startsWith("+") ? "diff-add" : l.startsWith("-") ? "diff-del" : "diff-ctx";
      s.textContent = l;
      p.append(s);
    });
    return p;
  }
  // "Change one thing": what this run changed since the previous run of the step.
  function renderDiff(target, j, open) {
    target.textContent = "";
    var d = document.createElement("details"), s = document.createElement("summary"), body = document.createElement("div");
    d.className = "disclosure"; d.open = !!open; body.className = "stack";
    var changes = [];
    if (j.model.prev && j.model.prev !== j.model.now) changes.push("model " + j.model.prev + " → " + j.model.now);
    if (j.diff) changes.push("code");
    s.textContent = j.prev_run_id ? "Changed since the previous run: " + (changes.join(" and ") || "nothing")
                                  : "Changed since the previous run";
    d.append(s, body);
    if (j.note) { var n = document.createElement("p"); n.className = "small muted"; n.textContent = j.note; body.append(n); }
    if (j.model.prev && j.model.prev !== j.model.now) {
      var m = document.createElement("p"); m.className = "small"; m.textContent = "Model: " + j.model.prev + " → " + j.model.now;
      body.append(m);
    }
    if (j.diff) body.append(diffView(j.diff));
    else if (j.prev_run_id && !j.note) {
      var same = document.createElement("p"); same.className = "small muted";
      same.textContent = "The code is the same as in run " + j.prev_run_id + ".";
      body.append(same);
    }
    target.append(d);
  }
  function loadDiff(runId, target, open) {
    return fetch("/api/runs/" + encodeURIComponent(runId) + "/diff").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) renderDiff(target, j, open); });
  }
  function watch(id, isLive) {
    if (es) es.close();
    current = id; pendingApproval = null; $("approval").hidden = true; calls = {}; total = 0; done = false; live = !!isLive; lastBody = null;
    window.labViews.reset();
    $("calls").textContent = ""; $("calls-count").textContent = ""; $("cost").textContent = "";
    $("run-id").textContent = "run " + id;
    $("history").value = id;
    loadDiff(id, $("run-diff"), false);
    if (live) { setRunning(true); pill("pill-in_progress", "running"); }
    es = new EventSource("/api/runs/" + encodeURIComponent(id) + "/events");
    es.onmessage = function (m) { onEvent(JSON.parse(m.data)); };
    es.addEventListener("end", function () {
      es.close();
      if (!done) { pill("pill-plain", "incomplete"); if (live) setRunning(false); }
    });
  }
  // experiment: grade that card's committed predictions against this run (null: a plain run).
  function startRun(experiment) {
    if (running) return Promise.resolve();
    $("run").disabled = true;
    return window.labEditor.saveAll().then(function (saved) {       // run what you see: save first
      if (!saved) { $("run").disabled = false; return; }
      return fetch("/api/steps/" + encodeURIComponent(STEP) + "/runs", {
        method: "POST", headers: {"content-type": "application/json"},
        body: JSON.stringify({model: $("model").value, experiment: experiment || null})
      }).then(function (r) { return r.json().then(function (j) { return [r, j]; }); })
        .then(function (rj) {
          if (!rj[0].ok) { $("run").disabled = false; line("could not start: " + (rj[1].detail || rj[0].status), "stderr"); return; }
          watch(rj[1].run_id, true);
          document.dispatchEvent(new CustomEvent("lab:run-start", {detail: {run_id: rj[1].run_id}}));
        });
    });
  }
  function loadHistory() {
    return fetch("/api/steps/" + encodeURIComponent(STEP) + "/runs").then(function (r) { return r.json(); }).then(function (j) {
      startedOver = j.started_over_at;
      var sel = $("history");
      sel.textContent = "";
      var head = document.createElement("option");
      head.value = ""; head.textContent = j.runs.length ? "Reopen a run (" + j.runs.length + ")" : "No runs yet";
      head.disabled = true; sel.append(head);
      j.runs.forEach(function (r) {
        var o = document.createElement("option");
        o.value = r.run_id;
        o.textContent = r.started_at.slice(5, 16).replace("T", " ") + " · " + (r.model || "?").replace("claude-", "") +
          " · " + (r.outcome || "running") + (r.experiment_id ? " · " + r.experiment_id.toUpperCase() : "");
        sel.append(o);
      });
      sel.value = current || "";
      return j.runs;
    });
  }
  $("history").addEventListener("change", function () { if ($("history").value) watch($("history").value, false); });
  document.addEventListener("lab:show-call", function (e) {   // a timeline row: open that call's request and response
    var c = calls[e.detail];
    if (!c) return;
    c.card.querySelectorAll("details").forEach(function (d, k) { if (k % 2 === 0) d.open = true; });
    c.card.scrollIntoView({behavior: "smooth", block: "start"});
  });
  $("run").addEventListener("click", function () { startRun(null); });
  $("stop").addEventListener("click", function () {
    if (current) fetch("/api/runs/" + encodeURIComponent(current) + "/stop", {method: "POST"});
  });
  // Reopen your latest run of this step (free: it's replayed from the store, not re-run), unless
  // you started the lesson over after it.
  loadHistory().then(function (runs) {
    if (runs.length && (!startedOver || runs[0].started_at > startedOver)) watch(runs[0].run_id, false);
  });
  window.labRun = {run: startRun, watch: watch, answerText: answerText, loadDiff: loadDiff,
                   isRunning: function () { return running; }, model: function () { return $("model").value; }};
})();
