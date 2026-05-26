(function () {
  "use strict";

  if (window.__geGasLpShellBooted) return;
  window.__geGasLpShellBooted = true;

  const RFC_EMPTY = "RFC —";
  const RFC_PATTERN = /^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$/;
  let observer = null;
  let debounceId = 0;
  let uxTimer = 0;
  let uxRuns = 0;

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

  function replaceText(root, from, to) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      if (node.nodeValue && node.nodeValue.includes(from)) {
        node.nodeValue = node.nodeValue.replaceAll(from, to);
      }
    });
  }

  function setLabelFor(inputId, label) {
    const input = document.getElementById(inputId);
    const field = input?.closest(".field");
    const labelEl = field?.querySelector("label");
    if (labelEl) labelEl.textContent = label;
  }

  function normalizeGasLpCopy() {
    setLabelFor("gasInternalName", "Nombre");
    setLabelFor("gasInternalCode", "Usuario");
    setLabelFor("gasInternalPin", "Contraseña (PIN)");
    const codeInput = document.getElementById("gasInternalCode");
    if (codeInput) codeInput.placeholder = "Auto o usuario, ej. MARTHA";
    const pinInput = document.getElementById("gasInternalPin");
    if (pinInput) pinInput.placeholder = "Auto o contraseña temporal";

    document.querySelectorAll("th").forEach((th) => {
      if (th.textContent.trim() === "Código") th.textContent = "Usuario";
    });
    document.querySelectorAll("button").forEach((btn) => {
      if (btn.textContent.trim() === "Crear usuario interno") btn.textContent = "Crear asistente";
    });
    replaceText(document.getElementById("mpanel-admin"), "código", "usuario");
    replaceText(document.getElementById("mpanel-admin"), "Código", "Usuario");
    replaceText(document.getElementById("mpanel-admin"), "PIN temporal", "Contraseña (PIN)");

    const status = document.getElementById("gasInternalStatus");
    if (status && status.innerHTML.includes("Código:")) {
      status.innerHTML = status.innerHTML
        .replace("Código:", "Usuario:")
        .replace("PIN temporal:", "Contraseña (PIN):");
    }

    const facturar = document.getElementById("mpanel-facturar");
    replaceText(facturar, "Generar Carta Porte 3.1", "Carta Porte de traspaso interno");
    replaceText(facturar, "Generar Carta Porte", "Timbrar Carta Porte de traslado");
    replaceText(facturar, "Cargar entregas", "Cargar traspasos");
    replaceText(facturar, "No hay entregas registradas", "No hay traspasos internos registrados");
  }

  function enhanceDashboard() {
    document.querySelectorAll(".ge-gaslp-ops-strip").forEach(el => el.remove());
  }

  function runUxSync() {
    normalizeGasLpCopy();
    enhanceDashboard();
  }

  function scheduleUxSync() {
    if (uxRuns > 12) return;
    if (uxTimer) window.clearTimeout(uxTimer);
    uxTimer = window.setTimeout(() => {
      uxTimer = 0;
      uxRuns += 1;
      runUxSync();
    }, 160);
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
    window.requestAnimationFrame(() => scheduleUxSync());
    const uxObserver = new MutationObserver(() => scheduleUxSync());
    ["mpanel-admin", "mpanel-facturar", "mpanel-ventas"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) uxObserver.observe(el, { childList: true, subtree: true, characterData: true });
    });
    window.addEventListener("pagehide", () => {
      if (debounceId) window.clearTimeout(debounceId);
      if (uxTimer) window.clearTimeout(uxTimer);
      if (observer) observer.disconnect();
      uxObserver.disconnect();
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
