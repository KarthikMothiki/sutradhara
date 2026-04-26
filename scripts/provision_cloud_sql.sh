#!/bin/bash

# Exit on error
set -e

echo "🚀 Provisioning Google Cloud SQL (PostgreSQL)..."

# Configuration
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
INSTANCE_NAME="sutradhara-db-instance"
DB_NAME="sutradharadb"
DB_USER="sutradhara"

# Generate a strong random password
DB_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)

echo "📌 Project ID: $PROJECT_ID"
echo "📌 Region: $REGION"
echo "📌 Instance Name: $INSTANCE_NAME"

# Enable Cloud SQL Admin API
gcloud services enable sqladmin.googleapis.com

# Create the Cloud SQL Instance
# Using db-f1-micro to stay well within the $100 budget
echo "⏳ Creating Cloud SQL instance (this will take 5-10 minutes)..."
gcloud sql instances create $INSTANCE_NAME \
    --database-version=POSTGRES_15 \
    --cpu=1 \
    --memory=3840MiB \
    --region=$REGION \
    --project=$PROJECT_ID \
    --edition=ENTERPRISE \
    --availability-type=zonal

# Create the database
echo "⏳ Creating database '$DB_NAME'..."
gcloud sql databases create $DB_NAME \
    --instance=$INSTANCE_NAME \
    --project=$PROJECT_ID

# Create the user
echo "⏳ Creating database user '$DB_USER'..."
gcloud sql users create $DB_USER \
    --instance=$INSTANCE_NAME \
    --password=$DB_PASSWORD \
    --project=$PROJECT_ID

# Output the connection details
echo "✅ Cloud SQL Provisioning Complete!"
echo "----------------------------------------------------"
echo "Instance Connection Name: $PROJECT_ID:$REGION:$INSTANCE_NAME"
echo "Database Name: $DB_NAME"
echo "Database User: $DB_USER"
echo "Database Password: $DB_PASSWORD"
echo "----------------------------------------------------"
echo "⚠️ IMPORTANT: Save this password somewhere safe! You will need it for deployment."
echo "The DATABASE_URL for Cloud Run will be:"
echo "postgresql+asyncpg://$DB_USER:$DB_PASSWORD@/$DB_NAME?host=/cloudsql/$PROJECT_ID:$REGION:$INSTANCE_NAME"
