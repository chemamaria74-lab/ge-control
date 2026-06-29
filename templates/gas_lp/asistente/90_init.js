function disableNumberWheelChanges(){
  document.querySelectorAll('input[type="number"]').forEach(input => {
    input.addEventListener('wheel', event => {
      if(document.activeElement === input){
        event.preventDefault();
      }
    }, {passive:false});
  });
}
disableNumberWheelChanges();
initSatCatalogs();
syncPaymentMethod();
load();
