"""
entity_extraction.py

Reads pubmed_results.csv (must have pmid/title/abstract headers),
extracts entities (diseases, chemicals, genes/proteins) using scispaCy models,
writes entities.csv with columns: entity,entity_type,pmid,sentence

Usage:
    python entity_extraction.py --input pubmed_results.csv --output entities.csv --min_count 1
"""

import argparse
import csv
import os
from collections import Counter, defaultdict
from tqdm import tqdm
import pandas as pd
import spacy

# choose models (we use two separate models for disease/chemical and genes)
MODEL_BC5 = "en_ner_bc5cdr_md"   # diseases + chemicals (BC5CDR)
MODEL_JNLP = "en_ner_jnlpba_md"  # genes/proteins (JNLPBA)

def load_models():
    nlp_bc5 = spacy.load(MODEL_BC5)
    nlp_jnlp = spacy.load(MODEL_JNLP)
    return nlp_bc5, nlp_jnlp

def normalize_ent(ent_text: str) -> str:
    return ent_text.strip()

def extract_from_text(nlp, text):
    doc = nlp(text)
    # return list of (ent_text, ent_label, sentence_text)
    out = []
    for ent in doc.ents:
        sent = ent.sent.text.strip() if ent.sent is not None else ""
        out.append((normalize_ent(ent.text), ent.label_, sent))
    return out

def main(input_csv, output_csv, min_count=1, max_rows=None):
    print("Loading models...")
    nlp_bc5, nlp_jnlp = load_models()
    print("Models loaded.")

    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]

    if not {"pmid", "title", "abstract"}.issubset(set(df.columns)):
        raise RuntimeError("CSV must contain columns pmid,title,abstract (case-insensitive). Found: " + str(list(df.columns)))

    rows = df.to_dict(orient="records")
    if max_rows:
        rows = rows[:max_rows]

    # accumulate entity occurrences per pmid
    # mapping (entity_text, entity_type) -> set of pmids and list of sentences
    occurrences = defaultdict(lambda: {"pmids": set(), "sentences": defaultdict(int)})

    print(f"Processing {len(rows)} rows...")
    for row in tqdm(rows):
        pmid = str(row.get("pmid", "")).strip()
        if not pmid:
            continue
        title = row.get("title", "") or ""
        abstract = row.get("abstract", "") or ""
        text_to_process = ""
        if title and abstract:
            text_to_process = title + "\n\n" + abstract
        elif abstract:
            text_to_process = abstract
        else:
            text_to_process = title

        # bc5 model: diseases + chemicals
        try:
            ents_bc5 = extract_from_text(nlp_bc5, text_to_process)
        except Exception as e:
            print(f"Warning: bc5 extraction failed for pmid {pmid}: {e}")
            ents_bc5 = []

        # jnlp model: genes/proteins
        try:
            ents_jnlp = extract_from_text(nlp_jnlp, text_to_process)
        except Exception as e:
            print(f"Warning: jnlp extraction failed for pmid {pmid}: {e}")
            ents_jnlp = []

        for ent_text, ent_label, sent in ents_bc5 + ents_jnlp:
            # map model labels to a small set
            label_norm = None
            if ent_label in {"DISEASE", "disease", "Disease", "DIS"}:
                label_norm = "Disease"
            elif ent_label in {"CHEMICAL", "CHEM", "Chemical"} or ent_label.upper().startswith("CHEM"):
                label_norm = "Chemical"
            elif ent_label in {"GENE_OR_GENOME", "GENE", "protein", "DNA", "RNA"} or ent_label.upper().startswith("GEN"):
                label_norm = "Gene"
            elif ent_label.upper() == "GENE":
                label_norm = "Gene"
            else:
                # bc5cdr uses 'DISEASE' and 'CHEMICAL', jnlpba has specific tags
                # make a best-effort mapping:
                if MODEL_BC5 and ent_label.upper() in {"DISEASE"}:
                    label_norm = "Disease"
                elif MODEL_BC5 and ent_label.upper() in {"CHEMICAL"}:
                    label_norm = "Chemical"
                else:
                    # fall back: use ent_label as-is (but prefer to skip unknown noisy labels)
                    label_norm = ent_label

            if not ent_text:
                continue
            key = (ent_text, label_norm)
            occurrences[key]["pmids"].add(pmid)
            occurrences[key]["sentences"][sent] += 1

    print("Aggregating results...")

    # flatten to rows and filter by min_count across distinct pmids
    out_rows = []
    for (ent_text, ent_type), meta in occurrences.items():
        pmid_list = sorted(meta["pmids"])
        if len(pmid_list) < min_count:
            continue
        # pick the most common sentence (if any)
        sentence = ""
        if meta["sentences"]:
            sentence = max(meta["sentences"].items(), key=lambda x: x[1])[0]
        out_rows.append({
            "entity": ent_text,
            "entity_type": ent_type,
            "pmid_count": len(pmid_list),
            "pmids": ";".join(pmid_list),
            "sentence": sentence
        })

    # Sort by pmid_count desc
    out_rows.sort(key=lambda r: r["pmid_count"], reverse=True)

    # Write a CSV with one row per entity; also write a normalized per-pmid CSV if desired
    print(f"Writing {len(out_rows)} entity rows to {output_csv} ...")
    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["entity", "entity_type", "pmid_count", "pmids", "sentence"])
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    # Also optionally write per-pmid normalized rows (entity,pid)
    per_pmid_csv = os.path.splitext(output_csv)[0] + "_per_pmid.csv"
    print(f"Writing per-pmid expanded file to {per_pmid_csv} ...")
    with open(per_pmid_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["entity", "entity_type", "pmid", "sentence"])
        writer.writeheader()
        for r in out_rows:
            pmids = r["pmids"].split(";")
            for pmid in pmids:
                writer.writerow({"entity": r["entity"], "entity_type": r["entity_type"], "pmid": pmid, "sentence": r["sentence"]})

    print("Done.")
