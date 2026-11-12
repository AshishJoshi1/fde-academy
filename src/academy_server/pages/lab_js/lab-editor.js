// The editor: one textarea per file, saved straight to playground/<step-id>/. Lesson steps highlight lines.
(function () {
  var STEP = LAB.step;
  var $ = function (id) { return document.getElementById(id); };
  var files = {}, order = [], current = null, entry = null, marked = [];
  var area = $("code"), gutter = $("gutter"), marks = $("marks"), state = $("save-state");

  function url(name) { return "/api/steps/" + encodeURIComponent(STEP) + "/files/" + encodeURIComponent(name); }
  function setState(text, cls) { state.textContent = text; state.className = "small " + (cls || "muted"); }
  function isDirty(name) { return !!files[name] && files[name].code !== files[name].saved; }
  function anyDirty() { return order.some(isDirty); }
  function showDirty() { if (anyDirty()) setState("unsaved changes", "secondary"); renderTabs(); }
  function lineHeight() { return parseFloat(getComputedStyle(area).lineHeight) || 20.8; }
  function shownMarks() { return current === entry ? marked : []; }
  function renderGutter() {
    var n = area.value.split("\n").length, hl = shownMarks();
    gutter.textContent = "";
    for (var i = 1; i <= n; i++) {
      var s = document.createElement("span");
      s.textContent = String(i);
      if (hl.indexOf(i) >= 0) s.className = "hl";
      gutter.append(s);
    }
    gutter.scrollTop = area.scrollTop;
    renderMarks();
  }
  function renderMarks() {
    marks.textContent = "";
    var lh = lineHeight(), top = parseFloat(getComputedStyle(area).paddingTop) || 10;
    shownMarks().forEach(function (n) {
      var m = document.createElement("div");
      m.className = "mark";
      m.style.top = (top + (n - 1) * lh - area.scrollTop) + "px";
      m.style.height = lh + "px";
      marks.append(m);
    });
  }
  // Called by the lesson: highlight these lines of the entry file and scroll them into view.
  function highlight(lines) {
    marked = lines || [];
    if (marked.length && current !== entry && files[entry]) open(entry);
    renderGutter();
    if (marked.length) area.scrollTop = Math.max(0, (Math.min.apply(null, marked) - 3) * lineHeight());
    renderMarks();
  }
  function renderTabs() {
    var bar = $("file-tabs");
    bar.textContent = "";
    order.forEach(function (name) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "tab"; b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(name === current));
      b.textContent = name + (isDirty(name) ? " •" : "");
      b.addEventListener("click", function () { open(name); });
      bar.append(b);
    });
  }
  function open(name) {
    if (current) files[current].code = area.value;
    current = name; area.value = files[name].code; area.scrollTop = 0;
    renderGutter(); renderTabs();
  }
  function load(view) {
    files = {}; order = Object.keys(view.files); current = null; entry = view.entry;
    order.forEach(function (n) { files[n] = {code: view.files[n].code, saved: view.files[n].code, hash: view.files[n].hash}; });
    open(order.indexOf(view.entry) >= 0 ? view.entry : order[0]);
    setState("saved", "muted");
    highlight(marked);
  }
  function save(name, force) {
    var f = files[name];
    return fetch(url(name), {method: "PUT", headers: {"content-type": "application/json"},
                             body: JSON.stringify({code: f.code, base_hash: force ? null : f.hash})})
      .then(function (r) { return r.json().then(function (j) { return [r, j]; }); })
      .then(function (rj) {
        if (rj[0].status === 409) {
          if (confirm(name + " changed on disk after this page loaded it (edited in VS Code?).\n\n" +
                      "OK: overwrite it with the editor's version.\nCancel: keep the disk version (reload the page to see it).")) {
            return save(name, true);
          }
          setState("not saved: the file changed on disk", "error-text");
          return false;
        }
        if (!rj[0].ok) { setState("not saved: " + (rj[1].detail || rj[0].status), "error-text"); return false; }
        f.saved = f.code; f.hash = rj[1].hash;
        return true;
      });
  }
  function saveAll() {
    if (current) files[current].code = area.value;
    return order.filter(isDirty).reduce(function (p, name) {
      return p.then(function (ok) { return ok ? save(name, false) : false; });
    }, Promise.resolve(true)).then(function (ok) {
      if (ok) setState("saved " + new Date().toLocaleTimeString(), "muted");
      renderTabs();
      return ok;
    });
  }
  function insert(text) {   // insertText keeps the browser's undo history
    if (!document.execCommand || !document.execCommand("insertText", false, text)) {
      area.setRangeText(text, area.selectionStart, area.selectionEnd, "end");
      area.dispatchEvent(new Event("input"));
    }
  }

  area.addEventListener("input", function () { files[current].code = area.value; renderGutter(); showDirty(); });
  area.addEventListener("scroll", function () { gutter.scrollTop = area.scrollTop; renderMarks(); });
  area.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveAll(); return; }
    if (e.key === "Tab" && !e.shiftKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); insert("    "); return; }
    if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !e.shiftKey) {   // keep indentation; indent after ':'
      var before = area.value.slice(0, area.selectionStart), line = before.slice(before.lastIndexOf("\n") + 1);
      e.preventDefault();
      insert("\n" + line.match(/^[ \t]*/)[0] + (/:\s*$/.test(line) ? "    " : ""));
    }
  });
  new ResizeObserver(function () { gutter.style.height = area.offsetHeight + "px"; }).observe(area);
  $("save").addEventListener("click", saveAll);
  $("reset").addEventListener("click", function () {
    if (!confirm("Reset to the starter code? Your edits will be replaced.\n" +
                 "(Every past run keeps a snapshot of the code it ran, and git has the history.)")) return;
    fetch("/api/steps/" + encodeURIComponent(STEP) + "/reset", {method: "POST"})
      .then(function (r) { return r.json(); }).then(load);
  });
  window.addEventListener("beforeunload", function (e) { if (anyDirty()) { e.preventDefault(); e.returnValue = ""; } });
  fetch("/api/steps/" + encodeURIComponent(STEP) + "/files").then(function (r) { return r.json(); }).then(load);
  window.labEditor = {saveAll: saveAll, highlight: highlight};
})();
