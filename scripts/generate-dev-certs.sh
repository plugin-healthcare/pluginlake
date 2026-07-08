#!/usr/bin/env bash
# Generate self-signed TLS certificates for pluginlake dev.
# Creates a CA + wildcard cert for *.localhost domains.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)/../.data/traefik/certs"
mkdir -p "$DIR"

if [ -f "$DIR/ca.pem" ] && [ -f "$DIR/wildcard.pem" ]; then
  echo "Certificates already exist in $DIR/"
  echo "Delete the directory to regenerate: rm -rf $DIR"
  exit 0
fi

echo "Generating CA..."
openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout "$DIR/ca.key" -out "$DIR/ca.pem" -days 825 \
  -subj "/CN=pluginlake-dev-ca" 2>/dev/null

echo "Generating wildcard cert for *.localhost..."
openssl req -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout "$DIR/wildcard.key" -out "$DIR/wildcard.csr" \
  -subj "/CN=localhost" 2>/dev/null

openssl x509 -req -in "$DIR/wildcard.csr" -CA "$DIR/ca.pem" -CAkey "$DIR/ca.key" \
  -CAcreateserial -out "$DIR/wildcard.pem" -days 825 \
  -extfile <(printf "subjectAltName=DNS:localhost,DNS:*.localhost,DNS:nuts-hub.localhost,DNS:nuts-station.localhost") 2>/dev/null

rm -f "$DIR/wildcard.csr" "$DIR/ca.srl"

echo "✅ Certificates generated:"
echo "   CA:   $DIR/ca.pem"
echo "   Cert: $DIR/wildcard.pem"
echo "   Key:  $DIR/wildcard.key"
echo ""
echo "To trust the CA locally (optional, avoids browser warnings):"
echo "   sudo cp $DIR/ca.pem /usr/local/share/ca-certificates/pluginlake-dev.crt"
echo "   sudo update-ca-certificates"
