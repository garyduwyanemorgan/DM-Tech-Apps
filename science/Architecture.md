# Architecture

Current

Field Data
↓
FastAPI
↓
Supabase
↓
Dashboard

Future

Field Data
Voice Data
Laboratory Data
Sensor Data
↓
Validation Layer
↓
Event Queue
↓
Scientific Engine
↓
Supabase
↓
API Layer
↓
Dashboard
↓
Digital Twin

## Design Rules

Core Logic:
- Pure Python
- No UI dependencies

Database:
- Isolated layer

Dashboard:
- Read only

API:
- Stateless

Models:
- Explainable

Avoid:
- Hidden AI decisions
- Hard-coded thresholds
- Dashboard bloat