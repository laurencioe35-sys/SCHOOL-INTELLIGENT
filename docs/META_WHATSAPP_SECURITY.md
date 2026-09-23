# Meta y WhatsApp

Los webhooks requieren firma constante e idempotencia de siete dias. WhatsApp
requiere opt-in explicito y plantillas aprobadas. `invoice_notification` se
registra como placeholder no aprobado: una factura puede registrar la intencion
de notificar sin tumbar el flujo ni enviar texto no aprobado.