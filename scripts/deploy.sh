#!/bin/bash

# ====================================================
# Green Moment Backend V2 - Deployment Script
# ====================================================

# 1. Configuration
PROJECT_ID="greenm02"
REGION="asia-east1"
SERVICE_NAME="gm-backend-v2"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
# Service Account matches what we verified in security.py
SERVICE_ACCOUNT="gm-backend-v2-identity@$PROJECT_ID.iam.gserviceaccount.com"

echo "🚀 Starting Deployment for $SERVICE_NAME..."

# 2. Build Container using Cloud Build
echo "⏳ Building Container on Cloud Build..."
# We use . (current directory) as context, assuming script is run from project root 
# OR we need to adjust. Standard practice is to run from root: ./scripts/deploy.sh
gcloud builds submit --tag $IMAGE_NAME --project $PROJECT_ID

if [ $? -ne 0 ]; then
    echo "❌ Build Failed."
    exit 1
fi

# 3. Deploy to Cloud Run
# --allow-unauthenticated is REQUIRED for the Mobile App to reach it (we handle security in app code)
echo "⏳ Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --platform managed \
    --region $REGION \
    --project $PROJECT_ID \
    --allow-unauthenticated \
    --service-account $SERVICE_ACCOUNT \
    --cpu 1 \
    --memory 2Gi \
    --min-instances 0 \
    --max-instances 3 \
    --concurrency 80

if [ $? -ne 0 ]; then
    echo "❌ Deployment Failed."
    exit 1
fi

echo "✅ Deployment Success!"
echo "🌍 Service URL:"
gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)'

echo ""
echo "👉 NEXT STEP: Go to Cloud Scheduler and update your job to hit this new URL:"
echo "   Endpoint: <URL>/internal/update-forecast"
echo "   Auth: OIDC Token (Service Account: $SERVICE_ACCOUNT)"
