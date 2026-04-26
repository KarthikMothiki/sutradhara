#!/bin/bash

# Exit on error
set -e

echo "💸 Setting up GCP Budget Management (\$100 Limit)..."

PROJECT_ID=$(gcloud config get-value project)
BILLING_ACCOUNT=$(gcloud beta billing projects describe $PROJECT_ID --format="value(billingAccountName)" | cut -d'/' -f2)

if [ -z "$BILLING_ACCOUNT" ]; then
    echo "❌ Error: Could not determine billing account for project $PROJECT_ID."
    echo "Make sure billing is enabled for this project."
    exit 1
fi

echo "📌 Project ID: $PROJECT_ID"
echo "📌 Billing Account: $BILLING_ACCOUNT"

# Enable Billing API
gcloud services enable billingbudgets.googleapis.com

# Create the budget
echo "⏳ Creating \$100 budget alert..."
gcloud beta billing budgets create \
    --billing-account=$BILLING_ACCOUNT \
    --display-name="Sutradhara Sprint Budget" \
    --budget-amount=100 \
    --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.8 \
    --threshold-rule=percent=1.0 \
    --filter-projects=projects/$PROJECT_ID

echo "✅ GCP Budget Management Configured!"
echo "Alerts will be sent at 50% (\$50), 80% (\$80), and 100% (\$100)."
