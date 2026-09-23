#!/usr/bin/env bash
# Genera secretos reales, puramente internos (no requieren ninguna
# cuenta de terceros), y opcionalmente los publica en un almacén de
# secretos gestionado en la nube en vez de solo imprimirlos en la
# terminal.
#
# TRANSPARENCIA: este script SOLO puede generar los secretos que
# dependen únicamente de nosotros (llaves HMAC/compartidas entre
# nuestros propios servicios). NO puede generar ni inventar:
#   - Credenciales de FaceIO (requieren una cuenta real en faceio.net)
#   - API keys de Anthropic (requieren una cuenta real en console.anthropic.com)
#   - Credenciales de pasarela de pago real (Stripe/Culqi/Niubiz/MercadoPago)
#     — requieren una cuenta de comercio real, verificada.
#   - Credenciales de LiveKit (requieren una cuenta/self-host real).
# Cualquier script que dijera generar esos valores estaría simplemente
# inventando datos — por eso esto solo resuelve la parte que sí depende
# únicamente de nosotros: ERP_SECRET_KEY y AI_AGENTS_INTERNAL_KEY.
#
# MODO POR DEFECTO (sin flags): igual que antes, solo imprime los
# secretos para copiarlos a mano a tu .env local.
#
# MODO CLOUD (nuevo): con --backend aws-secrets-manager o --backend
# vault, además de imprimirlos, los publica de verdad en ese almacén
# usando las CLIs oficiales (aws / vault), que deben estar instaladas y
# autenticadas de antemano (aws configure / vault login) — este script
# NO gestiona esas credenciales de acceso al almacén mismo, esas sí las
# aporta quien lo ejecuta.
#
# Uso:
#   ./generate_secrets.sh                                   # solo imprime (dev local)
#   ./generate_secrets.sh --backend aws-secrets-manager \
#       --secret-name erp-educativo/prod                    # imprime y publica en AWS
#   ./generate_secrets.sh --backend vault \
#       --vault-path secret/erp-educativo/prod              # imprime y publica en Vault
#   ./generate_secrets.sh --backend aws-secrets-manager \
#       --secret-name erp-educativo/prod --rotate            # rota (nuevos valores, misma entrada)

set -euo pipefail

BACKEND="none"
SECRET_NAME="erp-educativo/prod"
VAULT_PATH="secret/erp-educativo/prod"
ROTATE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) BACKEND="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --vault-path) VAULT_PATH="$2"; shift 2 ;;
    --rotate) ROTATE=true; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Argumento desconocido: $1" >&2; exit 1 ;;
  esac
done

ERP_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
AI_AGENTS_INTERNAL_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")

echo "Secretos generados:"
echo ""
echo "ERP_SECRET_KEY=$ERP_SECRET_KEY"
echo "AI_AGENTS_INTERNAL_KEY=$AI_AGENTS_INTERNAL_KEY"
echo ""
echo "Recordatorios:"
echo "  - multimedia-stream-server debe tener el MISMO ERP_SECRET_KEY (verifica"
echo "    los tokens del ERP con esta misma llave, ver state/auth.ts)."
echo "  - ai-agents-engine y core-erp-backend deben tener el MISMO"
echo "    AI_AGENTS_INTERNAL_KEY (autentica /grades/submit-from-agent, ver"
echo "    core-erp-backend/api/grades.py y ai-agents-engine/config/erp_client.py)."
echo ""

publish_to_aws_secrets_manager() {
  command -v aws >/dev/null 2>&1 || { echo "ERROR: falta instalar/configurar la AWS CLI." >&2; exit 1; }

  local payload
  payload=$(python3 - "$ERP_SECRET_KEY" "$AI_AGENTS_INTERNAL_KEY" <<'PY'
import json, sys
print(json.dumps({"ERP_SECRET_KEY": sys.argv[1], "AI_AGENTS_INTERNAL_KEY": sys.argv[2]}))
PY
)

  if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" >/dev/null 2>&1; then
    echo "Actualizando secreto existente '$SECRET_NAME' en AWS Secrets Manager..."
    aws secretsmanager put-secret-value --secret-id "$SECRET_NAME" --secret-string "$payload" >/dev/null
  else
    echo "Creando secreto '$SECRET_NAME' en AWS Secrets Manager..."
    aws secretsmanager create-secret --name "$SECRET_NAME" --secret-string "$payload" >/dev/null
  fi
  echo "Listo. Los servicios en producción deben leerlo (ej. vía External Secrets"
  echo "Operator en K8s — ver deploy/k8s/*-external-secret.yaml) en vez de tener"
  echo "estos valores como variables de entorno planas en el manifiesto."
}

publish_to_vault() {
  command -v vault >/dev/null 2>&1 || { echo "ERROR: falta instalar/configurar el CLI de Vault (vault login)." >&2; exit 1; }

  echo "Publicando en Vault en '$VAULT_PATH'..."
  vault kv put "$VAULT_PATH" \
    ERP_SECRET_KEY="$ERP_SECRET_KEY" \
    AI_AGENTS_INTERNAL_KEY="$AI_AGENTS_INTERNAL_KEY" >/dev/null
  echo "Listo. Los pods deben montar esto vía el Vault Agent Injector o el CSI"
  echo "Secrets Store Driver (ver deploy/k8s/*-secretproviderclass.yaml), no"
  echo "copiando el valor a mano al manifiesto."
}

if [[ "$ROTATE" == true && "$BACKEND" == "none" ]]; then
  echo "ERROR: --rotate requiere --backend aws-secrets-manager o --backend vault" >&2
  exit 1
fi

case "$BACKEND" in
  none) : ;;
  aws-secrets-manager) publish_to_aws_secrets_manager ;;
  vault) publish_to_vault ;;
  *) echo "ERROR: --backend debe ser 'aws-secrets-manager', 'vault', o omitirse." >&2; exit 1 ;;
esac
