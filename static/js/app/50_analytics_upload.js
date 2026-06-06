// ── Ventas Analytics ──────────────────────────────────────────────────────
(function() {
  const sel = document.getElementById('ventasYear');
  const now = new Date().getFullYear();
  for (let y = now; y >= now - 5; y--) {
    const o = document.createElement('option');
    o.value = y; o.textContent = y;
    if (y === now) o.selected = true;
    sel.appendChild(o);
  }
})();

function fmtNum(n, dec=0) {
  if (isNaN(n) || n === null) return '0';
  return Number(n).toLocaleString('es-MX', {minimumFractionDigits:dec, maximumFractionDigits:dec});
}
function fmtPesos(n) {
  return '$' + fmtNum(n, 2);
}
function fmtCompact(n) {
  if (!n || isNaN(n)) return '$0';
  if (Math.abs(n) >= 1_000_000) return '$' + fmtNum(n / 1_000_000, 2) + ' M';
  if (Math.abs(n) >= 1_000)     return '$' + fmtNum(n / 1_000, 1) + ' K';
  return '$' + fmtNum(n, 2);
}
function fmtLitros(n) {
  if (!n || isNaN(n)) return '0 L';
  if (Math.abs(n) >= 1_000_000) return fmtNum(n / 1_000_000, 3) + ' ML';
  if (Math.abs(n) >= 1_000)     return fmtNum(n / 1_000, 1) + ' K L';
  return fmtNum(n, 2) + ' L';
}

async function loadVentasAnalytics() {
  if (!authToken) return;
  const year   = document.getElementById('ventasYear').value;
  const facSel = document.getElementById('ventasFacility');
  const facId  = facSel ? (parseInt(facSel.value) || '') : '';
  const st     = document.getElementById('ventasStatus');
  st.textContent = 'Cargando...';
  document.getElementById('ventasNoData').style.display = 'none';
  let url = '/api/analytics/ventas?year=' + year;
  if (facId) url += '&facility_id=' + facId;
  try {
    const res  = await fetch(url, { headers: authHeader() });
    const data = await res.json();
    renderVentasCharts(data.monthly || [], data.capacidad || null);
    st.textContent = '';
  } catch(e) {
    st.textContent = 'Error al cargar datos.';
  }
}

