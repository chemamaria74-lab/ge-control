(function(){
  let overlay,detail;
  function ensure(){
    if(overlay)return overlay;
    overlay=document.createElement('div');
    overlay.className='ge-company-switch-overlay';
    overlay.hidden=true;
    overlay.setAttribute('aria-live','assertive');
    overlay.setAttribute('aria-busy','true');
    overlay.innerHTML='<div class="ge-company-switch-card" role="status"><span class="ge-company-switch-spinner" aria-hidden="true"></span><strong>Cambiando de empresa…</strong><small>Cargando la información correcta.</small></div>';
    detail=overlay.querySelector('small');
    document.body.appendChild(overlay);
    return overlay;
  }
  function companyLabel(company){
    if(!company)return '';
    if(company.all)return company.label||'Todas las empresas';
    return [company.nombre||company.name,company.rfc].filter(Boolean).join(' · ');
  }
  function show(company,select){
    ensure();
    const label=companyLabel(company);
    detail.textContent=label?`Cargando ${label}`:'Cargando la información correcta.';
    overlay.hidden=false;
    document.body.classList.add('ge-company-switching');
    if(select)select.disabled=true;
  }
  function hide(select){
    ensure().hidden=true;
    document.body.classList.remove('ge-company-switching');
    if(select)select.disabled=false;
  }
  async function run(company,select,task){
    show(company,select);
    try{
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      return await task();
    }finally{
      hide(select);
    }
  }
  window.GECompanySwitch={show,hide,run};
})();
