#!/bin/bash

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi


# Run the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000