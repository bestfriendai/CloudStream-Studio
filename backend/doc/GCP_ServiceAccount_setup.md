# GCP 服務帳號設置
## 1.創建 GCP 專案
    1. 前往 Google Cloud Console
    2. 點擊「選取專案」→「新增專案」
    3. 輸入專案名稱（例如：cloudstream-studio）
    4. 記下專案 ID（例如：cloudstream-studio-12345）
## 2. 啟用必要的 API
    1.設置專案 ID
    ```shellscript
    export PROJECT_ID="your-project-id"
    
    # 啟用 Cloud Storage API
    gcloud services enable storage-api.googleapis.com --project=$PROJECT_ID
    ```
或在 API 庫 中手動啟用：
- Cloud Storage API


## 3. 創建服務帳號
    方法 1: 使用 gcloud CLI
    ```shellscript
    # 設置變數
    export PROJECT_ID="your-project-id"
    export SERVICE_ACCOUNT_NAME="cloudstream-sa"
    export SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

    # 創建服務帳號
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="CloudStream Studio Service Account" \
        --project=$PROJECT_ID

    # 授予必要權限
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/storage.admin"

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role="roles/speech.admin"

    # 創建並下載金鑰
    gcloud iam service-accounts keys create service-account-key.json \
        --iam-account=$SERVICE_ACCOUNT_EMAIL \
        --project=$PROJECT_ID

    echo "✓ 服務帳號金鑰已創建: service-account-key.json"
    ```
    方法 2: 使用 Web Console
    - 前往 IAM & Admin
    - 訪問：https://console.cloud.google.com/iam-admin/serviceaccounts
    - 選擇你的專案
    - 創建服務帳號
    - 點擊「+ 建立服務帳號」
      - 服務帳號名稱：cloudstream-sa
      - 服務帳號 ID：cloudstream-sa
      - 描述：CloudStream Studio Service Account
      - 點擊「建立並繼續」
      - 授予角色
      - 選擇角色：Storage Admin
      - 點擊「繼續」
      - 創建金鑰
      - 點擊「完成」
    - 在服務帳號列表中，找到剛創建的帳號
    - 點擊右側的「⋮」→「管理金鑰」
      - 點擊「新增金鑰」→「建立新金鑰」
      - 選擇「JSON」格式
      - 點擊「建立」
      - 金鑰會自動下載為 your-project-id-xxxxx.json
## 4. 放置服務帳號金鑰
   創建 credentials 目錄(在backend目錄)
   ```
   mkdir -p credentials
   ```
   移動金鑰文件（根據你的實際文件名調整）
   ```
   mv ~/Downloads/your-project-id-xxxxx.json credentials/service-account-key.json
   ```
   或者重命名已下載的金鑰
   ```
   mv service-account-key.json credentials/service-account-key.json
   ```
   設置權限（僅所有者可讀）
   ```
   chmod 600 credentials/service-account-key.json
   ```
   驗證文件
    ```
    ls -la credentials/
    ```
## 5. 創建 Cloud Storage Bucket
   設置變數
   ```
   export PROJECT_ID="your-project-id"
   export BUCKET_NAME="cloudstream-studio-bucket"
   export REGION="asia-east1"  # 或選擇其他區域
   ```
   創建 Bucket
   ```
   gsutil mb -p $PROJECT_ID -l $REGION gs://$BUCKET_NAME/
   ```
   設置 CORS（允許前端訪問）
   ```
   cat > cors.json << EOF
   [
     {
       "origin": ["http://localhost:3000", "http://   localhost"],
       "method": ["GET", "POST", "PUT", "DELETE"],
       "responseHeader": ["Content-Type"],
       "maxAgeSeconds": 3600
     }
   ]
   EOF
   
   gsutil cors set cors.json gs://$BUCKET_NAME/
   rm cors.json
   ```
   驗證 Bucket
   ```
   gsutil ls -p $PROJECT_ID
   echo "✓ Bucket 已創建: gs://$BUCKET_NAME/"
   ```