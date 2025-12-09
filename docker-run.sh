docker run -d \
  --name cloudstream-studio \
  -p 80:80 \
  -e GCS_BUCKET_NAME="your-bucket-name" \
  -e GCP_PROJECT_ID="your-project" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/app/credentials/application_default_credentials.json" \
  -v ~/.config/gcloud/application_default_credentials.json:/app/credentials/application_default_credentials.json:ro \
  cloudstream:latest
