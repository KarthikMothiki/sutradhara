#!/bin/bash

# Exit on error
set -e

echo "🚀 Deploying Project Sūtradhāra to Google Cloud Run..."

# 1. Configuration
PROJECT_ID=$(gcloud config get-value project)
SERVICE_NAME="sutradhara-backend"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "📌 Project ID: $PROJECT_ID"
echo "📌 Service: $SERVICE_NAME"
echo "📌 Region: $REGION"

# 2. Build and Push to Google Container Registry
echo "⏳ Building and pushing Docker image..."
gcloud builds submit --tag $IMAGE_NAME .

# 3. Deploy to Cloud Run
echo "⏳ Deploying to Cloud Run..."

# Note: We assume Cloud SQL is already provisioned and DATABASE_URL is set as an env var
# Or you can pass secrets/env vars here
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --project $PROJECT_ID \
    --add-cloudsql-instances "$PROJECT_ID:$REGION:sutradhara-db-instance" \
    --update-env-vars "DEMO_MODE=false"

echo "✅ Deployment Successful!"
echo "----------------------------------------------------"
gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)'
echo "----------------------------------------------------"
