async function trv2UploadDocument(event) {
  event.preventDefault();
  const file = document.getElementById('trv2-doc-file').files[0];
  const message = document.getElementById('trv2-doc-message');
  if (!file) {
    if (message) message.textContent = 'Selecciona un PDF, XML o imagen.';
    return;
  }
  const data = await trv2Api('POST', '/api/tr-v2/documentos', {
    perfil_id: TRV2_PERFIL?.id || null,
    viaje_id: Number(document.getElementById('trv2-doc-viaje-id').value || 0) || null,
    tipo_documento: document.getElementById('trv2-doc-tipo').value || 'factura_cliente',
    nombre_archivo: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size || 0,
    metadata: {fase: 'transporte_v2_fase_2_5', bucket_pendiente: true},
  }, {allowError: true});
  const text = data?.message || data?.detail || 'Metadata documental guardada. Bucket transporte-v2-documents sigue pendiente.';
  if (message) message.textContent = text;
  trv2Toast(data?.ok ? 'Metadata documental guardada.' : text, data?.ok ? 'success' : 'error');
}
