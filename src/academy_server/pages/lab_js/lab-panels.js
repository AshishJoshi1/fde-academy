// Views of a run that makes several calls, for the steps that turn them on (panels: in step.yaml):
//   timeline  every model call, every tool your code ran and every mock API request, on one clock;
//   messages  the messages list each call sent: what it carried over, and what it added;
//   fixture   the mock API's request log.
// Built from the run's events alone, so a reopened run looks exactly as it did live.
(function () {
  var PANELS = LAB.panels;
  var $ = function (id) { return document.getElementById(id); };
  document.querySelectorAll(".pane[data-panel]").forEach(function (p) { p.hidden = PANELS.indexOf(p.dataset.panel) < 0; });
  function on(name) { return PANELS.indexOf(name) >= 0; }
  var ANY = on("timeline") || on("messages") || on("fixture");
  var evs = [], shownCall = null, timer = null;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function clip(s, n) { s = String(s); return s.length > n ? s.slice(0, n) + "…" : s; }
  function json(v) { return typeof v === "string" ? v : JSON.stringify(v); }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function pill(cls, text) { return el("span", "pill " + cls, text); }

  // The Message a call returned: the JSON body, or rebuilt from a stream's events.
  function messageOf(body) {
    if (!body) return null;
    if (body.type === "message") return body;
    if (!body.events) return null;
    var msg = null, blocks = [];
    body.events.forEach(function (e) {
      var d = e.data || {};
      if (d.type === "message_start") msg = Object.assign({}, d.message);
      else if (d.type === "content_block_start") blocks[d.index] = Object.assign({}, d.content_block);
      else if (d.type === "content_block_delta" && blocks[d.index]) {
        var b = blocks[d.index], dl = d.delta || {};
        if (dl.type === "text_delta") b.text = (b.text || "") + dl.text;
        if (dl.type === "thinking_delta") b.thinking = (b.thinking || "") + dl.thinking;
        if (dl.type === "input_json_delta") b._json = (b._json || "") + dl.partial_json;
      } else if (d.type === "message_delta" && msg) Object.assign(msg, d.delta || {});
    });
    if (!msg) return null;
    blocks.forEach(function (b) { if (b && b._json !== undefined) { try { b.input = JSON.parse(b._json || "{}"); } catch (x) {} delete b._json; } });
    msg.content = blocks.filter(Boolean);
    return msg;
  }
  // A failed call's error message. The gateway wraps Anthropic's error JSON, as a string, at the start
  // of its own message: the inner message is the useful one.
  function errorText(body) {
    var msg = body && body.error && typeof body.error.message === "string" ? body.error.message : null;
    if (msg === null) return body ? clip(json(body), 300) : "";
    var inner = /"message"\s*:\s*"((?:[^"\\]|\\.)*)"/.exec(msg);
    if (inner) { try { return JSON.parse('"' + inner[1] + '"'); } catch (e) {} }
    return clip(msg, 300);
  }
  function blocksOf(message) {
    return typeof message.content === "string" ? [{type: "text", text: message.content}] : (message.content || []);
  }
  function toolUseIds(message) {
    return message.role !== "assistant" ? [] : blocksOf(message)
      .filter(function (b) { return b.type === "tool_use"; }).map(function (b) { return b.id; });
  }
  // The "one message" check on the assistant message msgs[at]: every tool_use in it is answered in the ONE
  // user message right after it. The API joins consecutive user messages, so results split over several
  // get no error; only this check catches them. The same rule as results_in_one_message in experiments.py.
  function resultsCheck(msgs, at) {
    var ids = toolUseIds(msgs[at]);
    if (!ids.length) return null;
    var after = [];
    for (var k = at + 1; k < msgs.length && msgs[k].role !== "assistant"; k++) after.push(k);
    var withResults = after.filter(function (k) { return blocksOf(msgs[k]).some(function (b) { return b.type === "tool_result"; }); });
    var answered = {};
    after.forEach(function (k) { blocksOf(msgs[k]).forEach(function (b) { if (b.type === "tool_result") answered[b.tool_use_id] = k; }); });
    var missing = ids.filter(function (id) { return !(id in answered); });
    return {at: at, ids: ids, withResults: withResults, missing: missing,
            ok: !missing.length && withResults.length === 1 && withResults[0] === after[0]};
  }
  function checkPill(chk) {
    return chk.ok ? pill("pill-good", "one message")
         : chk.missing.length ? pill("pill-critical", chk.missing.length + " unanswered")
         : pill("pill-warning", "split over " + chk.withResults.length + " messages");
  }

  // Calls, the tools run between them, and the API requests, from the events.
  function model() {
    var byN = {}, calls = [], api = [], end = null, last = 1;
    evs.forEach(function (e) {
      var d = e.data;
      last = Math.max(last, e.t_ms);
      if (e.type === "llm.request") { byN[d.call] = {n: d.call, t: e.t_ms, req: d}; calls.push(byN[d.call]); }
      else if ((e.type === "llm.response" || e.type === "llm.error") && byN[d.call]) {
        var c = byN[d.call];
        c.res = d; c.failed = e.type === "llm.error" || d.status >= 400; c.end = e.t_ms;
        c.msg = e.type === "llm.response" && d.status < 400 ? messageOf(d.body) : null;
      } else if (e.type === "api.request") api.push({t: e.t_ms, d: d});
      else if (e.type === "run.exit") end = e.t_ms;
    });
    calls = calls.filter(function (c) { return c.req.body && Array.isArray(c.req.body.messages); });
    // A tool ran in your code between the response that asked for it and the next request,
    // which carries its tool_result. No instrumentation: it's read off the two calls.
    var tools = [];
    calls.forEach(function (c, i) {
      if (!c.msg) return;
      var next = calls[i + 1];
      blocksOf(c.msg).forEach(function (b) {
        if (b.type !== "tool_use") return;
        var result = null;
        if (next) next.req.body.messages.forEach(function (m) {
          blocksOf(m).forEach(function (r) { if (r.type === "tool_result" && r.tool_use_id === b.id) result = r; });
        });
        tools.push({t: c.end, until: next ? next.t : (end || last), use: b, result: result, from: c.n, next: next,
                    ended: end !== null});
      });
    });
    return {calls: calls, tools: tools, api: api, total: Math.max(end || last, 1), ended: end !== null};
  }

  // ------------------------------------------------------------ timeline
  function bar(kind, start, len, total) {
    var b = el("span", "trace-bar " + kind);
    b.style.setProperty("--start", (100 * start / total).toFixed(2) + "%");
    b.style.setProperty("--len", (100 * Math.max(len, 0) / total).toFixed(2) + "%");
    return b;
  }
  function traceRow(labelBits, child, dur, title, b) {
    var row = el("div", "trace-row"), label = el("div", "trace-label" + (child ? " child" : "")),
        d = el("div", "trace-dur", dur), track = el("div", "trace-track");
    row.setAttribute("role", "row");
    [label, d, track].forEach(function (x) { x.setAttribute("role", "cell"); });
    if (child === 2) label.style.paddingLeft = "34px";
    labelBits.forEach(function (x) { label.append(x); });
    track.title = title;
    track.append(b);
    row.append(label, d, track);
    return row;
  }
  function renderTimeline() {
    var box = $("timeline"), m = model();
    box.textContent = "";
    if (!m.calls.length && !m.api.length) {
      box.append(el("p", "small muted", "Every model call and every API request your code makes, in order, on one clock."));
      return;
    }
    var grid = el("div", "trace"), axis = el("div", "trace-axis"), h1 = el("div", "small muted", "Event"),
        h2 = el("div", "trace-dur", "Time"), ticks = el("div", "ticks");
    grid.setAttribute("role", "table");
    grid.setAttribute("aria-label", "Timeline: " + m.calls.length + " model call(s), " + m.api.length + " API request(s)");
    axis.setAttribute("role", "row");
    h1.style.alignSelf = "end"; h1.style.paddingBottom = "4px"; h2.style.alignItems = "end"; h2.style.paddingBottom = "4px";
    [0, 0.25, 0.5, 0.75, 1].forEach(function (f) {
      var s = el("span", null, (m.total * f / 1000).toFixed(1) + " s");
      s.style.left = (f * 100) + "%";
      ticks.append(s);
    });
    axis.append(h1, h2, ticks);
    grid.append(axis);
    var rows = [];
    m.calls.forEach(function (c) { rows.push({t: c.t, k: 0, c: c}); });
    m.tools.forEach(function (t) { rows.push({t: t.t, k: 1, tool: t}); });
    m.api.forEach(function (a) { rows.push({t: a.t, k: 2, a: a}); });
    rows.sort(function (x, y) { return x.t - y.t || x.k - y.k; });
    rows.forEach(function (r) {
      if (r.c) {
        var c = r.c, ms = c.res ? c.res.ms || 0 : Math.max(m.total - c.t, 0), u = (c.res && c.res.usage) || {};
        var tag = !c.res ? pill("pill-plain", "waiting")
                : c.failed ? pill("pill-critical", c.res.status ? String(c.res.status) : "no response")
                : pill("pill-plain pill-mono", (c.msg && c.msg.stop_reason) || String(c.res.status));
        var nUses = c.msg ? toolUseIds(Object.assign({role: "assistant"}, c.msg)).length : 0, bits = [el("span", "seq", String(c.n)), el("span", "name", "Call " + c.n), tag];
        if (nUses > 1) bits.push(pill("pill-plain pill-mono", nUses + " tool_use"));   // parallel calls: several in one response
        var row = traceRow(bits, 0,
          c.res ? (ms / 1000).toFixed(2) + " s" : "",
          "Call " + c.n + ": " + c.req.body.messages.length + " message(s) sent" +
          (c.res ? ", " + (ms / 1000).toFixed(2) + " s, input " + (u.input_tokens ?? "?") + ", output " + (u.output_tokens ?? "?") : ""),
          bar("llm", c.t, ms, m.total));
        row.addEventListener("click", function () { document.dispatchEvent(new CustomEvent("lab:show-call", {detail: c.n})); });
        row.style.cursor = "pointer";
        grid.append(row);
      } else if (r.tool) {
        var t = r.tool, state = t.result ? (t.result.is_error ? pill("pill-critical", "is_error") : pill("pill-good", "result sent"))
                : t.next ? pill("pill-critical", "no tool_result")
                : t.ended ? pill("pill-warning", "never sent back") : pill("pill-plain", "running");
        // Its input and the end of its id tell apart several calls of the same tool in one turn.
        var args = Object.values(t.use.input || {}).map(String).join(", "), name = el("span", "name two-line");
        name.append(el("code", null, t.use.name),
                    el("span", "small muted", clip(args, 40) + " · id …" + String(t.use.id).slice(-4)));
        grid.append(traceRow([name, state], 1, ((t.until - t.t) / 1000).toFixed(2) + " s",
          "Tool " + t.use.name + " " + json(t.use.input) + ", tool_use id " + t.use.id + ": call " + t.from + "'s response asked for it, and your code ran it" +
          (t.next ? ". Call " + t.next.n + (t.result ? " carried its tool_result." : " did not carry its tool_result.") : "."),
          bar("tool", t.t, t.until - t.t, m.total)));
      } else {
        var a = r.a.d, nm = el("span", "name"), cd = el("code", null, a.method + " " + a.path + (a.query ? "?" + a.query : ""));
        nm.append(cd);
        grid.append(traceRow([nm, pill(a.status < 400 ? "pill-plain pill-mono" : "pill-critical", String(a.status))], 2, "",
          "Mock API: " + a.method + " " + a.path + " → " + a.status, bar("http", r.t, m.total * 0.006, m.total)));
      }
    });
    box.append(grid);
    // The "one message" check, for each call whose tool_use blocks the next call answered (or should have).
    m.calls.forEach(function (c, i) {
      var next = m.calls[i + 1];
      if (!c.msg || !next) return;
      var ids = toolUseIds(Object.assign({role: "assistant"}, c.msg)), msgs = next.req.body.messages;
      if (!ids.length) return;
      var at = msgs.findIndex(function (msg) { return toolUseIds(msg).indexOf(ids[0]) >= 0; });
      var chk = at >= 0 ? resultsCheck(msgs, at) : {ok: false, ids: ids, missing: ids, withResults: []};
      var n = ids.length, what = "Call " + c.n + "'s " + (n === 1 ? "tool_use" : n + " tool_use blocks");
      var line = el("p", "small row", null), text = el("span", "secondary");
      text.textContent = chk.ok ? what + ": " + (n === 1 ? "its tool_result" : "all " + n + " tool_results") +
          " went back in one user message, message [" + chk.withResults[0] + "] of call " + next.n + "."
        : chk.missing.length ? what + ": " + chk.missing.length + " got no tool_result in call " + next.n + "'s messages."
        : what + ": the results were split over " + chk.withResults.length + " user messages in call " + next.n +
          ". The API joins them, so there's no error, but send them in one message: split results teach the model to stop calling tools in parallel.";
      line.style.margin = "var(--sp-3) 0 0";
      line.append(checkPill(chk), text);
      box.append(line);
    });
    var ins = m.calls.filter(function (c) { return c.res && c.res.usage; }).map(function (c) { return c.res.usage.input_tokens; });
    var cost = m.calls.reduce(function (s, c) { return s + ((c.res && c.res.cost_usd) || 0); }, 0);
    if (ins.length) {
      var sum = el("p", "small secondary num", "Input tokens per call: " + ins.join(" → ") + ". Every call resends the whole history. " +
                    "Total for the run: $" + cost.toFixed(6) + ".");
      sum.style.margin = "var(--sp-3) 0 0";
      box.append(sum);
    }
  }

  // ------------------------------------------------------------ messages
  function blockView(b) {
    var row = el("div", "block"), type = el("span", "block-type", b.type), body = el("span", "block-content");
    if (b.type === "text") body.textContent = clip(b.text || "", 600);
    else if (b.type === "thinking") {
      if (b.thinking) body.textContent = clip(b.thinking, 300);
      else { row.classList.add("is-empty"); body.textContent = "(display omitted, billed as output)"; }
    } else if (b.type === "tool_use") {
      body.append(el("code", null, b.name), document.createTextNode(" "), el("span", "json", json(b.input)),
                  el("div", "small muted", "id " + b.id));
    } else if (b.type === "tool_result") {
      if (b.is_error) row.classList.add("is-error");
      var content = Array.isArray(b.content) ? b.content.map(function (x) { return x.text || json(x); }).join("") : b.content;
      body.append(el("span", "json", clip(content == null ? "" : content, 400)),
                  el("div", "small muted", "answers tool_use_id " + b.tool_use_id + (b.is_error ? " · is_error: true" : "")));
    } else body.append(el("span", "json", clip(json(b), 300)));
    row.append(type, body);
    return row;
  }
  function messageView(index, message, tags, added) {
    var box = el("div", "msg" + (added ? " is-added" : "")), head = el("div", "msg-head"), body = el("div", "msg-body");
    head.append(el("span", "idx", index), el("span", "role", message.role), el("span", "spacer"));
    tags.forEach(function (t) { head.append(t); });
    blocksOf(message).forEach(function (b) { body.append(blockView(b)); });
    box.append(head, body);
    return box;
  }
  function renderMessages() {
    var view = $("messages-view"), tabs = $("messages-tabs"), m = model();
    tabs.textContent = ""; view.textContent = "";
    if (!m.calls.length) {
      view.append(el("p", "small muted", "The messages list each call sent: what it carried over from the call before, and what it added."));
      return;
    }
    var i = m.calls.findIndex(function (c) { return c.n === shownCall; });
    if (i < 0) i = m.calls.length - 1;
    m.calls.forEach(function (c, k) {
      var b = el("button", "tab", "Call " + c.n);
      b.type = "button"; b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(k === i));
      b.addEventListener("click", function () { shownCall = c.n; renderMessages(); });
      tabs.append(b);
    });
    var c = m.calls[i], msgs = c.req.body.messages, prev = i > 0 ? m.calls[i - 1] : null;
    var kept = prev ? prev.req.body.messages : [], grows = prev ? same(msgs.slice(0, kept.length), kept) : true;
    var carried = prev && grows ? kept.length : 0;
    var intro = "Call " + c.n + " sent " + msgs.length + " message" + (msgs.length === 1 ? "" : "s") + (prev
      ? ": " + carried + " carried over from call " + prev.n + " unchanged, " + (msgs.length - carried) + " added."
      : ". It's the first call, so all of it is new.");
    view.append(el("p", "small secondary", intro));
    if (!grows) {
      var warn = el("div", "callout callout-warning");
      warn.append(el("span", "icon icon-alert"), el("p", "small", "An earlier message changed since call " + prev.n +
        ". History should only grow: send every earlier message back exactly as it was."));
      view.append(warn);
    }
    // Each assistant turn's tool_use blocks, checked against the messages after it: "one message", split or unanswered.
    var checks = {}, split = null;
    msgs.forEach(function (msg, k) {
      var chk = resultsCheck(msgs, k);
      if (!chk) return;
      if (!chk.ok && !chk.missing.length) split = split || chk;
      if (chk.missing.length) checks[k] = chk;                       // marked on the assistant turn
      chk.withResults.forEach(function (r) { checks[r] = chk; });   // and on each message carrying its results
    });
    if (split) {
      var sw = el("div", "callout callout-warning");
      sw.append(el("span", "icon icon-alert"), el("p", "small", "Message [" + split.at + "]'s " + split.ids.length +
        " tool_use blocks are answered over " + split.withResults.length + " user messages. The API joins consecutive " +
        "user messages, so there's no error, but send every result in one message: split results teach the model to stop calling tools in parallel."));
      view.append(sw);
    }
    var list = el("div", "messages");
    msgs.forEach(function (msg, k) {
      var added = k >= carried, tags = [];
      if (added) tags.push(pill("pill-accent", "new in call " + c.n));
      if (checks[k]) {
        var chk = checks[k], here = blocksOf(msg).filter(function (b) { return b.type === "tool_result"; }).length;
        var p = checkPill(chk);
        p.title = msg.role === "assistant" ? chk.missing.length + " of these tool_use blocks got no tool_result after them"
          : "This message answers " + here + " of message [" + chk.at + "]'s " + chk.ids.length + " tool_use block(s)";
        tags.unshift(p);
      }
      if (msg.role === "user" && blocksOf(msg).some(function (b) { return b.type === "tool_result" && b.is_error; })) tags.unshift(pill("pill-critical", "is_error"));
      list.append(messageView("[" + k + "]", msg, tags, added && i > 0));
    });
    view.append(list);
    if (c.res) {
      if (c.failed) {
        var err = el("div", "callout callout-critical"), txt = el("div");
        txt.append(el("p", "small", "Call " + c.n + " got no answer: " + (c.res.status ? "HTTP " + c.res.status : "no response") +
                      ". The error, unwrapped from the gateway's message:"));
        txt.append(el("p", "small mono", c.res.status ? errorText(c.res.body) : (c.res.error || "")));
        [].forEach.call(txt.children, function (p) { p.style.margin = "0 0 4px"; });
        err.append(el("span", "icon icon-alert"), txt);
        view.append(err);
      } else view.append(el("p", "small secondary",
          "What call " + c.n + " got back. Your code appends it to the list as the next assistant message" +
          (i + 1 < m.calls.length ? ": it is message [" + msgs.length + "] in call " + m.calls[i + 1].n + "." : ", if it calls again.")));
      if (c.msg) {
        var back = el("div", "messages");
        back.append(messageView("came back", c.msg, [pill("pill-plain pill-mono", "stop_reason " + c.msg.stop_reason)], false));
        view.append(back);
      }
    }
  }

  // ------------------------------------------------------------ the mock API's request log
  function renderApi() {
    var box = $("api-log"), m = model();
    box.textContent = "";
    $("api-count").textContent = m.api.length ? m.api.length + " request" + (m.api.length === 1 ? "" : "s") : "";
    if (!m.api.length) {
      box.append(el("p", "small muted", m.ended ? "No requests: your code never called the mock API in this run."
                                              : "Every request your tool code makes to the mock Meridian API, as the API saw it."));
      return;
    }
    var t = el("table", "table"), head = el("tr"), tb = el("tbody"), th = el("thead");
    ["#", "At", "Request", "Status", "Body back"].forEach(function (h) { head.append(el("th", null, h)); });
    th.append(head); t.append(th, tb);
    m.api.forEach(function (a) {
      var d = a.d, tr = el("tr"), st = el("td");
      st.append(pill(d.status < 400 ? "pill-good" : "pill-critical", String(d.status)));
      var req = el("td"); req.append(el("code", null, d.method + " " + d.path + (d.query ? "?" + d.query : "")));
      tr.append(el("td", "num", String(d.n)), el("td", "num", (a.t / 1000).toFixed(2) + " s"), req, st,
                el("td", "num", json(d.body).length + " chars"));
      tb.append(tr);
    });
    box.append(t);
    m.api.forEach(function (a) {
      var det = el("details", "disclosure"), s = el("summary", null, "Request " + a.d.n + ": the body the API sent back");
      var p = el("pre", "json-view", JSON.stringify(a.d.body, null, 2));
      det.append(s, p);
      box.append(det);
    });
  }

  function render() {
    if (on("timeline")) renderTimeline();
    if (on("messages")) renderMessages();
    if (on("fixture")) renderApi();
  }
  window.labViews = {
    reset: function () { evs = []; shownCall = null; render(); },
    event: function (ev) {   // many events arrive at once when a past run is reopened: draw once
      if (!ANY || ["llm.request", "llm.response", "llm.error", "api.request", "run.exit"].indexOf(ev.type) < 0) return;
      evs.push(ev);
      if (!timer) timer = setTimeout(function () { timer = null; render(); }, 60);
    }
  };
})();
