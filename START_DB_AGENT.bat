@echo off
echo ============================================
echo  AI Database Agent - MongoDB
echo ============================================
echo.

echo [1/3] Seeding demo data into MongoDB...
python create_demo_db.py
python create_demo_mongo.py
if %errorlevel% neq 0 (
    echo ERROR: Failed to seed MongoDB. Make sure MongoDB is running.
    pause
    exit /b 1
)
echo Done.
echo.

echo [2/3] Starting AI Agent on port 8010...
start "AI Agent (port 8010)" cmd /k python -m uvicorn ai_agent.main:app --host 127.0.0.1 --port 8010 --workers 1
timeout /t 4 /nobreak >nul

echo [3/3] Starting DB Chat UI on port 8501...
start "DB Chat UI (port 8501)" cmd /k streamlit run ai_agent_ui.py --server.port 8501

echo.
echo ============================================
echo  Services started:
echo   AI Agent : http://127.0.0.1:8010/ai-agent/docs
echo   Chat UI  : http://localhost:8501
echo ============================================
echo.
echo Connect via the Chat UI:
echo   1. Select MongoDB in the sidebar
echo   2. URI: mongodb://localhost:27017
echo   3. Database: demo
echo   4. Click Connect and start asking questions
echo.
pause
