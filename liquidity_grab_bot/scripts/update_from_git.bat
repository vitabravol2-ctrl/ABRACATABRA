@echo off
cd /d %~dp0\..
set ENV_EXISTS=0
if exist .env (
  copy /Y .env .env.backup >nul
  set ENV_EXISTS=1
)

git fetch --all
git reset --hard origin/main
git clean -fd -e .env -e .env.backup

if %ENV_EXISTS%==1 (
  if exist .env.backup (
    copy /Y .env.backup .env >nul
    del .env.backup >nul
  )
)

echo UPDATED
pause
