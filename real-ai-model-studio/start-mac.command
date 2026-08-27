#!/bin/bash
# Real AI Model Studio — ワンクリック起動 (Mac)
# 前提: Docker Desktop がインストール済みで起動していること。
# 初回は Finder で右クリック →「開く」で起動してください（Gatekeeper対策）。
cd "$(dirname "$0")"

echo "============================================"
echo " Real AI Model Studio を起動します"
echo "============================================"

if ! command -v docker >/dev/null 2>&1; then
  echo ""
  echo "[!] Docker Desktop が見つかりません。"
  echo "    ブラウザでダウンロードページを開きます。インストール後、"
  echo "    Docker Desktop を起動してから、もう一度このファイルを開いてください。"
  open "https://www.docker.com/products/docker-desktop/"
  read -r -p "Enterキーで閉じます..."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo ""
  echo "[!] Docker Desktop がまだ起動していません。"
  echo "    クジラのアイコンが Running になってから、もう一度このファイルを開いてください。"
  read -r -p "Enterキーで閉じます..."
  exit 1
fi

echo ""
echo "ビルドと起動を行います（初回は5〜15分かかります。そのままお待ちください）..."
if ! docker compose up -d --build; then
  echo ""
  echo "[!] 起動に失敗しました。上に表示されたエラーをコピーして Claude に貼り付けてください。"
  read -r -p "Enterキーで閉じます..."
  exit 1
fi

echo ""
echo "画面が開くまで待機しています..."
for _ in $(seq 1 60); do
  if curl -s -o /dev/null http://localhost:3000; then
    echo ""
    echo "============================================"
    echo " 起動しました！ ブラウザを開きます。"
    echo " ログイン: admin@example.com / ChangeMe123!"
    echo " （ログイン後にパスワードを変更してください）"
    echo "============================================"
    open "http://localhost:3000"
    read -r -p "Enterキーで閉じます..."
    exit 0
  fi
  sleep 3
done

echo ""
echo "[!] 起動待ちがタイムアウトしました。少し待ってからブラウザで"
echo "    http://localhost:3000 を開いてみてください。"
echo "    開けない場合は、この画面の内容をコピーして Claude に貼り付けてください。"
docker compose ps
read -r -p "Enterキーで閉じます..."
exit 1
