#!/usr/bin/env bash
# Bootstrap script for the two-node Nuts integration test network.
#
# This script:
# 1. Creates a subject (DID) on each node
# 2. Issues a NutsOrganizationCredential to each
# 3. Loads credentials into wallets
# 4. Registers both at the discovery service
# 5. Verifies they can discover each other
#
# Prerequisites:
#   docker compose up -d   (from this directory)
#   Both nuts nodes healthy (ports 8081 and 9081)

set -euo pipefail

HUB_INTERNAL="http://127.0.0.1:8081"
STATION_INTERNAL="http://127.0.0.1:9081"

echo "=== Nuts Network Bootstrap ==="
echo ""

# Wait for nodes
echo "⏳ Waiting for nuts-hub..."
until curl -sf "$HUB_INTERNAL/status" > /dev/null 2>&1; do sleep 1; done
echo "⏳ Waiting for nuts-station..."
until curl -sf "$STATION_INTERNAL/status" > /dev/null 2>&1; do sleep 1; done
echo "✅ Both nodes are healthy"
echo ""

# --- Hub ---
echo "--- Hub Setup ---"

# Create subject
HUB_RESPONSE=$(curl -sf "$HUB_INTERNAL/internal/vdr/v2/subject" -X POST \
  -H "Content-Type: application/json" -d '{}')
HUB_SUBJECT=$(echo "$HUB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['subject'])")
HUB_DID=$(echo "$HUB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['documents'][0]['id'])")
echo "  Subject: $HUB_SUBJECT"
echo "  DID:     $HUB_DID"

# Add OAuth service endpoint to DID document
curl -sf "$HUB_INTERNAL/internal/vdr/v2/subject/$HUB_SUBJECT/service" -X POST \
  -H "Content-Type: application/json" \
  -d "{\"type\": \"oauth\", \"serviceEndpoint\": \"https://nuts-hub.localhost/oauth2/$HUB_SUBJECT\"}" -o /dev/null
echo "  OAuth service added ✅"

# Issue credential
HUB_VC=$(curl -sf "$HUB_INTERNAL/internal/vcr/v2/issuer/vc" -X POST \
  -H "Content-Type: application/json" \
  -d "{
    \"issuer\": \"$HUB_DID\",
    \"type\": \"NutsOrganizationCredential\",
    \"credentialSubject\": {
      \"id\": \"$HUB_DID\",
      \"organization\": {
        \"name\": \"PLUGIN Research Hub\",
        \"city\": \"Utrecht\"
      }
    },
    \"withStatusList2021Revocation\": false,
    \"expirationDate\": \"2027-01-01T00:00:00Z\"
  }")
echo "  Credential issued ✅"

# Load into wallet
curl -sf "$HUB_INTERNAL/internal/vcr/v2/holder/$HUB_SUBJECT/vc" -X POST \
  -H "Content-Type: application/json" -d "$HUB_VC" -o /dev/null
echo "  Wallet loaded ✅"

# Register at discovery
DISC_RESULT=$(curl -s -w "\n%{http_code}" "$HUB_INTERNAL/internal/discovery/v1/pluginlake-network/$HUB_SUBJECT" \
  -X POST -H "Content-Type: application/json" -d '{}')
DISC_CODE=$(echo "$DISC_RESULT" | tail -1)
if [ "$DISC_CODE" = "200" ] || [ "$DISC_CODE" = "201" ] || [ "$DISC_CODE" = "204" ]; then
  echo "  Discovery registered ✅"
else
  echo "  Discovery registration: HTTP $DISC_CODE"
  echo "$DISC_RESULT" | head -1
fi
echo ""

# --- Station ---
echo "--- Station Setup ---"

# Create subject
STATION_RESPONSE=$(curl -sf "$STATION_INTERNAL/internal/vdr/v2/subject" -X POST \
  -H "Content-Type: application/json" -d '{}')
STATION_SUBJECT=$(echo "$STATION_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['subject'])")
STATION_DID=$(echo "$STATION_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['documents'][0]['id'])")
echo "  Subject: $STATION_SUBJECT"
echo "  DID:     $STATION_DID"

# Add OAuth service endpoint to DID document
curl -sf "$STATION_INTERNAL/internal/vdr/v2/subject/$STATION_SUBJECT/service" -X POST \
  -H "Content-Type: application/json" \
  -d "{\"type\": \"oauth\", \"serviceEndpoint\": \"https://nuts-station.localhost/oauth2/$STATION_SUBJECT\"}" -o /dev/null
