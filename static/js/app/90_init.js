// Restore role from localStorage immediately (before verifySession returns)
applyRole(currentUserRole);
prefillHistSelector();
loadModuleFromStorage();  // Cargar módulo guardado
// verifySession maneja el flujo completo:
// token inválido → showLogin | token válido → empresa en session → cargarDatosDashboard
//                                           | sin empresa en session → iniciarFlujoEmpresa
verifySession();
