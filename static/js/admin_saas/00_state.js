let TOKEN = localStorage.getItem('zc_token') || localStorage.getItem('sat_token') || '';
let TENANTS = [];
let COMPANIES = [];
let USERS_HEALTH = [];
let LICENSES = [];
let BILLING_SETTINGS = {};
let showOnlyProblems = false;
const SAT_REGIMENES = [
  ['601','General de Ley Personas Morales'],['603','Personas Morales con Fines no Lucrativos'],['605','Sueldos y Salarios'],
  ['606','Arrendamiento'],['612','Personas Físicas con Actividades Empresariales y Profesionales'],['616','Sin obligaciones fiscales'],
  ['621','Incorporación Fiscal'],['626','Régimen Simplificado de Confianza']
];
const USO_CFDI = [['G03','Gastos en general'],['S01','Sin efectos fiscales'],['CP01','Pagos'],['G01','Adquisición de mercancías'],['I04','Equipo de cómputo y accesorios']];
const METODOS_PAGO = [['PUE','Pago en una sola exhibición'],['PPD','Pago en parcialidades o diferido']];
const FORMAS_PAGO = [['03','Transferencia electrónica'],['99','Por definir'],['01','Efectivo'],['02','Cheque nominativo'],['04','Tarjeta de crédito'],['28','Tarjeta de débito']];
