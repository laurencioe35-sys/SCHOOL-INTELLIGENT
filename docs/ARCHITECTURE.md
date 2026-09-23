# Arquitectura

## Capas
- API: HTTP, validación y serialización.
- Aplicación: casos de uso y políticas.
- Dominio: invariantes de negocio.
- Persistencia: SQLAlchemy/PostgreSQL.
- Agentes: ejecución controlada y auditable.

## Tenancy
Todas las entidades operativas incluyen `tenant_id`. El backend obtiene el tenant desde
el token y nunca acepta un tenant arbitrario desde el payload de una operación.

## Evolución
La base actual es deliberadamente pequeña pero funcional. Los dominios académicos,
financieros, RRHH, comunicaciones y analítica deben incorporarse como módulos aislados,
cada uno con contratos y pruebas.
