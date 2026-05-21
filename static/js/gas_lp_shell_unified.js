(function () {
  "use strict";

  if (window.__geGasLpShellBooted) return;
  window.__geGasLpShellBooted = true;

  const RFC_EMPTY = "RFC —";
  const RFC_PATTERN = /^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$/;
  let observer = null;
  let debounceId = 0;

  function cleanRfc(value) {
    const rfc = String(value || "")
      .replace(/^RFC\s+/i, "")
      .trim()
      .toUpperCase();
    if (!rfc || rfc === "—" || rfc.includes("CONFIGURADO")) return "";
    return rfc;
  }

  function readVisibleRfc() {
    const inputRfc = cleanRfc(document.getElementById("rfc")?.value);
    if (inputRfc) return inputRfc;

    const displayRfc = cleanRfc(document.getElementById("rfcDisplay")?.textContent);
    if (displayRfc && RFC_PATTERN.test(displayRfc)) return displayRfc;

    const activeRow = Array.from(document.querySelectorAll("#tbodyPerfiles tr")).find((row) =>
      row.textContent && row.textContent.includes("Activo")
    );
    if (activeRow) {
      const cells = activeRow.querySelectorAll("td");
      const rowRfc = cleanRfc(cells[1]?.textContent);
      if (rowRfc) return rowRfc;
    }

    return "";
  }

  function setHeaderRfc(rfc) {
    const badge = document.getElementById("gasLpRfcBadge");
    if (!badge) return;
    const clean = cleanRfc(rfc);
    badge.textContent = clean ? `RFC ${clean}` : RFC_EMPTY;
  }

  function syncHeaderRfc(fallbackPerfil) {
    const perfilRfc = fallbackPerfil && typeof fallbackPerfil === "object" ? fallbackPerfil.rfc : "";
    setHeaderRfc(readVisibleRfc() || perfilRfc || "");
  }

  function scheduleSync(fallbackPerfil) {
    if (debounceId) window.clearTimeout(debounceId);
    debounceId = window.setTimeout(() => {
      debounceId = 0;
      syncHeaderRfc(fallbackPerfil);
      if (cleanRfc(document.getElementById("gasLpRfcBadge")?.textContent) && observer) {
        observer.disconnect();
        observer = null;
      }
    }, 120);
  }

  function wrapGlobal(name, after) {
    const original = window[name];
    if (typeof original !== "function" || original.__geGasLpWrapped) return;
    const wrapped = function () {
      const result = original.apply(this, arguments);
      after.apply(this, arguments);
      return result;
    };
    wrapped.__geGasLpWrapped = true;
    window[name] = wrapped;
  }

  function boot() {
    if (!document.getElementById("gasLpRfcBadge")) return;

    wrapGlobal("actualizarSwitcherEmpresa", function (perfil) {
      scheduleSync(perfil);
    });
    wrapGlobal("actualizarRfcHint", function () {
      scheduleSync();
    });

    document.getElementById("rfc")?.addEventListener("input", () => scheduleSync(), { passive: true });
    document.getElementById("rfc")?.addEventListener("change", () => scheduleSync(), { passive: true });

    observer = new MutationObserver(() => scheduleSync());
    ["rfcDisplay", "empresaSwitcherName", "tbodyPerfiles"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el, { childList: true, subtree: true, characterData: true });
    });

    window.requestAnimationFrame(() => scheduleSync());
    window.addEventListener("pagehide", () => {
      if (debounceId) window.clearTimeout(debounceId);
      if (observer) observer.disconnect();
      observer = null;
      window.__geGasLpShellBooted = false;
    }, { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  window.geSyncGasLpHeader = syncHeaderRfc;
})();