function renderVentasCharts(monthly, capacidad) {
  const totalLitros    = monthly.reduce((s,m) => s + m.litros,     0);
  const totalPesos     = monthly.reduce((s,m) => s + m.pesos,      0);
  const totalLitrosRec = monthly.reduce((s,m) => s + m.litros_rec, 0);
  const mesesActivos   = monthly.filter(m => m.litros > 0).length;

  document.getElementById('kpiLitros').textContent    = fmtLitros(totalLitros);
  document.getElementById('kpiPesos').textContent     = fmtCompact(totalPesos);
  document.getElementById('kpiLitrosRec').textContent = fmtLitros(totalLitrosRec);
  document.getElementById('kpiMeses').textContent     = mesesActivos + ' / 12';

  const hasAnyReport = monthly.some(m => m.has_report);
  if (!hasAnyReport) {
    document.getElementById('ventasNoData').style.display = '';
  }

  // ── Bar chart: litros vendidos ──────────────────────────────────────────
  const barContainer = document.getElementById('barChartLitros');
  barContainer.innerHTML = '';
  const maxL = Math.max(...monthly.map(m => m.litros), 1);
  monthly.forEach(m => {
    const pct  = Math.max(Math.round((m.litros / maxL) * 100), m.litros > 0 ? 4 : 0);
    const col  = document.createElement('div');
    col.className = 'bar-col';
    const valLabel = m.litros > 0
      ? '<div style="font-size:.55rem;color:#9a3412;text-align:center;line-height:1.2;margin-bottom:2px;font-weight:600">' + fmtLitros(m.litros) + '</div>'
      : '<div style="font-size:.55rem;color:#cbd5e1;text-align:center;margin-bottom:2px">—</div>';
    col.innerHTML =
      valLabel +
      '<div class="bar" style="height:' + pct + '%;background:' +
        (m.litros > 0 ? 'linear-gradient(180deg,#f97316,#ea580c)' : '#e2e8f0') +
        ';border-radius:4px 4px 0 0" title="' + m.label + ': ' + fmtNum(m.litros, 2) + ' L"></div>' +
      '<div class="bar-label">' + m.label + '</div>';
    barContainer.appendChild(col);
  });

  // ── Line chart: ingresos (SVG polyline) ───────────────────────────────
  const svg = document.getElementById('lineChartPesos');
  svg.innerHTML = '';
  const W = 800, H = 170, PAD = 10;
  const maxP = Math.max(...monthly.map(m => m.pesos), 1);

  // Grid lines + Y-axis labels
  const Y_LABELS = 4;
  for (let i = 0; i <= Y_LABELS; i++) {
    const y     = PAD + ((H - PAD*2) / Y_LABELS) * i;
    const val   = maxP * (1 - i / Y_LABELS);
    const gline = document.createElementNS('http://www.w3.org/2000/svg','line');
    gline.setAttribute('x1', 0); gline.setAttribute('x2', W);
    gline.setAttribute('y1', y); gline.setAttribute('y2', y);
    gline.setAttribute('stroke', i === Y_LABELS ? '#cbd5e1' : '#f1f5f9');
    gline.setAttribute('stroke-width','1');
    svg.appendChild(gline);
    // Y label (right-aligned)
    if (val > 0) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg','text');
      txt.setAttribute('x', W - 2);
      txt.setAttribute('y', y - 3);
      txt.setAttribute('text-anchor','end');
      txt.setAttribute('font-size','9');
      txt.setAttribute('fill','#94a3b8');
      txt.setAttribute('font-family','inherit');
      txt.textContent = fmtCompact(val);
      svg.appendChild(txt);
    }
  }

  // Points
  const pts = monthly.map((m, i) => {
    const x = PAD + (i / 11) * (W - PAD * 2);
    const y = H - PAD - ((m.pesos / maxP) * (H - PAD * 2));
    return [x, y, m];
  });

  // Area fill
  const area = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  const areaPoints = [
    [PAD, H - PAD],
    ...pts.map(p => [p[0], p[1]]),
    [pts[pts.length-1][0], H - PAD]
  ].map(p => p.join(',')).join(' ');
  area.setAttribute('points', areaPoints);
  area.setAttribute('fill','rgba(59,130,246,0.08)');
  svg.appendChild(area);

  // Polyline
  const pl = document.createElementNS('http://www.w3.org/2000/svg','polyline');
  pl.setAttribute('points', pts.map(p => p[0]+','+p[1]).join(' '));
  pl.setAttribute('fill','none');
  pl.setAttribute('stroke','#3b82f6');
  pl.setAttribute('stroke-width','2.5');
  pl.setAttribute('stroke-linecap','round');
  pl.setAttribute('stroke-linejoin','round');
  svg.appendChild(pl);

  // Dots
  pts.forEach(([x, y, m]) => {
    const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
    circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 5);
    circle.setAttribute('fill', m.pesos > 0 ? '#3b82f6' : '#e2e8f0');
    circle.setAttribute('stroke','#fff'); circle.setAttribute('stroke-width','2');
    const title = document.createElementNS('http://www.w3.org/2000/svg','title');
    title.textContent = m.label + ': ' + fmtPesos(m.pesos);
    circle.appendChild(title);
    svg.appendChild(circle);
  });

  // Month labels under ingresos line chart
  const lblRow = document.getElementById('lineLabels');
  lblRow.innerHTML = monthly.map(m =>
    '<span style="font-size:.58rem;color:#94a3b8;text-align:center;flex:1">' + m.label + '</span>'
  ).join('');

  // ── Line chart: Inventario final (almacenamiento) ───────────────────────
  const svgInv = document.getElementById('lineChartInv');
  svgInv.innerHTML = '';
  const maxInv = Math.max(...monthly.map(m => m.inv_final || 0), capacidad || 0, 1);

  // Grid lines + Y labels
  for (let i = 0; i <= 4; i++) {
    const y   = PAD + ((H - PAD*2) / 4) * i;
    const val = maxInv * (1 - i / 4);
    const gl  = document.createElementNS('http://www.w3.org/2000/svg','line');
    gl.setAttribute('x1',0); gl.setAttribute('x2',W);
    gl.setAttribute('y1',y); gl.setAttribute('y2',y);
    gl.setAttribute('stroke', i === 4 ? '#cbd5e1' : '#f1f5f9');
    gl.setAttribute('stroke-width','1');
    svgInv.appendChild(gl);
    if (val > 0) {
      const txt = document.createElementNS('http://www.w3.org/2000/svg','text');
      txt.setAttribute('x', W-2); txt.setAttribute('y', y-3);
      txt.setAttribute('text-anchor','end'); txt.setAttribute('font-size','9');
      txt.setAttribute('fill','#94a3b8'); txt.setAttribute('font-family','inherit');
      txt.textContent = fmtLitros(val);
      svgInv.appendChild(txt);
    }
  }

  const ptsInv = monthly.map((m, i) => {
    const x = PAD + (i / 11) * (W - PAD * 2);
    const v = m.inv_final || 0;
    const y = H - PAD - ((v / maxInv) * (H - PAD * 2));
    return [x, y, m];
  });

  // Area fill (teal)
  const areaInv = document.createElementNS('http://www.w3.org/2000/svg','polygon');
  areaInv.setAttribute('points', [
    [PAD, H-PAD],
    ...ptsInv.map(p => [p[0],p[1]]),
    [ptsInv[ptsInv.length-1][0], H-PAD]
  ].map(p=>p.join(',')).join(' '));
  areaInv.setAttribute('fill','rgba(20,184,166,0.10)');
  svgInv.appendChild(areaInv);

  // Polyline
  const plInv = document.createElementNS('http://www.w3.org/2000/svg','polyline');
  plInv.setAttribute('points', ptsInv.map(p=>p[0]+','+p[1]).join(' '));
  plInv.setAttribute('fill','none');
  plInv.setAttribute('stroke','#C8A96B');
  plInv.setAttribute('stroke-width','2.5');
  plInv.setAttribute('stroke-linecap','round');
  plInv.setAttribute('stroke-linejoin','round');
  svgInv.appendChild(plInv);

  // Dots
  ptsInv.forEach(([x, y, m]) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('cx',x); c.setAttribute('cy',y); c.setAttribute('r',5);
    c.setAttribute('fill', m.has_report ? '#C8A96B' : '#e2e8f0');
    c.setAttribute('stroke','#fff'); c.setAttribute('stroke-width','2');
    const t = document.createElementNS('http://www.w3.org/2000/svg','title');
    t.textContent = m.label + ': ' + (m.has_report ? fmtNum(m.inv_final,2) + ' L' : 'Sin reporte');
    c.appendChild(t);
    svgInv.appendChild(c);
  });

  // Dashed capacity-limit line (only when a facility capacity is known)
  if (capacidad && capacidad > 0 && maxInv > 0) {
    const capY = H - PAD - ((capacidad / maxInv) * (H - PAD * 2));
    const capLine = document.createElementNS('http://www.w3.org/2000/svg','line');
    capLine.setAttribute('x1', PAD); capLine.setAttribute('x2', W - PAD);
    capLine.setAttribute('y1', capY); capLine.setAttribute('y2', capY);
    capLine.setAttribute('stroke', '#ef4444');
    capLine.setAttribute('stroke-width', '1.5');
    capLine.setAttribute('stroke-dasharray', '6 4');
    svgInv.appendChild(capLine);
    const capTxt = document.createElementNS('http://www.w3.org/2000/svg','text');
    capTxt.setAttribute('x', W - PAD - 2);
    capTxt.setAttribute('y', capY - 4);
    capTxt.setAttribute('text-anchor', 'end');
    capTxt.setAttribute('font-size', '9');
    capTxt.setAttribute('fill', '#ef4444');
    capTxt.setAttribute('font-family', 'inherit');
    capTxt.setAttribute('font-weight', '600');
    capTxt.textContent = 'Capacidad máx: ' + fmtLitros(capacidad);
    svgInv.appendChild(capTxt);
  }

  document.getElementById('lineLabelsInv').innerHTML = monthly.map(m =>
    '<span style="font-size:.58rem;color:#94a3b8;text-align:center;flex:1">' + m.label + '</span>'
  ).join('');

  // ── Balance anual table ─────────────────────────────────────────────────
  const tbody = document.getElementById('balanceTbody');
  tbody.innerHTML = '';

  const capHdrRow = document.getElementById('balanceCapHdr');
  if (capHdrRow) capHdrRow.remove();
  if (capacidad) {
    const hdr = document.createElement('tr');
    hdr.id = 'balanceCapHdr';
    hdr.innerHTML = '<td colspan="8" style="padding:.3rem .6rem;background:#fef2f2;color:#991b1b;font-size:.73rem;border-bottom:1px solid #fecaca">' +
      'Capacidad física del tanque: <strong>' + fmtNum(capacidad, 2) + ' L</strong> — ' +
      'Las celdas resaltadas en rojo indican que el inventario supera este límite.' +
      '</td>';
    tbody.appendChild(hdr);
  }

  monthly.forEach(m => {
    const tr      = document.createElement('tr');
    const hasData = m.has_report && m.inv_inicial !== null;
    const stripe  = m.mes % 2 === 0 ? '#f8fafc' : '#fff';
    const hasAc   = m.has_report && (m.litros_autoconsumo || 0) > 0;
    const litrosCfdi = m.litros_cfdi !== undefined ? m.litros_cfdi : m.litros;

    const calcOver     = hasData && m.calc_exceeds_cap;
    const finOver      = m.has_report && m.exceeds_cap;
    const capCellStyle = 'background:#fee2e2;color:#991b1b;font-weight:700;';

    let statusCell = '<td style="text-align:center;font-size:1rem">—</td>';
    if (hasData) {
      if (m.balance_ok === true && !calcOver && !finOver) {
        statusCell = '<td style="text-align:center;font-size:1rem;color:#16a34a" title="Balance correcto"><i class="fa-solid fa-circle-check"></i></td>';
      } else if (calcOver || finOver) {
        const diff = m.inv_final !== null && m.inv_calc !== null ? ' Δ ' + fmtNum(Math.abs(m.inv_final - m.inv_calc), 2) + ' L' : '';
        statusCell = '<td style="text-align:center;font-size:.8rem;background:#fee2e2;color:#991b1b;font-weight:700" title="Supera capacidad' + diff + '"><i class="fa-solid fa-circle-exclamation"></i></td>';
      } else if (m.balance_ok === false) {
        const diff = m.inv_final !== null && m.inv_calc !== null ? ' (Δ ' + fmtNum(Math.abs(m.inv_final - m.inv_calc), 2) + ' L)' : '';
        statusCell = '<td style="text-align:center;font-size:1rem;color:#d97706" title="Diferencia detectada' + diff + '"><i class="fa-solid fa-triangle-exclamation"></i></td>';
      }
    }

    const tdR = 'padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;color:';
    tr.style.background = stripe;
    tr.innerHTML =
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;color:#374151;font-weight:600">' + m.label + '</td>' +
      '<td style="' + tdR + '#1e40af">'  + (hasData      ? fmtNum(m.inv_inicial, 2)   : '—') + '</td>' +
      '<td style="' + tdR + '#15803d">'  + (m.has_report ? fmtNum(m.litros_rec, 2)    : '—') + '</td>' +
      // Entregas CFDI (rojo)
      '<td style="' + tdR + '#9a3412">'  + (m.has_report ? fmtNum(litrosCfdi, 2)      : '—') + '</td>' +
      // Autoconsumo (ámbar si hay, guión si no)
      (hasAc
        ? '<td style="' + tdR + '#92400e;background:#fffbeb;font-weight:700">' + fmtNum(m.litros_autoconsumo, 2) + ' <span title="Autoconsumo registrado" style="font-size:.7rem">AC</span></td>'
        : '<td style="' + tdR + '#94a3b8">—</td>') +
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;' + (calcOver ? capCellStyle : 'color:#374151;') + '">' + (hasData ? fmtNum(m.inv_calc, 2) : '—') + '</td>' +
      '<td style="padding:.38rem .6rem;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;' + (finOver ? capCellStyle : 'color:#374151;') + '">' + (m.has_report && m.inv_final !== null ? fmtNum(m.inv_final, 2) : '—') + '</td>' +
      statusCell;
    tbody.appendChild(tr);
  });
}

