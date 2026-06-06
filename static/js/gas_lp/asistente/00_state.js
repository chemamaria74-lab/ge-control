const token = localStorage.getItem('ge_gaslp_internal_token') || '';
let CLIENTES = [];
let FACTURAS = [];
let COMPLEMENTOS = [];
let FACILITIES = [];
let CATALOGOS = {choferes:[], vehiculos:[], rutas:[], ubicaciones:[], instalaciones:[], mercancias:[]};
let CURRENT_COMPANY = null;
let CURRENT_ASSISTANT = null;
let COMP_SEL = {};
let COMP_CONFIRM_CONTEXT = null;
let EDIT_CLIENT_ID = null;
let EMAIL_FACTURA_ID = null;
let DASH_CLIENT_KEY = '';
let isStamping = false;
let suppressFacturaStatus = false;
let CP_PREVIEW_READY = false;
let CP_PREVIEW_VALIDO = false;
let CP_FINAL_PAYLOAD = null;
let ACTIVE_CP_TAB = 'timbrar';
let transferConfirmResolver = null;
let invoiceConfirmResolver = null;
let ACTIVE_OPERATION = 'venta';
let INVOICE_FINAL_PAYLOAD = null;
const SAT_REGIMENES = [
  ['601','General de Ley Personas Morales'],
  ['603','Personas Morales con Fines no Lucrativos'],
  ['605','Sueldos y Salarios e Ingresos Asimilados a Salarios'],
  ['606','Arrendamiento'],
  ['607','Régimen de Enajenación o Adquisición de Bienes'],
  ['608','Demás ingresos'],
  ['610','Residentes en el Extranjero sin Establecimiento Permanente en México'],
  ['611','Ingresos por Dividendos (socios y accionistas)'],
  ['612','Personas Físicas con Actividades Empresariales y Profesionales'],
  ['614','Ingresos por intereses'],
  ['615','Régimen de los ingresos por obtención de premios'],
  ['616','Sin obligaciones fiscales'],
  ['620','Sociedades Cooperativas de Producción que optan por diferir sus ingresos'],
  ['621','Incorporación Fiscal'],
  ['622','Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras'],
  ['623','Opcional para Grupos de Sociedades'],
  ['624','Coordinados'],
  ['625','Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas'],
  ['626','Régimen Simplificado de Confianza']
];
const SAT_USOS_CFDI = [
  ['G01','Adquisición de mercancías'],
  ['G02','Devoluciones, descuentos o bonificaciones'],
  ['G03','Gastos en general'],
  ['I01','Construcciones'],
  ['I02','Mobiliario y equipo de oficina por inversiones'],
  ['I03','Equipo de transporte'],
  ['I04','Equipo de cómputo y accesorios'],
  ['I05','Dados, troqueles, moldes, matrices y herramental'],
  ['I06','Comunicaciones telefónicas'],
  ['I07','Comunicaciones satelitales'],
  ['I08','Otra maquinaria y equipo'],
  ['D01','Honorarios médicos, dentales y gastos hospitalarios'],
  ['D02','Gastos médicos por incapacidad o discapacidad'],
  ['D03','Gastos funerales'],
  ['D04','Donativos'],
  ['D05','Intereses reales efectivamente pagados por créditos hipotecarios'],
  ['D06','Aportaciones voluntarias al SAR'],
  ['D07','Primas por seguros de gastos médicos'],
  ['D08','Gastos de transportación escolar obligatoria'],
  ['D09','Depósitos en cuentas para el ahorro, primas de pensiones'],
  ['D10','Pagos por servicios educativos (colegiaturas)'],
  ['S01','Sin efectos fiscales'],
  ['CP01','Pagos'],
  ['CN01','Nómina']
];
const CONCEPTOS_FACTURA = {
  gas_lp_litro: {
    descripcion: 'Gas licuado de petróleo',
    clave_prod_serv: '15111510',
    clave_unidad: 'LTR',
    unidad: 'Litro',
    no_identificacion: 'GLP-LTR',
    iva_rate: '0.16',
    serie: 'AA'
  }
};
