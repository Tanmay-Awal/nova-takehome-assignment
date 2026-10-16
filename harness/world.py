"""The world model: everything the harness holds on a given as_of date, organised for the rules in engine.py.

Nothing here calls a model. All inputs are the structured facts written by understand.py.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import store

CENT = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def d2s(d: Decimal) -> str:
    return f"{money(d):.2f}"


def pdate(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def norm_awb(a: str) -> str:
    s = re.sub(r"-H\d+$", "", a or "").strip()
    return re.sub(r"^(?:AWB|MAWB|HAWB)[-_]?", "", s, flags=re.I).strip("- \t")


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    m += 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


class Contract:
    def __init__(self, cid: str):
        self.id = cid
        self.msa: dict | None = None          # fact record
        self.msa_doc: dict | None = None
        self.amendments: list[tuple[dict, dict]] = []   # (doc, fact record)
        self.annexes: list[tuple[dict, dict]] = []

    @property
    def d(self) -> dict:
        return self.msa["data"]

    @property
    def terms(self) -> dict:
        return self.d["terms"]

    def term(self, name, default=None):
        t = self.terms.get(name)
        return t["value"] if t else default

    def clause(self, num: str):
        c = self.d["clauses"].get(num)
        return c

    def schedule1(self) -> list[dict]:
        return self.d.get("schedule1") or []

    def person_by_email(self, addr: str):
        a = (addr or "").strip().lower()
        for p in self.schedule1():
            if p.get("email", "").lower() == a:
                return p
        return None

    def carrier_party(self) -> str | None:
        for p in self.schedule1():
            if p.get("party_role") == "Carrier":
                return p["party"]
        for p in self.schedule1():
            if p.get("party") and p["party"] in (self.id or ""):
                return p["party"]
        for p in self.schedule1():
            if set(p["categories"]) & {"rates", "waivers", "treasury"}:
                return p["party"]
        return None

    def contact(self, category: str, party: str | None = None):
        party = party or self.carrier_party()
        norm = lambda s: (s or "").lower().replace("-", "_")
        c_target = norm(category)
        for p in self.schedule1():
            p_cats = [norm(c) for c in p.get("categories", [])]
            if c_target in p_cats and (party is None or p["party"] == party):
                return p
        return None

    def kam(self):
        return self.contact("notices")

    @property
    def currency(self) -> str:
        return self.d.get("currency") or "USD"


class World:
    def __init__(self, state_dir: str, as_of: str):
        self.state_dir = state_dir
        self.as_of = as_of
        self.asd = pdate(as_of)
        self.docs = store.load_docs(state_dir, as_of)
        facts = store.load_facts(state_dir)
        self.by_ref = {d["ref"]: d for d in self.docs}
        self.facts = {r: f for r, f in facts.items() if r in self.by_ref}
        self.feedback = [fb for fb in store.load_feedback(state_dir)]
        self.contracts: dict[str, Contract] = {}
        self._load_contracts()
        self.invoices: list[dict] = []            # invoice / statement / credit-note fact records with their doc
        self.credit_notes: list[dict] = []
        self.payment_advices: list[dict] = []
        self.tracking: dict[str, list[dict]] = {}
        self.awbs: dict[str, dict] = {}
        self.dgds: dict[str, dict] = {}
        self.registers: list[dict] = []
        self.email_facts: list[dict] = []
        self._load_rest()
        self.ledger = self._ledger()

    # --------------------------------------------------------------------------------------------------------
    def _load_contracts(self):
        msa_docs = []
        for r, f in self.facts.items():
            doc = self.by_ref[r]
            if f["kind"] == "msa":
                cid = f["data"].get("contract_id")
                if cid:
                    msa_docs.append((doc.get("received_ts", 0), doc.get("received", ""), r, f, doc))
        msa_docs.sort(key=lambda x: (x[0], x[2]))

        for _, _, r, f, doc in msa_docs:
            cid = f["data"].get("contract_id")
            c = self.contracts.setdefault(cid, Contract(cid))
            # Tag clauses with source doc_ref
            f_clauses = f["data"].get("clauses", {})
            for cl in f_clauses.values():
                if isinstance(cl, dict) and "doc_ref" not in cl:
                    cl["doc_ref"] = doc["ref"]

            if c.msa is None:
                c.msa = {"kind": "msa", "data": dict(f["data"])}
                c.msa_doc = doc
            else:
                c_data = c.msa["data"]
                f_data = f["data"]
                if "terms" in f_data:
                    c_data.setdefault("terms", {}).update(f_data["terms"])
                if "clauses" in f_data:
                    c_data.setdefault("clauses", {}).update(f_data["clauses"])
                if f_data.get("rates"):
                    if not c_data.get("rates"):
                        c_data["rates"] = list(f_data["rates"])
                    else:
                        existing_map = {(r["lane"], r["band"]): i for i, r in enumerate(c_data["rates"])}
                        for nr in f_data["rates"]:
                            key = (nr["lane"], nr["band"])
                            if key in existing_map:
                                c_data["rates"][existing_map[key]] = nr
                            else:
                                c_data["rates"].append(nr)
                for tbl in ["fuel", "accessorials", "charge_codes", "fx", "schedule1", "periods"]:
                    if not c_data.get(tbl) and f_data.get(tbl):
                        c_data[tbl] = f_data[tbl]
                    elif c_data.get(tbl) and f_data.get(tbl) and tbl == "schedule1":
                        existing_emails = {p.get("email") for p in c_data[tbl] if p.get("email")}
                        for p in f_data[tbl]:
                            if not p.get("email") or p.get("email") not in existing_emails:
                                c_data[tbl].append(p)
                    elif c_data.get(tbl) and f_data.get(tbl) and tbl == "fx":
                        existing_months = {r["month"]: i for i, r in enumerate(c_data[tbl]) if "month" in r}
                        for r in f_data[tbl]:
                            if "month" in r:
                                if r["month"] in existing_months:
                                    c_data[tbl][existing_months[r["month"]]] = r
                                else:
                                    c_data[tbl].append(r)
                if f_data.get("currency") and not c_data.get("currency"):
                    c_data["currency"] = f_data["currency"]
                # If newer doc has rates or terms, keep msa_doc updated
                if f_data.get("rates") or not c_data.get("rates"):
                    c.msa_doc = doc

        for r, f in self.facts.items():
            doc = self.by_ref[r]
            if f["kind"] in ("amendment", "annex"):
                cid = f["data"].get("contract_id")
                c = self.contracts.get(cid)
                if c is None:
                    continue
                (c.amendments if f["kind"] == "amendment" else c.annexes).append((doc, f))
        for c in list(self.contracts.values()):
            if c.msa is None:
                del self.contracts[c.id]

    def _load_rest(self):
        for r, f in self.facts.items():
            doc = self.by_ref[r]
            k, d = f.get("kind"), f.get("data")
            if not d:
                continue
            if k in ("invoice", "statement", "credit_note"):
                rec = {"doc": doc, "fact": f, "d": d}
                (self.credit_notes if (k == "credit_note" or d.get("kind") == "credit_note" or d.get("credit")) else self.invoices).append(rec)
            elif k == "payment_advice":
                self.payment_advices.append({"doc": doc, "d": d})
            elif k == "tracking":
                for e in d["events"]:
                    self.tracking.setdefault(e["awb"], []).append({**e, "doc": doc})
            elif k == "awb" and d:
                self.awbs[d["awb"]] = {**d, "doc": doc}
            elif k == "dgd" and d:
                self.dgds[d["awb"]] = {**d, "doc": doc}
            elif k == "ap_register":
                self.registers.append({"doc": doc, "rows": d["rows"]})
            elif k == "email":
                for x in d.get("facts", []):
                    self.email_facts.append({**x, "doc": doc})
        self.invoices.sort(key=lambda r: (r["d"].get("invoice_date") or "", r["doc"]["ref"]))
        self.registers.sort(key=lambda r: r["doc"]["received_ts"])

    def _ledger(self) -> dict[str, dict]:
        """Latest known ledger row per invoice number (a later register wins)."""
        out: dict[str, dict] = {}
        for rec in self.invoices:
            d = rec["d"]
            inv_id = d.get("invoice_id")
            if not inv_id:
                continue
            due = d.get("due_date")
            if not due and d.get("invoice_date"):
                c = self.contract_of(rec)
                pdays = c.term("payment_days", 30) if c else 30
                from datetime import timedelta
                idate = pdate(d["invoice_date"])
                if idate:
                    due = (idate + timedelta(days=pdays)).isoformat()
            out[norm_inv(inv_id)] = {
                "invoice_no": inv_id,
                "status": "open",
                "amount": d.get("total") or 0.0,
                "due_date": due,
                "paid_date": None,
                "currency": d.get("currency", "USD"),
                "line": f"Invoice {inv_id} due {due}",
                "doc": rec["doc"],
                "page": 1
            }
        for pa in getattr(self, "payment_advices", []):
            d = pa["d"]
            inv_ref = d.get("invoice_id")
            if inv_ref:
                key = norm_inv(inv_ref)
                if key in out:
                    out[key]["status"] = "paid"
                    out[key]["paid_date"] = d.get("paid_date")
                    if d.get("amount"):
                        out[key]["paid_amount"] = d["amount"]
                else:
                    out[key] = {
                        "invoice_no": inv_ref,
                        "status": "paid",
                        "amount": d.get("amount") or 0.0,
                        "due_date": None,
                        "paid_date": d.get("paid_date"),
                        "currency": d.get("currency", "USD"),
                        "line": f"Payment remittance for {inv_ref} paid {d.get('paid_date')}",
                        "doc": pa["doc"],
                        "page": 1
                    }
        for reg in self.registers:
            for row in reg["rows"]:
                out[norm_inv(row["invoice_no"])] = {**row, "doc": reg["doc"]}
        return out

    # --------------------------------------------------------------------------------------------------------
    def contract_of(self, rec) -> Contract | None:
        ref = rec["d"].get("contract_ref")
        if ref and ref in self.contracts:
            return self.contracts[ref]
        if ref:
            for cid, c in self.contracts.items():
                if ref in cid or cid in ref:
                    return c
        inv_id = rec["d"].get("invoice_id") or ""
        inv_pref = inv_id.split("-")[0].upper() if "-" in inv_id else ""
        if inv_pref:
            pref_matches = [c for c in self.contracts.values() if c.id.startswith(inv_pref)]
            if len(pref_matches) == 1:
                return pref_matches[0]
        cands = [c for c in self.contracts.values() if c.currency == rec["d"].get("currency")]
        if len(cands) == 1:
            return cands[0]
        inv_lanes = {ln.get("lane") for ln in rec["d"].get("lines", []) if ln.get("lane")}
        if inv_lanes:
            lane_cands = [c for c in self.contracts.values() if any(r.get("lane") in inv_lanes for r in c.d.get("rates", []))]
            if len(lane_cands) == 1:
                return lane_cands[0]
        return cands[0] if len(cands) == 1 else (list(self.contracts.values())[0] if len(self.contracts) == 1 else None)

    def pickup(self, awb: str, inv_line_date: str | None):
        """-> (date, tier, evidence) with tier 1=tracking, 2=carrier email, 3=AWB, 4=invoice."""
        base = norm_awb(awb)
        for key in (awb, base):
            for e in self.tracking.get(key, []):
                if e["event"] == "PICKED_UP":
                    return pdate(e["date"]), 1, {"doc": e["doc"]["ref"], "page": e["page"], "quote": e["line"]}
        for x in self.email_facts:
            if x["type"] == "event" and x["event"] == "PICKED_UP" and norm_awb(x["awb"]) == base and not x.get("quoted"):
                return pdate(x["date"]), 2, {"doc": x["doc"]["ref"], "page": 1, "quote": x["quote"]}
        for key in (awb, base):
            a = self.awbs.get(key)
            if a and a.get("executed"):
                return pdate(a["executed"]), 3, None
        return pdate(inv_line_date), 4, None

    def events(self, awb: str) -> list[dict]:
        out = list(self.tracking.get(awb, [])) or list(self.tracking.get(norm_awb(awb), []))
        return sorted(out, key=lambda e: e["date"])

    def fx(self, c: Contract, invoice_date: str):
        month = (invoice_date or "")[:7]
        for r in c.d.get("fx") or []:
            if r["month"] == month:
                return r
        fx_list = c.d.get("fx") or []
        if len(fx_list) == 1:
            return fx_list[0]
        return None

    def to_usd(self, c: Contract, amount: Decimal, invoice_date: str, currency: str):
        """-> (Decimal usd | None, fx row | None). None when a needed rate is missing."""
        if currency == "USD":
            return money(amount), None
        r = self.fx(c, invoice_date)
        if not r:
            return None, None
        return money(amount / Decimal(str(r["inr_per_usd"]))), r


def norm_inv(s: str) -> str:
    return re.sub(r"[\s#:]", "", (s or "").upper())


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def locate(w: "World", ref: str, quote: str) -> int | None:
    """Page (1-based) of a document that holds the quote (spacing ignored), or None."""
    doc = w.by_ref.get(ref)
    if not doc:
        return None
    q = squash(quote)
    for i, p in enumerate(doc["pages"], 1):
        if q and q in squash(p):
            return i
    return None
