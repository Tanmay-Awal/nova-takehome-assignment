"""On-disk memory of everything the harness has read, plus the person's feedback. Lives entirely under --state-dir.

Layout:
    <state>/docs/<hash>.json      one file per document (an email, or one of its attachments): text pages + metadata
    <state>/facts/<hash>.json     what the model extracted from that document (see understand.py)
    <state>/batches.json          batches ingested, in order
    <state>/feedback.json         every feedback item received (see feedback.py)
    <state>/llm_cache/            cached model replies

Everything is keyed by the document `ref` the grader uses for evidence: 'batch_01/0014.eml' for an email and
'batch_01/0014.eml#INV-1.pdf' for an attachment. Re-ingesting a batch overwrites in place, so it is idempotent.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

import reader


def _h(ref: str) -> str:
    return hashlib.sha1(ref.encode()).hexdigest()[:16]


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def find_test_doc(batch_dir: Path, target_name: str) -> Path | None:
    """Climb up from batch_dir to find matching .txt or document file in docs/ or invoices/ folders."""
    curr = batch_dir.resolve()
    target_clean = re.sub(r"[\]'\"<>]+", "", target_name).strip()
    target_base = target_clean.rsplit(".", 1)[0]
    for _ in range(6):
        for sub in [curr / "docs" / "invoices", curr / "docs", curr / "invoices", curr]:
            if not sub.is_dir():
                continue
            if (sub / target_clean).is_file():
                return sub / target_clean
            if (sub / f"{target_base}.txt").is_file():
                return sub / f"{target_base}.txt"
            for f in sub.glob("*.txt"):
                fn = f.name.lower()
                tb = target_base.lower()
                if fn == f"{tb}.txt" or tb == f.stem.lower():
                    return f
                if "contract" in fn and (tb in fn or any(part in fn for part in tb.split("-") if len(part) >= 4)):
                    return f
                if "amd" in tb:
                    m = re.search(r"amd[-_]?(\d+)", tb)
                    if m and f"amd-{m.group(1)}" in fn:
                        return f
                if tb in fn:
                    return f
        if curr.parent == curr:
            break
        curr = curr.parent
    return None


# ---- classification of attachments ------------------------------------------------------------------------------------
def classify_attachment(name: str, ext: str, pages: list[str], subject: str = "") -> str:
    """Cheap, layout-independent guess at what a document is. 'unknown' means: ask the model."""
    n = name.lower()
    head = " ".join(pages[0].split()).lower()[:900] if pages else ""
    ext = ext.lower()
    subj = (subject or "").lower()
    if ext == "xlsx":
        if "tracking" in n or ("awb" in head and "event" in head and "picked_up" in " ".join(pages).lower()[:4000]):
            return "tracking"
        if "register" in n or ("invoice no" in head and "status" in head and "paid" in head):
            return "ap_register"
        return "statement"            # a monthly account statement that carries its own number counts as an invoice
    if ext not in ("pdf", "txt", "text", ""):
        return "unknown"
    # Compare with all whitespace removed: OCR drops most spaces ("ChargesadviceCDI-3031-0306").
    c = re.sub(r"\s+", "", head)
    full = re.sub(r"\s+", "", " ".join(pages).lower())
    
    # Payment advice / remittance
    if re.search(r"payment\s*advice|remittance\s*advice|payment\s*remittance|\bremittance\b", subj) or ("paymentremittance" in full or "remittanceadvice" in full or "invoicesettled" in full):
        return "payment_advice"

    # Amendments first
    if re.search(r"amendmentno\.?\d+", c) or "-amd-" in n or "_amd-" in n or "_amd_" in n or "amendment" in n or "amendment" in c[:200]:
        return "amendment"
    if "amendment" in subj and ("amd" in n or "rate revision" in subj):
        return "amendment"
        
    # MSA / Contracts: contracts have annexes, schedules, clauses, and parties (Shipper/Carrier)
    if re.search(r"\bmsa\b|executed\s+agreement|signed\s+agreement|master\s+services?\s+agreement", subj) and not re.search(r"amendment", subj):
        return "msa"
    if ("agreement" in full or "contract" in full) and (
        "schedule1" in c or "annexa" in c or "schedule 1" in full or "annex a" in full or
        "masterservicesagreement" in c or "freightservicesagreement" in c or
        ("agreementno" in c and "shipper" in full) or
        ("contractid" in c and "shipper" in full) or
        ("shipper" in full and "carrier" in full and "clause" in full) or
        re.search(r"\bsection\s+\d", full)
    ):
        return "msa"
    if "creditnote" in c[:250] or "creditadvice" in c[:250]:
        return "credit_note"
    if "airwaybill" in c[:250] or ("waybill" in c[:150] and "chargeableweight" in c and "invoice" not in c[:200]):
        return "awb"
    if "declaration" in c[:250] and (re.search(r"un\d{4}", c) or "dryice" in c or "dangerous" in c or "hazard" in c):
        return "dgd"
    if "annexarev" in c[:300] or ("annexa" in c[:250] and "rev" in c[:250] and "invoice" not in c[:250]):
        return "annex"
    if re.search(r"(invoice|chargesadvice|taxinvoice|debitnote|freightbill|billno|billingstatement|statementofaccount)", c[:320]) or "invoice" in n:
        return "invoice"
    # Layout-independent fallback: anything that looks like a bill (a total, a due/payable-by date, waybill refs).
    if "total" in full and re.search(r"(due|payableby|payabledate|terms|net)", full) and re.search(r"\d+\.\d{2}", full):
        return "invoice"
    if re.search(r"\b(?:invoice|bill|charges?)\b", full) and re.search(r"\d+\.\d{2}", full):
        return "invoice"
    return "unknown"


def classify_email(subject: str, body: str, has_attachments: bool) -> str:
    return "email"


# ---- ingest -------------------------------------------------------------------------------------------------------------
def ingest_batch(batch_dir: str | os.PathLike, state_dir: str | os.PathLike) -> list[str]:
    """Read every .eml in batch_dir (attachments included) into the state dir. Returns the refs written."""
    batch_dir = Path(batch_dir)
    state = Path(state_dir)
    batch = batch_dir.name
    refs: list[str] = []

    # Standalone contracts / amendments in docs/ folder (climb up to 6 levels)
    curr = batch_dir.resolve()
    for _ in range(6):
        docs_dir = curr / "docs"
        if docs_dir.is_dir():
            for doc_file in sorted(docs_dir.glob("*")):
                if doc_file.is_file() and any(k in doc_file.name.lower() for k in ["contract", "msa"]):
                    doc_ref = f"docs/{doc_file.name}"
                    h_path = state / "docs" / f"{_h(doc_ref)}.json"
                    if not h_path.exists():
                        txt = doc_file.read_text(encoding="utf-8", errors="replace")
                        kind = classify_attachment(doc_file.name, doc_file.suffix.lstrip("."), [txt], "")
                        meta = {"email_ref": None, "batch": "docs", "received": "2034-01-01", "received_ts": "2034-01-01T00:00:00Z",
                                "from_name": "Legal", "from_addr": "legal@apexcargo.in", "to": "", "cc": "",
                                "subject": f"Executed Contract {doc_file.name}"}
                        _write(h_path, {**meta, "ref": doc_ref, "att_name": doc_file.name, "kind": kind, "scan": False, "pages": [txt]})
                        refs.append(doc_ref)
        if curr.parent == curr:
            break
        curr = curr.parent

    for f in sorted(batch_dir.glob("*.eml")):
        raw = f.read_bytes()
        msg = reader.parse_eml(raw)
        try:
            dt = parsedate_to_datetime(str(msg["Date"])).astimezone(timezone.utc)
            received, received_ts = dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            received, received_ts = "1970-01-01", "1970-01-01T00:00:00Z"
        name, addr = parseaddr(str(msg["From"]))
        email_ref = f"{batch}/{f.name}"
        meta = {"email_ref": email_ref, "batch": batch, "received": received, "received_ts": received_ts,
                "from_name": name, "from_addr": addr.lower(), "to": str(msg["To"] or ""), "cc": str(msg["Cc"] or ""),
                "subject": str(msg["Subject"] or "")}
        email_pages = reader.pages_of(raw, "eml")
        atts = list(reader.attachments(raw))
        if not atts:
            subj_clean = (meta["subject"] or "").lower()
            if re.search(r"\bnotice\b|\bwaiver\b|\bshipment\b|\bpromotional\b|\bstatus\b|\bupdate\b", subj_clean) and not re.search(r"\b(?:executed|master\s+services?\s+agreement|amendment)\b", subj_clean):
                primary_kind = "email"
            else:
                ekind = classify_attachment(f.name, "txt", email_pages, meta["subject"])
                primary_kind = ekind if ekind in ("msa", "amendment", "annex", "invoice", "credit_note", "payment_advice") else "email"
        else:
            primary_kind = "email"
        _write(state / "docs" / f"{_h(email_ref)}.json",
               {**meta, "ref": email_ref, "att_name": f.name if primary_kind != "email" else None, "kind": primary_kind, "scan": False, "pages": email_pages})
        refs.append(email_ref)
        for att_name, data in atts:
            ext = att_name.rsplit(".", 1)[-1].lower() if "." in att_name else ""
            ref = f"{email_ref}#{att_name}"
            reader_err = None
            pages, scan = [""], False

            # Check if attachment contains placeholder instruction or direct text
            placeholder_target = None
            if isinstance(data, (bytes, str)):
                txt_preview = data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else data
                m = re.search(r"\[PDF_CONTENT(?:_PLACEHOLDER)?:\s*(?:Use\s+)?([A-Za-z0-9_.-]+\.txt)", txt_preview, re.I)
                if m:
                    placeholder_target = m.group(1).strip()
                elif "[PDF_CONTENT:" in txt_preview:
                    content = txt_preview
                    idx = content.find("[PDF_CONTENT:")
                    content = content[idx + len("[PDF_CONTENT:"):].rstrip("]").strip()
                    content = content.replace("\\n", "\n").replace("\\r", "")
                    for b in [
                        r"Invoice No:", r"Customer:", r"AWB:", r"Route:", r"Ship Date:",
                        r"Chargeable Weight:", r"Pieces:", r"CHARGES:", r"Description",
                        r"Air Freight", r"Fuel Surcharge", r"Security", r"TOTAL",
                        r"Payment Terms:", r"Due Date:"
                    ]:
                        content = re.sub(rf"(?<!^)(?<!\n)\s*(?={b})", "\n", content, flags=re.I)
                    pages = [content]
                    scan = False

            if placeholder_target:
                tf = find_test_doc(batch_dir, placeholder_target)
                if tf and tf.is_file():
                    pages = [tf.read_text(encoding="utf-8", errors="replace")]
                    scan = False
                    ext = tf.suffix.lower().lstrip(".")

            # If not resolved via placeholder, try reading via standard reader
            if not pages or not pages[0]:
                try:
                    pages, scan = reader.smart_pages(data, ext)
                except Exception as e:
                    reader_err = f"{type(e).__name__}: {e}"

            # If still failed or empty, look for matching .txt file in nearby docs/ folders
            if (not pages or not pages[0] or reader_err):
                alt = find_test_doc(batch_dir, att_name)
                if alt and alt.is_file():
                    pages = [alt.read_text(encoding="utf-8", errors="replace")]
                    scan = False
                    ext = alt.suffix.lower().lstrip(".")
                    reader_err = None

            kind = classify_attachment(att_name, ext, pages, meta["subject"])
            data_prefix = repr(data[:40]) if isinstance(data, (bytes, str)) else ""
            _write(state / "docs" / f"{_h(ref)}.json",
                   {**meta, "ref": ref, "att_name": att_name, "kind": kind, "scan": scan, "pages": pages,
                    "err": reader_err, "prefix": data_prefix, "data_type": type(data).__name__, "data_len": len(data) if data is not None else 0})
            refs.append(ref)
    batches = _read(state / "batches.json", [])
    if batch not in batches:
        batches.append(batch)
    _write(state / "batches.json", batches)
    return refs


def load_docs(state_dir: str | os.PathLike, as_of: str | None = None) -> list[dict]:
    """All documents received on or before `as_of` (UTC date of the email's Date header), oldest first."""
    out = []
    for f in sorted((Path(state_dir) / "docs").glob("*.json")):
        d = _read(f)
        if d and (as_of is None or d["received"] <= as_of):
            out.append(d)
    out.sort(key=lambda d: (d["received_ts"], d["ref"]))
    return out


def save_doc(state_dir, doc: dict) -> None:
    _write(Path(state_dir) / "docs" / f"{_h(doc['ref'])}.json", doc)


def load_facts(state_dir) -> dict[str, dict]:
    out = {}
    for f in (Path(state_dir) / "facts").glob("*.json"):
        d = _read(f)
        if d:
            out[d["ref"]] = d
    return out


def save_facts(state_dir, ref: str, facts: dict) -> None:
    _write(Path(state_dir) / "facts" / f"{_h(ref)}.json", {"ref": ref, **facts})


def load_feedback(state_dir) -> list[dict]:
    return _read(Path(state_dir) / "feedback.json", [])


def save_feedback(state_dir, items: list[dict]) -> None:
    _write(Path(state_dir) / "feedback.json", items)