echo "  OAuth service added ✅"

# Issue credential
STATION_VC=$(curl -sf "$STATION_INTERNAL/internal/vcr/v2/issuer/vc" -X POST \
  -H "Content-Type: application/json" \
  -d "{
    \"issuer\": \"$STATION_DID\",
    \"type\": \"NutsOrganizationCredential\",
    \"credentialSubject\": {
      \"id\": \"$STATION_DID\",
      \"organization\": {
        \"name\": \"Demo Ziekenhuis Amsterdam\",
        \"city\": \"Amsterdam\"
      }
    },
    \"withStatusList2021Revocation\": false,
    \"expirationDate\": \"2027-01-01T00:00:00Z\"
  }")
echo "  Credential issued ✅"

# Load into wallet
curl -sf "$STATION_INTERNAL/internal/vcr/v2/holder/$STATION_SUBJECT/vc" -X POST \
  -H "Content-Type: application/json" -d "$STATION_VC" -o /dev/null
echo "  Wallet loaded ✅"

# Register at discovery (station contacts hub's discovery server)
DISC_RESULT=$(curl -s -w "\n%{http_code}" "$STATION_INTERNAL/internal/discovery/v1/pluginlake-network/$STATION_SUBJECT" \
  -X POST -H "Content-Type: application/json" -d '{}')
DISC_CODE=$(echo "$DISC_RESULT" | tail -1)
if [ "$DISC_CODE" = "200" ] || [ "$DISC_CODE" = "201" ] || [ "$DISC_CODE" = "204" ]; then
  echo "  Discovery registered ✅"
else
  echo "  Discovery registration: HTTP $DISC_CODE"
  echo "$DISC_RESULT" | head -1
fi
echo ""

# --- Verify discovery ---
echo "--- Discovery Verification ---"
sleep 2

SEARCH=$(curl -sf "$HUB_INTERNAL/internal/discovery/v1/pluginlake-network?credentialSubject.organization.city=*")
COUNT=$(echo "$SEARCH" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "  Nodes found in network: $COUNT"

if [ "$COUNT" -ge 2 ]; then
  echo "  ✅ Both nodes discovered each other!"
else
  echo "  ⚠️  Expected 2 nodes, found $COUNT. Check logs:"
  echo "    docker compose logs nuts-hub nuts-station"
  exit 1
fi
echo ""

# --- Token exchange ---
echo "--- Token Exchange (Hub → Station) ---"

# Get station's OAuth AS URL from discovery
STATION_AUTH_SERVER=$(echo "$SEARCH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for entry in data:
    if 'nuts-station' in entry['credential_subject_id']:
        print(entry['registrationParameters']['authServerURL'])
        break
")
echo "  Station auth server: $STATION_AUTH_SERVER"

# Request access token from hub's node to station's authorization server
TOKEN_RESPONSE=$(curl -sf -X POST "$HUB_INTERNAL/internal/auth/v2/$HUB_SUBJECT/request-service-access-token" \
  -H "Content-Type: application/json" \
  -d "{\"authorization_server\": \"$STATION_AUTH_SERVER\", \"scope\": \"pluginlake-data-access\"}")
ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
TOKEN_TYPE=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token_type'])")
echo "  Token type: $TOKEN_TYPE"
echo "  Access token: ${ACCESS_TOKEN:0:20}..."

# Introspect the token on the station to verify it's valid
INTROSPECT=$(curl -sf -X POST "$STATION_INTERNAL/internal/auth/v2/accesstoken/introspect" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$ACCESS_TOKEN")
ACTIVE=$(echo "$INTROSPECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['active'])")
CLIENT_ID=$(echo "$INTROSPECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['client_id'])")
ORG_NAME=$(echo "$INTROSPECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['organization_name'])")

if [ "$ACTIVE" = "True" ]; then
  echo "  ✅ Token is active!"
  echo "  Client: $CLIENT_ID"
  echo "  Organization: $ORG_NAME"
else
  echo "  ❌ Token introspection failed (active=$ACTIVE)"
  exit 1
fi
echo ""

echo "=== All checks passed ✅ ==="
echo ""
echo "  Hub DID:     $HUB_DID"
echo "  Station DID: $STATION_DID"
echo "  Hub subject: $HUB_SUBJECT"
echo "  Station subject: $STATION_SUBJECT"
