#!/bin/bash
# setup-token.sh - Token 設定助手

set -e

echo "=========================================="
echo "Google Cloud Storage Token 設定"
echo "=========================================="
echo

# 建立必要目錄


# 檢查 credentials
CRED_FILE="./credentials/credentials.json"

if [ ! -f "$CRED_FILE" ]; then
    echo "❌ 找不到 $CRED_FILE"
    echo
    echo "請執行以下步驟："
    echo "=========================================="
    echo "1. 前往 Google Cloud Console:"
    echo "   https://console.cloud.google.com"
    echo
    echo "2. 選擇您的專案"
    echo
    echo "3. 前往 APIs & Services > Credentials"
    echo "   https://console.cloud.google.com/apis/credentials"
    echo
    echo "4. 點擊 'Create Credentials' > 'OAuth 2.0 Client ID'"
    echo
    echo "5. Application type 選擇 'Desktop app'"
    echo "   名稱可以填: CloudStream Manager"
    echo
    echo "6. 點擊 'Create'"
    echo
    echo "7. 下載 JSON 檔案"
    echo "   (檔名通常是 client_secret_xxxxx.json)"
    echo
    echo "8. 將檔案移動並重新命名："
    echo "   mv ~/Downloads/client_secret_*.json $CRED_FILE"
    echo
    echo "=========================================="
    echo
    exit 1
fi

echo "✓ 找到 credentials.json"

# 顯示檔案資訊
echo "檔案位置: $CRED_FILE"
echo "檔案大小: $(du -h $CRED_FILE | cut -f1)"
echo

# 檢查 JSON 格式
if ! python3 -c "import json; json.load(open('$CRED_FILE'))" 2>/dev/null; then
    echo "❌ credentials.json 格式錯誤"
    echo "請確認檔案是有效的 JSON 格式"
    exit 1
fi

echo "✓ JSON 格式正確"

# 檢查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 找不到 Python 3"
    echo "請先安裝 Python 3: https://www.python.org/downloads/"
    exit 1
fi

echo "✓ 找到 Python 3: $(python3 --version)"

# 檢查並安裝依賴
echo
echo "檢查 Python 套件..."

REQUIRED_PACKAGES=(
    "google-auth"
    "google-auth-oauthlib"
    "google-auth-httplib2"
    "google-cloud-storage"
)

MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    package_import="${package//-/_}"
    if python3 -c "import ${package_import}" 2>/dev/null; then
        echo "✓ $package 已安裝"
    else
        echo "⚠️  $package 未安裝"
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo
    echo "安裝缺少的套件..."
    pip3 install "${MISSING_PACKAGES[@]}"
    echo "✓ 套件安裝完成"
fi

# 執行授權
echo
echo "=========================================="
echo "開始 OAuth 授權流程"
echo "=========================================="
echo
echo "瀏覽器將會開啟授權頁面"
echo "請完成以下步驟："
echo "1. 選擇您的 Google 帳號"
echo "2. 點擊 '允許' 授予以下權限："
echo "   - 查看和管理 Google Cloud Storage"
echo "3. 等待授權完成"
echo "4. 看到 'The authentication flow has completed' 後"
echo "   可以關閉瀏覽器視窗"
echo
read -p "按 Enter 繼續..."
# 檢查認證
if [ ! -f "token.pickle" ]; then
    echo ""
    echo "首次執行，需要進行 OAuth 認證..."
    python ./utils/gcs_auth.py
fi