document.getElementById('btnLoadVentas').addEventListener('click', loadVentasAnalytics);

// ── Poblar selectores de año ────────────────────────────────────────────────
(function() {
  const y = new Date().getFullYear();
  ['provYear','provAnio'].forEach(id => {
    const sel = document.getElementById(id);
    if (!sel) return;
    for (let i = y; i >= y - 3; i--) {
      const o = document.createElement('option');
      o.value = o.textContent = i;
      sel.appendChild(o);
    }
  });
})();

// ── Drop zones ────────────────────────────────────────────────────────────
setupDrop('dropExcel', 'fileExcel', 'btnExcel');
setupDropMulti('dropCFDI', 'fileCFDI', 'btnCFDI');

// Single-file drop zone (Excel/CSV)
function setupDrop(dId, iId, bId) {
  const drop = document.getElementById(dId);
  const inp  = document.getElementById(iId);
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const f = e.dataTransfer.files[0];
    if (f) attach(drop, inp, bId, f);
  });
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => { if (inp.files[0]) attach(drop, inp, bId, inp.files[0]); });
}
function attach(drop, inp, bId, f) {
  drop.querySelector('.lbl').textContent = f.name;
  inp._file = f;
  document.getElementById(bId).disabled = false;
}

// Multi-file drop zone (CFDI)
function setupDropMulti(dId, iId, bId) {
  const drop = document.getElementById(dId);
  const inp  = document.getElementById(iId);
  drop.addEventListener('dragover',  e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => {
    e.preventDefault(); drop.classList.remove('over');
    const files = Array.from(e.dataTransfer.files).filter(f => /\.(xml|zip)$/i.test(f.name));
    if (files.length) attachMulti(inp, bId, files);
  });
  drop.addEventListener('click', () => inp.click());
  inp.addEventListener('change', () => {
    if (inp.files.length) attachMulti(inp, bId, Array.from(inp.files));
  });
}
function attachMulti(inp, bId, newFiles) {
  const existing = inp._files || [];
  const names = new Set(existing.map(f => f.name));
  newFiles.forEach(f => { if (!names.has(f.name)) { existing.push(f); names.add(f.name); } });
  inp._files = existing;
  renderChips(inp, bId);
}
function renderChips(inp, bId) {
  const chips = document.getElementById('cfdiChips');
  const clear = document.getElementById('btnClearCFDI');
  const lbl   = document.getElementById('dropCFDILbl');
  const files = inp._files || [];
  if (!files.length) {
    chips.style.display = 'none'; chips.innerHTML = '';
    clear.style.display = 'none';
    lbl.textContent = 'Arrastra uno o varios archivos ZIP/XML aquí';
    document.getElementById(bId).disabled = true;
    return;
  }
  chips.style.display = 'flex'; clear.style.display = '';
  lbl.textContent = `${files.length} archivo(s) seleccionado(s)`;
  document.getElementById(bId).disabled = false;
  chips.innerHTML = files.map((f, i) =>
    `<span class="file-chip"><i class="fa-solid fa-file" style="margin-right:.3rem"></i>${f.name}<span class="rm" data-i="${i}">&times;</span></span>`
  ).join('');
  chips.querySelectorAll('.rm').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      inp._files.splice(parseInt(btn.dataset.i), 1);
      renderChips(inp, bId);
    });
  });
}
document.getElementById('btnClearCFDI').addEventListener('click', () => {
  const inp = document.getElementById('fileCFDI');
  inp._files = []; inp.value = '';
  renderChips(inp, 'btnCFDI');
  resetResult();
});

