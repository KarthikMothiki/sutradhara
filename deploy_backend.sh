#!/bin/bash

# Exit on error
set -e

echo "🚀 Deploying Sūtradhāra Backend to Google Cloud Run..."

# Set your variables
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="sutradhara-agent"

# Option 2: Production Deploy (Cloud SQL PostgreSQL)
# This deploys the container and connects it to the managed PostgreSQL database.
# We set max-instances to 3 to handle concurrent requests while staying within the $100 budget.

INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:sutradhara-db-instance"

echo "⏳ Please ensure you have run scripts/provision_cloud_sql.sh first!"
read -p "Enter the DATABASE_URL (postgresql+asyncpg://...): " DB_URL

gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --max-instances 3 \
  --memory 512Mi \
  --cpu 1 \
  --add-cloudsql-instances $INSTANCE_CONNECTION_NAME \
  --set-env-vars="LOG_LEVEL=info,DATABASE_URL=$DB_URL"

echo "✅ Deployment successful!"
echo "⚠️  Important: Copy the deployed service URL and paste it into frontend/app.js (CLOUD_RUN_URL variable) before pushing to GitHub."
