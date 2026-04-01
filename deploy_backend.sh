#!/bin/bash

# Exit on error
set -e

echo "🚀 Deploying Sūtradhāra Backend to Google Cloud Run..."

# Set your variables
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="sutradhara-agent"

# Option 1: Standard Free Tier Deploy (Ephemeral Database)
# This deploys the container. The local SQLite database will be reset
# anytime the container goes to sleep (scales to 0).
# We use --max-instances 1 to prevent multiple containers from causing SQLite lock issues.
gcloud run deploy $SERVICE_NAME \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --max-instances 1 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars="LOG_LEVEL=info"

echo "✅ Deployment successful!"
echo "⚠️  Important: Copy the deployed service URL and paste it into frontend/app.js (CLOUD_RUN_URL variable) before pushing to GitHub."
