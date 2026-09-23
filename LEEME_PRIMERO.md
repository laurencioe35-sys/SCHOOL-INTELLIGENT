# Cómo usar este paquete (actualizado a ERP V21)

## 01_documentos_maestros/
- `ERP_ENTERPRISE_AUTONOMO_V2_ROBUSTO.md` (V1-V21) → renómbralo a `CLAUDE.md` en la raíz del repo `erp-enterprise/`.
  Incluye ahora el vertical completo `colegio_virtual/`: admisiones, currículo, aula virtual, gradebook/boletines,
  proctoring, historial académico, certificados de graduación y biblioteca de contenido con licenciamiento.
- `PIZARRA_INTELIGENTE_ALTA_INGENIERIA.md` → renómbralo a `CLAUDE.md` en la raíz del repo `smart-whiteboard/` (repo separado)
- Los `.pdf` son la misma versión, para leer sin abrir un editor de código

## 02_auditoria/
`AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md` — cópialo a `docs/` en ambos repos.

## 03_prompts_arranque/
15 prompts (10 ERP/Pizarra originales + 5 colegio_virtual), uno por módulo del backlog.
Nota: los prompts de colegio_virtual_gradebook y colegio_virtual_admissions referencian código
que ahora se extendió más en V17-V21 (report_card_generator, transcript_service, certificate_generator,
content_library) — el prompt sigue siendo válido, el CLAUDE.md tiene el detalle adicional.

## 04_mensaje_loop_completo/
El mensaje único que reemplaza pegar los 15 prompts uno por uno.

## Orden de lectura sugerido
1. `01_documentos_maestros/ERP_ENTERPRISE_AUTONOMO_V2_ROBUSTO.pdf` — tabla de contenidos
2. `02_auditoria/AUDITORIA_CONSISTENCIA_ERP_PIZARRA.md`
3. `04_mensaje_loop_completo/MENSAJE_ARRANQUE_LOOP_COMPLETO.md` para arrancar
