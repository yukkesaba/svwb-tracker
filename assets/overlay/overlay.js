// SVWB Tracker の配信用表示で共通に使う部分。
// 同じフォルダの data.js（トラッカーが書き出す）を 2 秒ごとに読み直して、各ページの描画関数に渡す
(function () {
  var handlers = [];
  var last = null;
  var lastKey = "";

  function el(id) { return document.getElementById(id); }

  window.SVWB = {
    onData: function (fn) {
      handlers.push(fn);
      if (last) fn(last, false);
    },
    text: function (id, v) {
      var e = el(id);
      if (e) e.textContent = v;
    },
    show: function (selector, on) {
      var list = document.querySelectorAll(selector);
      for (var i = 0; i < list.length; i++) list[i].style.display = on ? "" : "none";
    },
    // 勝率の色: 55% 以上は勝ち色、45% 以下は負け色
    rateClass: function (rate) {
      if (rate === null || rate === undefined) return "";
      return rate >= 55 ? "win" : rate <= 45 ? "loss" : "";
    },
    setClass: function (id, base, extra) {
      var e = el(id);
      if (e) e.setAttribute("class", base + (extra ? " " + extra : ""));
    },
    streakText: function (d) {
      if (!d.streak) return "";
      return d.streak + (d.streak_kind === "win" ? "連勝中" : "連敗中");
    },
    signed: function (v) { return v > 0 ? "+" + v : String(v); },
    marks: function (id, recent, cls) {
      var box = el(id);
      if (!box) return;
      box.innerHTML = "";
      for (var i = 0; i < recent.length; i++) {
        var s = document.createElement("span");
        s.className = cls + " " + recent[i];
        box.appendChild(s);
      }
    },
    pulse: function (id) {
      var e = el(id);
      if (!e) return;
      e.classList.remove("pulse");
      void e.offsetWidth; // アニメーションをやり直す
      e.classList.add("pulse");
    }
  };

  function load() {
    var s = document.createElement("script");
    s.src = "data.js?t=" + Date.now(); // 毎回読み直す
    s.onload = function () {
      s.remove();
      var d = window.SVWB_DATA;
      if (!d) return;
      var key = JSON.stringify(d);
      if (key === lastKey) return;
      var changed = last !== null && last.total !== d.total; // 試合が増えた
      last = d;
      lastKey = key;
      for (var i = 0; i < handlers.length; i++) handlers[i](d, changed);
    };
    s.onerror = function () { s.remove(); };
    document.head.appendChild(s);
  }

  load();
  setInterval(load, 2000);
})();
