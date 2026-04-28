#!/bin/bash

# Exit on error
set -e

# Deploy Sūtradhāra to Cloud Run with Cloud SQL integration
# Uses --env-vars-file (YAML) to safely handle values with commas/special chars
# -------------------------------------------------------

# Configuration
PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="sutradhara-backend"
REGION="us-central1"
REPO="sutradhara-repo"
IMAGE_NAME="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$SERVICE_NAME"
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:sutradhara-db-instance"
DB_USER="sutradhara"
DB_PASS="sutradharapassword"
DB_NAME="sutradharadb"

# Build DATABASE_URL for Cloud SQL (Unix socket)
DATABASE_URL="postgresql+asyncpg://$DB_USER:$DB_PASS@/$DB_NAME?host=/cloudsql/$INSTANCE_CONNECTION_NAME"

echo "📌 Project ID: $PROJECT_ID"
echo "📌 Service:    $SERVICE_NAME"
echo "📌 Region:     $REGION"
echo "📌 SQL Instance: $INSTANCE_CONNECTION_NAME"
echo "📌 Image:      $IMAGE_NAME"

# Write env vars to a YAML file (safe for commas, brackets, special chars)
ENV_FILE="$(mktemp /tmp/cloudrun-env-XXXXXX.yaml)"
cat > "$ENV_FILE" <<EOF
DATABASE_URL: "$DATABASE_URL"
DEMO_MODE: "true"
EOF

# Helper to append optional vars from .env
add_env_var() {
    local var_name=$1
    if [ -f .env ]; then
        local var_value
        var_value=$(grep "^${var_name}=" .env | cut -d '=' -f2- | tr -d '"' | tr -d "'")
        if [ -n "$var_value" ]; then
            echo "${var_name}: \"${var_value}\"" >> "$ENV_FILE"
        fi
    fi
}

add_env_var "GOOGLE_API_KEY"
# Notion credentials are NOT injected for Cloud Run (Privacy)
# They are passed from the client per-request in Live Mode.
# add_env_var "NOTION_TOKEN"
# add_env_var "NOTION_DATABASE_ID"
add_env_var "MODEL_FALLBACK_CHAIN"
add_env_var "DAILY_BRIEFING_TIME"
add_env_var "WEEKLY_REVIEW_TIME"
add_env_var "WEEKLY_REVIEW_DAY"
add_env_var "LOG_LEVEL"
add_env_var "SCHEDULER_ENABLED"
add_env_var "GOOGLE_CLOUD_PROJECT"
add_env_var "GOOGLE_CLOUD_LOCATION"

echo "📋 Environment vars file: $ENV_FILE"
cat "$ENV_FILE"

# Build and push Docker image
echo "⏳ Building and pushing Docker image..."
gcloud builds submit --tag "$IMAGE_NAME" .

# Deploy to Cloud Run
echo "⏳ Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_NAME" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --project "$PROJECT_ID" \
  --set-cloudsql-instances "$INSTANCE_CONNECTION_NAME" \
  --env-vars-file "$ENV_FILE"

# Cleanup temp file
rm -f "$ENV_FILE"

# Show deployment URL
echo "✅ Deployment Successful!"
echo "----------------------------------------------------"
gcloud run services describe "$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --format 'value(status.url)'
echo "----------------------------------------------------"
