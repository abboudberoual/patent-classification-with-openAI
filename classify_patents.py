from dotenv import load_dotenv
load_dotenv()
import os
import time
import math
import argparse
import pandas as pd
from pathlib import Path
from openai import OpenAI
from docx import Document
import fitz  # PyMuPDF
# ---------- Helpers ----------

def read_docx_text(docx_path: Path) -> str:
    """Extract plain text from a .docx file."""
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Send prompts to OpenAI and return model output."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=os.getenv("MODEL_NAME", "gpt-4.1"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )
    return resp.choices[0].message.content

def read_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF (definitions)."""
    text = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text.append(page.get_text("text"))
    return "\n".join(text)

def build_system_prompt(prompt_docx: Path, def_text: str, def_filename: str) -> str:
    """Take base Prompt Command File, inject definition filename + text, and enforce 5-col table."""
    base_prompt = read_docx_text(prompt_docx)
    base_prompt = base_prompt.replace("#definition file", def_filename)
    base_prompt = base_prompt.replace("#Patent Information file", "df_006.csv")
    base_prompt += (
        "\n\n=== DEFINITION CRITERIA START ===\n"
        f"{def_text}\n"
        "=== DEFINITION CRITERIA END ===\n"
        "\nReturn ONLY a GitHub-style Markdown table with EXACTLY 5 columns and NO extra pipes or notes.\n"
        "Use this header EXACTLY (case & order must match):\n"
        "| patent num | definition code | decision | Confidence Level | Justification |\n"
        "Do not add any text before or after the table.\n"
    )
    return base_prompt


def build_user_prompt(batch_df: pd.DataFrame, def_filename: str) -> str:
    """Build per-batch prompt with patent rows."""
    rows = []
    for _, r in batch_df.iterrows():
        rows.append(
            f"- patent_num: {r.get('patent_num','')}\n"
            f"  patent_title: {r.get('patent_title','')}\n"
            f"  patent_abstract: {r.get('patent_abstract','')}\n"
            f"  cpc: {r.get('cpc','')}\n"
            f"  claim_text: {r.get('claim_text','')}\n"
            f"  conm: {r.get('conm','')}\n"
            f"  sic: {r.get('sic','')}\n"
        )
    return (
        f"Definition code (write exactly in table): {def_filename}\n"
        "Classify the following patents. Return ONLY the Markdown table:\n\n"
        + "\n".join(rows)
    )

def parse_markdown_table(md_table: str) -> pd.DataFrame:
    """
    Parse a GitHub-style Markdown table and return a DataFrame with EXACTLY 5 columns:
    | patent num | definition code | decision | Confidence Level | Justification |
    """
    # normalize and split
    lines = [ln.strip() for ln in md_table.splitlines() if ln.strip()]
    # find first header line that contains pipes
    header_idx = next(i for i, ln in enumerate(lines) if ln.startswith("|") and ln.endswith("|"))
    header = [h.strip() for h in lines[header_idx].strip("|").split("|")]
    # drop the separator line (---|---) if present
    data_lines = []
    for ln in lines[header_idx+1:]:
        bare = ln.replace("|", "").replace("-", "").replace(":", "").strip()
        if bare == "":  # ignore pure separator rows
            continue
        if set(bare) == set():  # just in case
            continue
        if set(ln.replace("|", "").strip()) <= {"-", ":"}:
            continue
        data_lines.append(ln)

    rows = []
    for ln in data_lines:
        cols = [c.strip() for c in ln.strip("|").split("|")]
        rows.append(cols[:5])  # keep exactly 5

    # enforce exact 5 headers
    expected = ["patent num", "definition code", "decision", "Confidence Level", "Justification"]
    if len(header) >= 5:
        header = [h.strip() for h in header[:5]]
    else:
        raise ValueError(f"Header has {len(header)} columns; expected 5.")

    # normalize header text
    header_map = dict(zip(header, expected))
    df = pd.DataFrame(rows, columns=[header_map.get(h, h) for h in header])
    # ensure final header names exactly match expected
    df.columns = expected
    return df

def append_markdown_to_xlsx(md_table: str, xlsx_path: Path, sheet_name: str):
    df = parse_markdown_table(md_table)

    if xlsx_path.exists():
        with pd.ExcelWriter(xlsx_path, engine="openpyxl", mode="a", if_sheet_exists="overlay") as w:
            try:
                existing = pd.read_excel(xlsx_path, sheet_name=sheet_name)
                out = pd.concat([existing, df], ignore_index=True)
            except Exception:
                out = df
            out.to_excel(w, sheet_name=sheet_name, index=False)
    else:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
            df.to_excel(w, sheet_name=sheet_name, index=False)


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--definition", required=True)
    ap.add_argument("--prompt", required=True, help="Prompt Command File (e.g., 'Prompt Command File - D1.docx')")
    ap.add_argument("--sheet", required=True, help="e.g., df_006_D1")
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--outfile", default="Output File.xlsx")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    def_path = Path(args.definition)
    prompt_docx = Path(args.prompt)
    out_path = Path(args.outfile)

    df = pd.read_csv(csv_path)
    def_text = read_pdf_text(def_path)
    system_prompt = build_system_prompt(prompt_docx, def_text, def_path.name)

    n = len(df)
    batches = math.ceil(n / args.batch)
    for i in range(batches):
        start = i * args.batch
        end = min((i + 1) * args.batch, n)
        batch_df = df.iloc[start:end]
        user_prompt = build_user_prompt(batch_df, def_path.name)

        for attempt in range(3):
            try:
                md = call_llm(system_prompt, user_prompt)
                if "| patent num |" not in md:
                    raise ValueError("Model did not return a Markdown table.")
                append_markdown_to_xlsx(md, out_path, args.sheet)
                print(f"✅ Batch {start+1}-{end} written to {out_path} [{args.sheet}]")
                break
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"Failed to process batch {start+1}-{end}")

if __name__ == "__main__":
    main()