// ── Auto-limpiar archivos al cambiar el período ───────────────────────────
['procMes', 'procAnio'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('change', () => {
    const inp = document.getElementById('fileCFDI');
    if (inp && (inp._files || []).length > 0) {
      inp._files = []; inp.value = '';
      renderChips(inp, 'btnCFDI');
      resetResult();
    }
  });
});

// ── Auto-asignar ModalidadPermiso según tipo de instalación ──────────────
document.getElementById('fac_tipo_permiso')?.addEventListener('change', function() {
  actualizarInfoPermiso(this.value);
});

// Catálogo de permisos → actividad SAT (espeja PERMISO_CONFIG del backend)
const PERMISO_ACTIVIDAD = {
  'PER40': {code:'DIS', desc:'Distribución'}, 'PER41': {code:'DIS', desc:'Distribución'},
  'PER42': {code:'DIS', desc:'Distribución'}, 'PER51': {code:'DIS', desc:'Distribución'},
  'PER43': {code:'EXO', desc:'Expendio'},     'PER44': {code:'EXO', desc:'Expendio'},
  'PER45': {code:'CMN', desc:'Comercialización'},
  'PER50': {code:'ALM', desc:'Almacenamiento'},
};
function actualizarInfoPermiso(tipoPermiso) {
  const info = PERMISO_ACTIVIDAD[tipoPermiso] || {code:'DIS', desc:'Distribución'};
  const codeEl = document.getElementById('fac_actividad_code');
  const descEl = document.getElementById('fac_actividad_desc');
  const badge  = document.getElementById('fac_actividad_badge');
  if (codeEl) codeEl.textContent = info.code;
  if (descEl) descEl.textContent = info.desc;
  if (badge) {
    badge.style.background = info.code === 'EXO' ? '#fef9c3' : '#eff6ff';
    badge.style.borderColor = info.code === 'EXO' ? '#fcd34d' : '#bfdbfe';
    badge.style.color = info.code === 'EXO' ? '#92400e' : '#1e40af';
  }
}



