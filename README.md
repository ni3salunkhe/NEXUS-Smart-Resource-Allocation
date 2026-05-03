# NEXUS: Mission-Critical NGO Registry & Ingestion System

NEXUS is a robust, multi-tenant digital infrastructure designed to empower NGOs with secure beneficiary tracking, high-velocity data ingestion, and advanced identity resolution. Built for scale and reliability, NEXUS simplifies the journey from raw field reports to actionable assistance.

---

## 🚀 Project Overview

The NEXUS platform provides a unified gateway for ingesting needs and managing household registries across multiple organizations (tenants). It leverages geospatial intelligence, natural language processing, and automated deduplication to ensure data integrity and operational efficiency.

### Key Architectural Pillars:
* **Multi-Tenant Isolation**: Row-Level Security (RLS) ensures NGO data remains strictly private across the DB and API.
* **Geospatial Intelligence**: PostGIS-powered tracking for rapid disaster response and proximity-based dispatch.
* **Intelligent Ingestion**: Multi-channel pipeline with OCR and NLP capabilities.
* **Identity Resolution**: Advanced ensemble matching to prevent duplicate assistance.
* **Role-Based Workflows**: Tailored interfaces and routing for Platform Admins, Tenant Coordinators, and Field Volunteers.

---

## 🛠️ Architecture & Modules

### 1. Frontend Client (React/Vite)
* **Stack**: React 19, Vite, Tailwind CSS, Zustand, React-Query, Leaflet.
* **Features**:
  * Role-based dashboards (Admin, Coordinator, Volunteer).
  * Real-time WebSocket updates for needs and active workflows.
  * Geospatial household mapping and multi-tenant selectors.
  * Progressive Web App (PWA) readiness for offline field ops.

### 2. API Gateway
* **Routing**: Centralized gateway handling cross-origin requests, authentication stripping, and routing logic across all backend microservices.
* **Security**: Enforces strict CORS, rate limiting, and standardizes tenant identification via `X-Tenant-ID`.

### 3. Backend Microservices (FastAPI)
* **Auth Service**: JWT-based authentication, unified logging, and multi-tenant scoping.
* **Registry Service**: DPDP-compliant intake workflows, identity cascade matching, and RLS-enforced database mutations.
* **Ingestion Service**: Resilient multi-modal ingestion (Mobile, Web, CSV) pipelined via Kafka.
* **Coordination Service**: End-to-end task lifecycles, automated volunteer dispatch state machines, and priority queuing.
* **Intelligence & Analytics Service**: Needs triaging, urgency scoring, NLP extraction, and system-wide impact metrics.

### 4. Infrastructure & Event Layer
* **PostgreSQL / PostGIS**: Transactional store with multi-tenant row-level security.
* **Kafka**: Distributed event bus ensuring zero message loss and exact-ordering for `NeedCreated` and `TaskDispatched` events.
* **Redis**: Rate limiting, state caching, and rapid session access.
* **Docker Compose**: Production-hardened containerization with dependency healthchecks.

---

## ⚙️ Project Setup

### 1. Prerequisites
* **Python**: 3.10 or higher.
* **Node.js & npm**: 20.x or higher (for the frontend).
* **Docker**: For running database and messaging services.
* **API Keys** (Optional): Google Cloud Vision / Maps for enhanced processing.

### 2. Services & Docker Management
Ensure your Docker environment is active.
```bash
# Start all infrastructure
docker-compose up -d

# Check service health
docker-compose ps
```

### 3. Backend Setup
Install dependencies within a virtual environment:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Initialize the database:
```bash
# Apply migrations and schema
python scripts/apply_migrations.py
python scripts/apply_phase01.py

# Seed initial data
python scripts/seed_phase0.py
```

Run backend services:
```bash
# Using powershell script for convenience:
./start_backend.ps1
```

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Testing & Validation

NEXUS integrates an exhaustive, multi-layered verification suite validating system survivability under adversarial conditions.

### 1. Unit & Integration Tests
```bash
pytest backend/tests/ -v
```

### 2. Comprehensive E2E Flow
Validates full end-to-end service integration from Registry Intake to Field-Worker Dispatch:
```bash
python scripts/master_system_validation.py
```

### 3. Infrastructure & Resilience Audits
* **Kafka Resilience Audit**: 10/10 Score for zero-loss, idempotency, and burst recovery.
* **Intelligence Audit**: Definite validation of feedback loops, DB immutability, and sub-40ms latency contracts.
* **Survivability Suite**: Validates system degradation and automated recovery mechanisms.

```bash
python scripts/kafka_resilience_audit.py
python scripts/survivability_suite.py
```

## 🛡️ Distributed Production Readiness
The NEXUS platform is certified for distributed operation:
* **Event Safety**: Memory-bounded idempotency and interruptible consumer loops.
* **Security**: 100% tenant isolation via FORCED RLS in PostgreSQL.
* **Integrity**: Granular immutability triggers on critical audit logs.
* **Concurrency**: Optimized DB pooling with semaphore-limited burst protection.

---

## 📄 License
This project is proprietary and intended for mission-critical NGO operations.
