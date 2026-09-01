@echo off
set PATH=C:\Program Files\Docker\Docker\resources\bin;%PATH%
REM ============================================================================
REM  SODA Contexture — ClickHouse Agent Stack Launcher
REM  Usage:
REM    run.bat up       Build and start all containers
REM    run.bat down     Stop and remove containers
REM    run.bat logs     Tail logs from all containers
REM    run.bat test     Run NLP query routing tests (no DB required)
REM    run.bat shell    Open a ClickHouse client shell
REM    run.bat init     Re-run the SQL init script against the running DB
REM ============================================================================

set COMPOSE=docker compose -f pkg\agents\clickhouse\docker-compose.yml

if "%1"=="up" (
    echo [*] Building and starting ClickHouse agent stack...
    %COMPOSE% up --build -d
    echo.
    echo [*] Waiting for services to be healthy...
    timeout /t 8 /nobreak >nul
    %COMPOSE% ps
    echo.
    echo [*] Stack is ready!
    echo     ClickHouse native port : http://localhost:9000
    echo     ClickHouse HTTP port   : http://localhost:8123
    echo     MCP Agent SSE endpoint : http://localhost:8004/sse
    goto end
)

if "%1"=="down" (
    echo [*] Stopping ClickHouse agent stack...
    %COMPOSE% down -v
    goto end
)

if "%1"=="logs" (
    %COMPOSE% logs -f
    goto end
)

if "%1"=="test" (
    echo [*] Running NLP query routing tests (mocked - no DB required)...
    py pkg\agents\clickhouse\test_agent_nlp.py
    goto end
)

if "%1"=="shell" (
    echo [*] Opening ClickHouse client shell...
    docker exec -it contexture-clickhouse clickhouse-client
    goto end
)

if "%1"=="init" (
    echo [*] Re-running SQL init script...
    docker exec -i contexture-clickhouse clickhouse-client --multiquery < scripts\clickhouse\init.sql
    goto end
)

echo Usage: run.bat [up ^| down ^| logs ^| test ^| shell ^| init]
echo.
echo   up     Build and start all containers (ClickHouse DB + MCP agent)
echo   down   Stop and clean up all containers and volumes
echo   logs   Tail live container logs
echo   test   Run NLP routing tests without needing a running DB
echo   shell  Open an interactive ClickHouse SQL shell
echo   init   Re-seed the database with sample schema and data

:end