// ── Samples ───────────────────────────────────────────────────────────────
document.getElementById('dlSampleExcel').addEventListener('click', () => {
  const csv = `fecha,tipo_movimiento,producto,volumen,unidad,inventario_inicial,inventario_final
2026-01-02,entrada,gas_lp,8000,litros,5000,
2026-01-05,salida,gas_lp,3000,litros,,
2026-01-10,entrada,gas_lp,14814.815,litros,,
2026-01-15,salida,gas_lp,5000,litros,,
2026-01-20,entrada,gas_lp,6000,litros,,
2026-01-31,salida,gas_lp,4000,litros,,20814.815`;
  dl('data:text/csv;charset=utf-8,' + encodeURIComponent(csv), 'ejemplo_gaslp.csv');
});

document.getElementById('dlSampleXML').addEventListener('click', () => {
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/3"
  Version="3.3" Fecha="2026-01-15T10:30:00" TipoDeComprobante="I"
  SubTotal="160000.00" Total="185600.00" Moneda="MXN" FormaPago="03">
  <cfdi:Emisor Rfc="GASD123456789" Nombre="DISTRIBUIDORA GAS LP SA DE CV" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="PLANTA9876543" Nombre="EMPRESA GAS LP SA DE CV" UsoCFDI="G03"/>
  <cfdi:Conceptos>
    <cfdi:Concepto ClaveProdServ="15101800" ClaveUnidad="LTR" Cantidad="8000.000"
      Descripcion="Gas LP a granel" ValorUnitario="20.00" Importe="160000.00"/>
  </cfdi:Conceptos>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
      UUID="a1b2c3d4-e5f6-7890-abcd-ef1234567890" FechaTimbrado="2026-01-15T10:35:00"
      RfcProvCertif="SAT970701NN3" SelloCFD="abc123" SelloSAT="xyz789" NoCertificadoSAT="00001"/>
  </cfdi:Complemento>
</cfdi:Comprobante>`;
  dl('data:application/xml;charset=utf-8,' + encodeURIComponent(xml), 'ejemplo_cfdi_gaslp.xml');
});

// ── Procesamiento ─────────────────────────────────────────────────────────
document.getElementById('btnExcel').addEventListener('click', () => {
  const f = document.getElementById('fileExcel')._file;
  if (f) process(f, '/api/upload', 'loadExcel', 'Excel/CSV', false);
});
document.getElementById('btnCFDI').addEventListener('click', () => {
  const inp   = document.getElementById('fileCFDI');
  const files = inp._files || [];
  if (files.length) processCFDI(files);
});
