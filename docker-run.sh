docker run -d \
  --name cloudstream-studio \
  -p 80:80 \
  -e GCP_PROJECT_ID=dh-veo3-ai \
  -e GCS_BUCKET_NAME=dh-dreamer-v \
  -v $(pwd)/backend/credentials/credentials.json:/app/credentials/service-account-key.json:ro \
  cloudstream:latest
