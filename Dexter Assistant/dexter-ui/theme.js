/* ============================================================
   dexter-ui :: theme.js
   Handles:
     - Theme selection (light / dark / auto) persisted in
       localStorage and applied to <html data-theme="...">.
     - Sidebar collapse + mobile drawer state.
     - Tiny toast helper window.DexterUI.toast(msg, opts).
     - Optional version badge injection.
   No build step. Vanilla ES2015+.
   ============================================================ */
(function () {
  "use strict";

  var LS_THEME = "dx.theme.v2";
  var LS_SIDEBAR = "dx.sidebar";
  var VALID = ["light", "dark", "auto"];

  // When loaded inside the Dexter launcher iframe, mark the document so CSS
  // can hide redundant in-app hero headers / top-level page titles.
  try {
    if (window.top !== window.self) {
      document.documentElement.classList.add("dx-embedded");
    }
  } catch (e) {
    // Cross-origin access to window.top can throw — treat as embedded.
    document.documentElement.classList.add("dx-embedded");
  }

  function getStoredTheme() {
    var v = null;
    try { v = localStorage.getItem(LS_THEME); } catch (e) {}
    if (VALID.indexOf(v) === -1) return null;
    return v;
  }

  function defaultTheme() {
    // Project decision: light mode default.
    return "light";
  }

  function applyTheme(theme) {
    if (VALID.indexOf(theme) === -1) theme = defaultTheme();
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(LS_THEME, theme); } catch (e) {}
    document.dispatchEvent(new CustomEvent("dx:theme-change", { detail: { theme: theme } }));
    // Sync any matching radio inputs / select controls.
    var ctrls = document.querySelectorAll('[data-dx-theme-control]');
    ctrls.forEach(function (el) {
      if (el.tagName === "SELECT") el.value = theme;
      if (el.type === "radio") el.checked = (el.value === theme);
      if (el.dataset && el.dataset.dxThemeValue) {
        el.setAttribute("aria-pressed", el.dataset.dxThemeValue === theme ? "true" : "false");
      }
    });
  }

  function initTheme() {
    var stored = getStoredTheme();
    applyTheme(stored || defaultTheme());

    // Live response to OS changes when in auto mode.
    if (window.matchMedia) {
      var mql = window.matchMedia("(prefers-color-scheme: dark)");
      var handler = function () {
        if (document.documentElement.getAttribute("data-theme") === "auto") {
          // No attribute change needed; CSS @media handles it.
          document.dispatchEvent(new CustomEvent("dx:theme-change", { detail: { theme: "auto" } }));
        }
      };
      if (mql.addEventListener) mql.addEventListener("change", handler);
      else if (mql.addListener) mql.addListener(handler);
    }
  }

  // ---------- Sidebar ----------
  function applySidebarState(state) {
    var app = document.querySelector(".dx-app");
    if (!app) return;
    if (state === "collapsed" || state === "open" || state === "expanded") {
      app.setAttribute("data-sidebar", state);
    } else {
      app.removeAttribute("data-sidebar");
    }
    try {
      if (state === "collapsed") localStorage.setItem(LS_SIDEBAR, "collapsed");
      else localStorage.removeItem(LS_SIDEBAR);
    } catch (e) {}
  }

  function initSidebar() {
    var stored = null;
    try { stored = localStorage.getItem(LS_SIDEBAR); } catch (e) {}
    if (stored === "collapsed" && window.innerWidth > 900) {
      applySidebarState("collapsed");
    }

    document.addEventListener("click", function (ev) {
      var t = ev.target.closest("[data-dx-sidebar-toggle]");
      if (t) {
        ev.preventDefault();
        var app = document.querySelector(".dx-app");
        if (!app) return;
        var current = app.getAttribute("data-sidebar");
        if (window.innerWidth <= 900) {
          applySidebarState(current === "open" ? null : "open");
        } else {
          applySidebarState(current === "collapsed" ? null : "collapsed");
        }
        return;
      }
      // Overlay click on mobile closes drawer.
      if (ev.target.classList && ev.target.classList.contains("dx-sidebar-overlay")) {
        applySidebarState(null);
      }
    });
  }

  // ---------- Theme control bindings ----------
  function initThemeControls() {
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-dx-theme-value]");
      if (!btn) return;
      var v = btn.getAttribute("data-dx-theme-value");
      if (VALID.indexOf(v) !== -1) {
        ev.preventDefault();
        applyTheme(v);
      }
    });
    document.addEventListener("change", function (ev) {
      var el = ev.target;
      if (!el.matches || !el.matches("[data-dx-theme-control]")) return;
      var v = (el.tagName === "SELECT") ? el.value : el.value;
      if (VALID.indexOf(v) !== -1) applyTheme(v);
    });
  }

  // ---------- Toast helper ----------
  function ensureToastStack() {
    var s = document.querySelector(".dx-toast-stack");
    if (s) return s;
    s = document.createElement("div");
    s.className = "dx-toast-stack";
    s.setAttribute("role", "region");
    s.setAttribute("aria-live", "polite");
    s.setAttribute("aria-label", "Notifications");
    document.body.appendChild(s);
    return s;
  }

  function toast(message, opts) {
    opts = opts || {};
    var kind = opts.kind || "info";
    var timeoutMs = opts.timeout != null ? opts.timeout : 4500;
    var stack = ensureToastStack();
    var el = document.createElement("div");
    el.className = "dx-toast dx-toast--" + kind;
    el.setAttribute("role", "status");
    el.textContent = message == null ? "" : String(message);
    stack.appendChild(el);
    if (timeoutMs > 0) {
      setTimeout(function () {
        el.style.transition = "opacity 250ms ease, transform 250ms ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-4px)";
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 280);
      }, timeoutMs);
    }
    return el;
  }

  // ---------- Boot ----------
  function boot() {
    initTheme();
    initSidebar();
    initThemeControls();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Public namespace
  window.DexterUI = {
    applyTheme: applyTheme,
    getTheme: function () { return document.documentElement.getAttribute("data-theme") || defaultTheme(); },
    toast: toast,
    setSidebar: applySidebarState
  };
})();
