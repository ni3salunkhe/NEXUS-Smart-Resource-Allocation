# NEXUS: Mission-Critical NGO Registry & Ingestion System

NEXUS is a robust, multi-tenant digital infrastructure designed to empower NGOs with secure beneficiary tracking, high-velocity data ingestion, and advanced identity resolution. Built for scale and reliability, NEXUS simplifies the journey from raw field reports to actionable assistance.

---

## 🚀 Project Overview

The NEXUS platform provides a unified gateway for ingesting needs and managing household registries across multiple organizations (tenants). It leverages geospatial intelligence, natural language processing, and automated deduplication to ensure data integrity and operational efficiency.

### Key Architectural Pillars:
* **Multi-Tenant Isolation**: Row-Level Security (RLS) ensures NGO data remains strictly private.
* **Geospatial Intelligence**: PostGIS-powered tracking for rapid disaster response.
* **Intelligent Ingestion**: Multi-channel pipeline with OCR and NLP capabilities.
* **Identity Resolution**: Advanced ensemble matching to prevent duplicate assistance.

---

## 🛠️ Development Phases

### Phase 0.5: Household Registry & Security
* **Infrastructure**: PostgreSQL + PostGIS baseline with custom migration logic.
* **Security**: Hardened Tenant isolation via PostgreSQL policies.
* **Ledger**: Append-only history tracking for audit compliance.
* **Resolution**: 4-stage identity cascade (Exact, Geo, Fuzzy, Composite).

### Phase 1: High-Velocity Ingestion Pipeline
* **Channels**: Mobile Forms, WhatsApp, SMS, Webhooks, CSV Bulk, and Paper Surveys (OCR).
* **OCR Bridge**: Hybrid pipeline using Google Cloud Vision with a Tesseract fallback.
* **NLP Processor**: Multilingual classification, severity scoring, and entity extraction.
* **Logic**: Automated Deduplication (Jaccard Similarity) and Review Queue routing for low-confidence data.

---

## ⚙️ Project Setup

### 1. Prerequisites
* **Python**: 3.10 or higher.
* **Docker**: For running database and messaging services.
* **API Keys** (Optional): Google Cloud Vision / Maps for enhanced processing.

### 2. Services & Docker Management
Ensure your Docker environment is active. We use the following core services:
* **PostgreSQL / PostGIS**: Primary transactional store.
* **Kafka**: Real-time event bus (Need Created, Audit, etc.).
* **Redis**: Caching and Rate-limiting.

**Standard commands:**
```bash
# Start all infrastructure
docker-compose up -d

# Check service health
docker-compose ps
```

### 3. Python Environment
Install dependencies within a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Database Initialization
Run the migration scripts to initialize the multi-tenant schema and apply Phase 1 tables:
```bash
# Apply Phase 0.5 & Phase 1 Schema
python scripts/apply_migrations.py
python scripts/apply_phase01.py

# Seed initial test data
python scripts/seed_phase0.py
```

---

## 🧪 Testing & Validation

NEXUS includes a rigorous verification suite to ensure system reliability under adversarial conditions.

### Run Unit Tests:
```bash
pytest tests/test_phase0.py -v
pytest tests/test_phase01.py -v
```

### Run Lifecycle Audit:
The "Crucible" test simulates real-world noisy data, duplicates, and multilingual inputs:
```bash
python scripts/audit_phase01.py
```

---

## 📄 License
This project is proprietary and intended for mission-critical NGO operations.
