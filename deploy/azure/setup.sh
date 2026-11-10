#!/usr/bin/env bash
# One-time creation of the TripAura backend on Azure Container Apps.
# Run it in Azure Cloud Shell (portal.azure.com -> the >_ icon -> Bash). Nothing to install.
#
#   curl -fsSL https://raw.githubusercontent.com/ranjanvrma/trip-aura/main/deploy/azure/setup.sh -o setup.sh
#   bash setup.sh
#
# Prerequisite: the image ghcr.io/<owner>/trip-aura-api:latest exists and is Public
# (pushed by .github/workflows/deploy-backend-azure.yml).
#
# Creates: resource group, Container Apps environment (no paid log workspace), and the container
# app (1 vCPU / 2 GiB, scales to zero, max 1 replica). Prints the backend URL and the
# AZURE_CREDENTIALS JSON for GitHub so later pushes deploy automatically.
set -euo pipefail

OWNER="${OWNER:-ranjanvrma}"
IMAGE="${IMAGE:-ghcr.io/${OWNER}/trip-aura-api:latest}"
RG="${RG:-trip-aura}"
LOCATION="${LOCATION:-eastus}"          # near Neon's AWS us-east-1; change if your subscription disallows it
ENV_NAME="${ENV_NAME:-trip-aura-env}"
APP="${APP:-trip-aura-api}"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

read -rp "Neon DATABASE_URL (paste): " DATABASE_URL
read -rp "Vercel URL, e.g. https://trip-aura-cr.vercel.app (Enter to set later): " CORS
CORS="${CORS:-http://localhost:5173}"
CORS="${CORS%/}"

say "Registering Azure providers (first time only, ~1-2 min)"
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az extension add --name containerapp --upgrade --only-show-errors

# Azure for Students subscriptions only allow a few regions ("RequestDisallowedByAzure").
# Read the allowed list from the subscription's policy and pick one if LOCATION isn't allowed.
ALLOWED="$(az policy assignment list --disable-scope-strict-match \
  --query "[].parameters.listOfAllowedLocations.value[]" --output tsv 2>/dev/null | sort -u | tr '\n' ' ')"
if [ -n "$ALLOWED" ]; then
  echo "Regions allowed for this subscription: $ALLOWED"
  if ! printf ' %s ' "$ALLOWED" | grep -q " ${LOCATION} "; then
    for pref in eastus eastus2 centralus westus2 northcentralus southcentralus canadacentral \
                centralindia southindia westindia uksouth westeurope northeurope \
                southeastasia eastasia koreacentral japaneast australiaeast; do
      if printf ' %s ' "$ALLOWED" | grep -q " ${pref} "; then LOCATION="$pref"; break; fi
    done
    if ! printf ' %s ' "$ALLOWED" | grep -q " ${LOCATION} "; then
      LOCATION="$(printf '%s' "$ALLOWED" | awk '{print $1}')"
    fi
  fi
fi
echo "Using region: $LOCATION"

if az group show --name "$RG" --output none 2>/dev/null; then
  say "Using existing resource group $RG"   # its own location doesn't matter for the resources inside
else
  say "Creating resource group $RG in $LOCATION"
  az group create --name "$RG" --location "$LOCATION" --output none
fi

say "Creating Container Apps environment (logs to console only, no paid workspace)"
az containerapp env create --name "$ENV_NAME" --resource-group "$RG" --location "$LOCATION" \
  --logs-destination none --output none

say "Creating the backend app from $IMAGE (pulling a ~1.5 GB image takes a few minutes)"
az containerapp create --name "$APP" --resource-group "$RG" --environment "$ENV_NAME" \
  --image "$IMAGE" --target-port 7860 --ingress external \
  --cpu 1.0 --memory 2.0Gi --min-replicas 0 --max-replicas 1 \
  --secrets "database-url=${DATABASE_URL}" \
  --env-vars "DATABASE_URL=secretref:database-url" "DATA_MODE=open" \
             "CORS_ORIGINS=${CORS}" "CORS_ORIGIN_REGEX=https://trip-aura-.*\\.vercel\\.app" \
             "OPEN_USER_AGENT=TripAura/1.0 (+https://github.com/${OWNER}/trip-aura)" \
  --output none

URL="https://$(az containerapp show --name "$APP" --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn --output tsv)"

say "Creating deploy credentials for GitHub Actions (scoped to resource group $RG only)"
SUB="$(az account show --query id --output tsv)"
CREDS="$(az ad sp create-for-rbac --name "trip-aura-github" --role contributor \
  --scopes "/subscriptions/${SUB}/resourceGroups/${RG}" --json-auth --only-show-errors)"

cat <<EOF

=====================================================================
Backend URL:   ${URL}
  health:      ${URL}/api/health   (first request wakes it up: ~30-60 s)
  API docs:    ${URL}/docs

Next:
 1. Vercel -> env var VITE_API_BASE_URL = ${URL}
 2. GitHub -> Settings -> Secrets and variables -> Actions
      secret   AZURE_CREDENTIALS = the JSON below (copy all of it)
      variable AZURE_ENABLED     = true
 3. When you know the Vercel URL:
      az containerapp update -n ${APP} -g ${RG} --set-env-vars CORS_ORIGINS=https://trip-aura-cr.vercel.app
=====================================================================
${CREDS}
EOF
