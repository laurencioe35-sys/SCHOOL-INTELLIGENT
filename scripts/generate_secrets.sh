#!/usr/bin/env bash
# Genera un ERP_SECRET_KEY real y fuerte para desarrollo local.
#
# TRANSPARENCIA: este script SOLO puede generar el secreto que es
# puramente interno (la llave HMAC de nuestros propios tokens). NO puede
# generar ni inventar:
#   - Credenciales de FaceIO (requieren una cuenta real en faceio.net)
#   - API keys de Anthropic (requieren una cuenta real en console.anthropic.com)
#   - Credenciales de la pasarela de pago (Culqi/Niubiz/MercadoPago) —
#     requieren una cuenta de comercio real, verificada, con RUC.
# Cualquier archivo que dijera tener esos valores "reales" sin que
# existan esas cuentas sería simplemente inventado — por eso este script
# solo resuelve la parte que sí depende únicamente de nosotros.

set -euo pipefail

SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")

echo "ERP_SECRET_KEY generado (cópialo a tu .env):"
echo ""
echo "ERP_SECRET_KEY=$SECRET"
echo ""
echo "Recuerda: multimedia-stream-server/.env debe tener EXACTAMENTE el"
echo "mismo valor, porque el servidor CRDT verifica los tokens del ERP"
echo "con esta misma llave (ver multimedia-stream-server/state/auth.ts)."
