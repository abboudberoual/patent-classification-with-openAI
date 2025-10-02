# patent-classification-with-openAI
# Patent Classification with OpenAI

Lightweight script to classify patent records using OpenAI models.

## What’s included
- `classify_patents.py` — main script
- `requirements.txt` — dependencies (`pip install -r requirements.txt`)

## What’s NOT included (and why)
This repository does **not** include any datasets, prompt command files (DOCX), category definition PDFs, or generated outputs.  
These materials are course/professor content and **cannot be shared**. Please supply your own equivalents locally when running the script.

## Prerequisites
- Python 3.9+ recommended  
- An OpenAI API key set in your environment:
  - macOS/Linux: `export OPENAI_API_KEY=your_key`
  - Windows (PowerShell): `[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY','your_key','User')`
- (Optional) Select a model via `MODEL_NAME` (defaults to the script’s internal setting):
  - `export MODEL_NAME=gpt-4.1`

## Usage
Replace paths with your own local files.

```bash
python classify_patents.py \
  --csv /path/to/df.csv \
  --definition /path/to/Definition.pdf \
  --prompt "/path/to/Prompt Command File.docx" \
  --sheet df_D1 \
  --batch 10 \
  --outfile /path/to/results.xlsx
