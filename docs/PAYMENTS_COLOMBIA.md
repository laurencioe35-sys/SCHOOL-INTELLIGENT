# Pagos Colombia

Nequi y PSE se modelan como cobros asincronos: `charge()` devuelve `pending` y
la conciliacion solo puede marcar la factura como pagada despues de una
confirmacion de webhook verificada e idempotente.

La firma exacta de webhook no se implementa ni se inventa en este entorno. Los
adaptadores lanzan `NotImplementedError` hasta que el contrato tecnico del
proveedor entregue el mecanismo, claves, version y vectores de prueba. Un
webhook no verificado nunca debe cambiar una factura ni crear un asiento.