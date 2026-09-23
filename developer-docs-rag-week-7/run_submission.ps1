$ErrorActionPreference = "Stop"

Write-Host "[1/4] Installing dependencies..."
pip install -r requirements.txt

Write-Host "[2/4] Inspecting chunkers..."
python inspect_chunks.py

Write-Host "[3/4] Building baseline index..."
python build_db.py --strategy baseline --reset

Write-Host "[4/4] Building structure-aware index and evaluating..."
python build_db.py --strategy structure --reset
python evaluate_rag.py --generation

Write-Host "Done. Review results.md and search_dump.txt."
