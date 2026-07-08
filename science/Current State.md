# Current State

## Technology

Frontend:
- Streamlit

Backend:
- FastAPI

Database:
- Supabase

Agent:
- MCP Server

Automation:
- n8n

Voice:
- Vonage → STT → n8n → FastAPI

## Current Features

### Core

models.py
constants.py
alert_engine.py
calculations.py

### Database

client.py
queries.py

### Dashboard

- Executive Dashboard
- Compliance Reporting
- Water Quality Monitoring
- Alert & Response
- Seasonal Calendar
- Sludge Management
- Environmental Drivers
- Species Threat Matrix
- Intervention Technologies
- ML Prediction System

### API

GET /health

GET /sites

POST /assess

POST /log

GET /status/{site}

GET /tools

### MCP Tools

assess_reading

log_reading

get_site_status

get_treatment_protocol

list_sites

## Current Status

Supabase Connected

FastAPI Working

MCP Working

Dashboard Working

Voice Pipeline In Progress