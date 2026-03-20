@echo off
echo ==================================================
echo   Le Maison - Auto Start Server ^& Tunnel
echo ==================================================
echo.

:: Start the Flask app in a new window
echo [▶] Starting Flask Server...
start "Flask Server" cmd /c "flask run"

:: Wait a little bit for flask to spin up
timeout /t 3 /nobreak >nul

:: Keep localtunnel alive in this window
echo [▶] Starting LocalTunnel with subdomain: lemaison-final-test...
:loop
:: Adding --local-host 127.0.0.1 helps prevent the random 503 Tunnel Unavailable errors
lt --port 5000 --local-host 127.0.0.1 --subdomain lemaison-final-test
echo [!] LocalTunnel disconnected. Restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop
