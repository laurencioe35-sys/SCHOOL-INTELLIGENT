# Despliegue en Kubernetes (producción)

Estos manifiestos son el equivalente productivo de `docker-compose.yml`
(explícitamente documentado ahí como "solo desarrollo local"). Cubren
`core-erp-backend`, `batch-worker` y `crdt-sync-server`.

## Qué SÍ resuelve esto
- Deployments con réplicas, health checks, requests/limits.
- Autoescalado horizontal (HPA) para `core-erp-backend` y
  `crdt-sync-server` — el `batch-worker` corre con 1 réplica a propósito
  (ver comentarios en `11-batch-worker.yaml`: la cola Redis única no
  soporta consumidores concurrentes sin particionarla primero).
- Secretos vía External Secrets Operator + AWS Secrets Manager (o Vault,
  ver comentarios en `02-external-secrets.yaml`), en vez de texto plano
  en git.
- Ingress con TLS automático (cert-manager) y timeouts largos para el
  WebSocket de `crdt-sync-server`.
- Job de migración (`alembic upgrade head`) separado del Deployment, para
  correr una sola vez por release.

## Qué NO resuelve esto (requiere infraestructura/cuentas reales)
- **Postgres y Redis en sí**: se asumen SERVICIOS GESTIONADOS (Amazon RDS
  Multi-AZ, Amazon ElastiCache/MemoryDB, o equivalentes en GCP/Azure), no
  pods de este clúster — ver el razonamiento en `01-configmap.yaml`. Solo
  falta apuntar `ERP_DATABASE_URL`/`ERP_REDIS_URL` (en el Secret) a esos
  endpoints reales.
- **El SFU de WebRTC** (LiveKit): `multimedia-stream-server/streaming/webrtc_handler.ts`
  documenta el contrato de integración pero no incluye un servidor LiveKit
  porque requiere puertos UDP/TCP de media y, normalmente, un TURN server
  — no algo que se resuelva con un Deployment genérico. Para producción,
  usar LiveKit Cloud (gestionado) o su Helm chart oficial
  (`livekit/livekit-server`) como un release aparte, y configurar
  `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` en el Secret una vez exista esa
  cuenta.
- **Build y push de las imágenes**: ✅ resuelto por
  `.github/workflows/build-and-push-images.yml` — construye
  `erp-core-backend` y `erp-crdt-sync-server` y las sube a GHCR
  (`ghcr.io/<owner>/erp-core-backend`, `ghcr.io/<owner>/erp-crdt-sync-server`)
  en cada push a `main` que toque esos directorios, con tags por SHA,
  rama y versión semántica. **No ejecutado en este sandbox** (no hay
  daemon de Docker disponible aquí — ver nota en el propio workflow); si
  vas a usar un registry distinto a GHCR (ECR, Docker Hub, Artifact
  Registry), cambiar `env.REGISTRY` y el paso de login por el que
  corresponda. Una vez que corra al menos una vez en tu repo real,
  reemplazar los placeholders `REGISTRY/erp-core-backend:TAG` de estos
  manifiestos por la imagen y el tag reales (o automatizar ese reemplazo
  con `kustomize edit set image` como un paso más del mismo workflow).
- **DNS real**: `api.tu-dominio.edu.pe` / `crdt.tu-dominio.edu.pe` son
  placeholders en `20-ingress.yaml`.

## Uso

```bash
# 1) Generar y publicar los secretos que sí podemos generar nosotros:
../../scripts/generate_secrets.sh --backend aws-secrets-manager \
  --secret-name erp-educativo/prod

# 2) Agregar a esa misma entrada (a mano, una sola vez) los secretos que
#    dependen de una cuenta de terceros y no se pueden generar:
#    ERP_DATABASE_URL, PAYMENT_GATEWAY_API_KEY, ANTHROPIC_API_KEY,
#    LIVEKIT_API_KEY/SECRET.

# 3) Instalar External Secrets Operator (una sola vez por clúster):
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace

# 4) Aplicar los manifiestos:
kubectl apply -k .

# 5) Verificar el rollout:
kubectl -n erp-educativo get pods,hpa,ingress
```
