@echo off
title TRACE_PD — Personal Behavior Debugger
echo.
echo  ████████╗██████╗  █████╗  ██████╗███████╗    ██████╗ ██████╗
echo  ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██╔════╝    ██╔══██╗██╔══██╗
echo     ██║   ██████╔╝███████║██║     █████╗      ██████╔╝██║  ██║
echo     ██║   ██╔══██╗██╔══██║██║     ██╔══╝      ██╔═══╝ ██║  ██║
echo     ██║   ██║  ██║██║  ██║╚██████╗███████╗    ██║     ██████╔╝
echo     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝    ╚═╝     ╚═════╝
echo.
echo  Personal Behavior Debugger
echo  Containers: trcpd_db, trcpd_backend, trcpd_frontend, trcpd_nginx
echo.
echo  Checking Docker...
docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo  ERROR: Docker Desktop not found.
    echo  Install from https://docker.com/products/docker-desktop
    pause
    exit /b 1
)
echo  Docker found. Starting all services...
echo.
echo  After startup:
echo    Frontend  : http://localhost:13000
echo    API Docs  : http://localhost:18000/docs
echo    Nginx     : http://localhost:10080  ^(recommended^)
echo    PostgreSQL: localhost:15432
echo.
echo  Demo login: demo@trace.dev  /  demo1234
echo.
docker compose up --build
pause
