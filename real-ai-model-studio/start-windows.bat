@echo off
rem Real AI Model Studio — ワンクリック起動 (Windows)
rem 前提: Docker Desktop がインストール済みで起動していること。
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Real AI Model Studio を起動します
echo ============================================

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
echo ビルドと起動を行います（初回は5〜15分かかります。そのままお待ちください）...
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo [!] 起動に失敗しました。上に表示されたエラーをコピーして Claude に貼り付けてください。
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
echo  ログイン: admin@example.com / ChangeMe123!
echo  （ログイン後にパスワードを変更してください）
echo ============================================
start http://localhost:3000
pause
exit /b 0

:timeout
echo.
echo [!] 起動待ちがタイムアウトしました。少し待ってからブラウザで
echo     http://localhost:3000 を開いてみてください。
echo     開けない場合は、この画面の内容をコピーして Claude に貼り付けてください。
docker compose ps
pause
exit /b 1
