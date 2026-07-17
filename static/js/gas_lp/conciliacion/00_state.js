const CONCILIACION_TOKEN_KEY='ge_gaslp_conciliacion_token';
const token=localStorage.getItem(CONCILIACION_TOKEN_KEY)||'';
const PROFILE_KEY='ge_gaslp_conciliacion_perfil_id';
let FACTURAS=[], PPD_PENDIENTES=[], FACILITIES=[], PERFILES=[], COMPLEMENTOS=[], CLIENTES=[], SEL={}, COMP_CONFIRM_CTX=null, CRED_CLIENT_KEY='', PUB_CONFIRM_RESOLVER=null, PUB_FINAL_PAYLOAD=null, PUBLICO_COMPANY_PRICE=0;
let CANCEL_CTX=null;
let BANK_RECONCILIATION_CTX=null;
let DASHBOARD_SEARCHED=false, COMPLEMENTOS_SEARCHED=false, CREDITO_SEARCHED=false, DESCUENTOS_SEARCHED=false, DESC_CLIENT_KEY='';
let activePerfilId=Number(localStorage.getItem(PROFILE_KEY)||'0')||null;
