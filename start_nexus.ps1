# NEXUS Full-Stack Test Execution Script
# Run this from the root directory (e:\NEXUS_copy)

echo "======================================================"
echo "    Starting Infrastructure (Postgres, Mongo, Kafka)"
echo "======================================================"
docker-compose up -d

echo ""
echo "Waiting 15 seconds for databases to initialize..."
Start-Sleep -Seconds 15

echo ""
echo "======================================================"
echo "    Starting NEXUS Backend Services"
echo "======================================================"
cd backend
# Starts all uvicorn servers and the node proxy
.\start_backend.ps1
cd ..

echo ""
echo "======================================================"
echo "    Starting NEXUS Frontend (Vite Dev Server)"
echo "======================================================"
cd frontend
npm run dev
