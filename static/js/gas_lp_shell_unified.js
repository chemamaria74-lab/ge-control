(function () {
  "use strict";

  const RFC_EMPTY = "RFC —";
  const RFC_PATTERN = /^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$/;

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
    wrapGlobal("actualizarSwitcherEmpresa", function (perfil) {
      syncHeaderRfc(perfil);
    });
    wrapGlobal("actualizarRfcHint", function () {
      syncHeaderRfc();
    });

    document.getElementById("rfc")?.addEventListener("input", () => syncHeaderRfc());
    document.getElementById("rfc")?.addEventListener("change", () => syncHeaderRfc());

    const observer = new MutationObserver(() => syncHeaderRfc());
    ["rfcDisplay", "empresaSwitcherName", "tbodyPerfiles"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el, { childList: true, subtree: true, characterData: true });
    });

    syncHeaderRfc();
    let attempts = 0;
    const timer = window.setInterval(() => {
      syncHeaderRfc();
      attempts += 1;
      if (attempts >= 24 || cleanRfc(document.getElementById("gasLpRfcBadge")?.textContent)) {
        window.clearInterval(timer);
      }
    }, 500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  window.geSyncGasLpHeader = syncHeaderRfc;
})();
