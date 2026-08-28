@echo off
rem Real AI Model Studio — ワンクリック起動 (Windows)
rem 前提: Docker Desktop がインストール済みで起動していること。
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Real AI Model Studio を起動します
echo ============================================

rem ZIPを展開せずに実行すると、この bat だけが一時フォルダにコピーされて
rem 他のファイルが見えない。まずそれを検出して案内する。
if not exist "docker-compose.yml" (
  echo.
  echo [!] 必要なファイルが見つかりません。
  echo     ZIP を「展開（解凍）」せずに、ZIPの中から直接実行していませんか？
  echo.
  echo     1. ダウンロードした ZIP ファイルを右クリック →「すべて展開」
  echo     2. 展開してできたフォルダを開き、real-ai-model-studio フォルダの中の
  echo        start-windows をダブルクリックしてください
  pause
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Docker Desktop が見つかりません。
  echo     ブラウザでダウンロードページを開きます。インストール後、
  echo     Docker Desktop を起動してから、もう一度このファイルをダブルクリックしてください。
  start https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo.
  echo [!] Docker Desktop がまだ起動していません。
  echo     クジラのアイコンが Running になってから、もう一度このファイルをダブルクリックしてください。
  pause
  exit /b 1
)

echo.
echo ビルドと起動を行います。初回は5〜15分かかります。
echo この画面には途中経過が出ませんが、動いています。そのままお待ちください...
echo （経過の記録は同じフォルダの setup-log.txt に保存されます）
docker compose up -d --build > setup-log.txt 2>&1
if errorlevel 1 (
  echo.
  echo [!] 起動に失敗しました。原因の記録（setup-log.txt）をメモ帳で開きます。
  echo     メモ帳の中身を全部コピーして（Ctrl+A → Ctrl+C）、Claude に貼り付けてください。
  start notepad setup-log.txt
  pause
  exit /b 1
)

echo.
echo 画面が開くまで待機しています...
set /a tries=0
:waitloop
set /a tries+=1
curl -s -o nul http://localhost:3000 2>nul
if not errorlevel 1 goto ready
if %tries% geq 60 goto timeout
timeout /t 3 /nobreak >nul
goto waitloop

:ready
echo.
echo ============================================
echo  起動しました！ ブラウザを開きます。
echo  もし開かなければ、ブラウザのアドレス欄に localhost:3000 と入力してください。
echo  ログイン: admin@example.com / ChangeMe123!
echo  （ログイン後にパスワードを変更してください）
echo ============================================
start http://localhost:3000
pause
exit /b 0

:timeout
echo.
echo [!] 起動待ちがタイムアウトしました。状況の記録をメモ帳で開きます。
echo     メモ帳の中身を全部コピーして（Ctrl+A → Ctrl+C）、Claude に貼り付けてください。
docker compose ps >> setup-log.txt 2>&1
docker compose logs api --tail 50 >> setup-log.txt 2>&1
start notepad setup-log.txt
pause
exit /b 1
