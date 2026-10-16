"""Rate resolution and shipment pricing (deterministic).

resolve_rate(): which instrument sets the Annex A rate for (contract, lane, pickup date) - the MSA, a signed amendment, an
Annex A revision attached to an amendment, or a rate notice from a Schedule 1 'rates' person - and what happens when two of
them are in force at once (conflict) or the one we need is not held (missing).
price_invoice(): reprice every line of an invoice from the contract, tracking, AWB and declaration facts.
"""
from __future__ import annotations

import re
from decimal import Decimal

from world import World, Contract, money, pdate, norm_awb, norm_name, add_months
from feedback import Feedback


# ---------------------------------------------------------------------------------------------------------------------
def clause_ev(c: Contract, num: str, limit: int = 300) -> dict | None:
    cl = c.clause(num)
    if not cl:
        return None
    t = cl["text"]
    if len(t) > limit:
        cut = t.rfind(". ", 0, limit)
        t = t[: cut + 1] if cut > 60 else t[:limit]
    doc_ref = cl.get("doc_ref") or c.msa_doc["ref"]
    return {"doc": doc_ref, "page": cl.get("page", 1), "quote": t}


def row_for_weight(rows: list[dict], kg: float):
    """rows: band rows of one lane with lo/hi. The band that contains kg (gaps of 0.5 go to the lower band)."""
    best = None
    for r in rows:
        if r["band"] == "min":
            continue
        lo = r["lo"] if r["lo"] is not None else 0.0
        hi = r["hi"] if r["hi"] is not None else float("inf")
        if lo <= kg <= hi:
            return r
        if lo <= kg and (best is None or lo > (best["lo"] or 0)):
            best = r
    return best


class Cand:
    """One instrument's rates for a lane at a pickup date."""

    def __init__(self, src, rows, level, doc_ref, label, learned=None, eff=None):
        self.src, self.rows, self.level, self.doc_ref, self.label = src, rows, level, doc_ref, label
        self.learned, self.eff = learned, eff

    def rate(self, kg):
        """-> (rate, min, evidence list) for a chargeable weight."""
        r = row_for_weight(self.rows, kg)
        mn = next((x for x in self.rows if x["band"] == "min"), None)
        ev = []
        if r:
            ev.append(r["ev"])
        if mn:
            ev.append(mn["ev"])
        return (r["v"] if r else None), (mn["v"] if mn else None), ev


class Resolution:
    def __init__(self, status, cand=None, alt=None, missing=None, why=None):
        self.status = status           # ok | conflict | missing | none
        self.cand, self.alt, self.missing, self.why = cand, alt, missing, why


def _msa_cand(c: Contract, lane: str, pickup) -> Cand | None:
    d = c.d
    rows = [r for r in d["rates"] if r["lane"] == lane]
    if not rows:
        return None
    periods = d["periods"]
    idx = 0
    for i, p in enumerate(periods):
        if pdate(p["from"]) <= pickup:
            idx = i
    out = []
    for r in rows:
        vals = r["values"]
        v = vals[idx] if idx < len(vals) else vals[-1]
        out.append({"band": r["band"], "lo": r["lo"], "hi": r["hi"], "v": Decimal(str(v)),
                    "ev": {"doc": c.msa_doc["ref"], "page": r["page"], "quote": r["line"]}})
    return Cand("msa", out, 1, c.msa_doc["ref"], "MSA Annex A")


def _amend_cands(w: World, c: Contract, lane: str, pickup):
    """All amendment instruments for the lane in force at pickup -> list of (eff_date, Cand | ('missing', name, action, doc))."""
    found = []
    for doc, f in c.amendments:
        a = f["data"]
        if a.get("signed") is False:
            continue
        eff = pdate(a.get("effective_from"))
        for act in a.get("actions", []):
            if act["type"] == "replace_rates" and eff and eff <= pickup:
                rows = [r for r in a["rates"] if r["lane"] == lane]
                if rows:
                    out = [{"band": r["band"], "lo": r["lo"], "hi": r["hi"], "v": Decimal(str(r["values"][0])),
                            "ev": {"doc": doc["ref"], "page": r["page"], "quote": r["line"]}} for r in rows]
                    found.append((eff, doc["received_ts"], Cand("amendment", out, 1, doc["ref"], a.get("amendment_ref") or "amendment", eff=eff)))
            elif act["type"] == "annex_reference" and lane in act["lanes"]:
                frm, to = pdate(act["from"]), pdate(act["to"])
                if frm and frm <= pickup and (to is None or pickup <= to):
                    ann = None
                    for adoc, af in c.annexes:
                        if norm_name(af["data"].get("name")) == norm_name(act["annex"]):
                            ann = (adoc, af["data"])
                    if ann is None:
                        found.append((frm, doc["received_ts"], ("missing", act["annex"], act, doc)))
                    else:
                        adoc, ad = ann
                        rows = [r for r in ad["rates"] if r["lane"] == lane]
                        idx = 0
                        for i, p in enumerate(ad.get("periods") or []):
                            if pdate(p["from"]) <= pickup:
                                idx = i
                        out = [{"band": r["band"], "lo": r["lo"], "hi": r["hi"],
                                "v": Decimal(str(r["values"][idx] if idx < len(r["values"]) else r["values"][-1])),
                                "ev": {"doc": adoc["ref"], "page": r["page"], "quote": r["line"]}} for r in rows]
                        if out:
                            found.append((frm, adoc["received_ts"], Cand("annex", out, 1, adoc["ref"], act["annex"], eff=frm)))
    found.sort(key=lambda t: (t[0], t[1]))
    return found


def notice_authorised(w: World, c: Contract, fb: Feedback, x: dict, lane: str):
    """-> (ok, learned feedback item | None). x = rate_notice email fact with its doc."""
    doc = x["doc"]
    if x.get("quoted"):
        return False, None
    when = pdate(doc["received"])
    it = fb.accepted_rate(c.id, lane, pdate(x.get("effective_from")) or when, sender=doc["from_name"], effective_from=x.get("effective_from"))
    if not it:
        it = fb.accepted_rate(c.id, lane, pdate(x.get("effective_from")) or when)
    if it:
        return True, it
    p = c.person_by_email(doc["from_addr"])
    if p and "rates" in p["categories"] and p["party"] == c.carrier_party():
        return True, None
    if p:
        it = fb.authority(p["name"], "rates", c.id, when)
        if it:
            return True, it
    return False, None


def _notice_cand(w: World, c: Contract, fb: Feedback, lane: str, pickup):
    best = None
    for x in w.email_facts:
        if x["type"] != "rate_notice":
            continue
        ref = x.get("ref") or ""
        if "/" in ref and ref.split("/")[0] != c.id:
            continue
        if "/" not in ref and not (c.person_by_email(x["doc"]["from_addr"]) or c.id in " ".join(r.get("quote", "") for r in x.get("rows", []))):
            continue
        rows = [r for r in x["rows"] if r["lane"] == lane]
        if not rows:
            continue
        ef, et = pdate(x.get("effective_from")), pdate(x.get("effective_to"))
        if ef is None or ef > pickup or (et and pickup > et):
            continue
        ok, learned = notice_authorised(w, c, fb, x, lane)
        if not ok:
            continue
        out = [{"band": r["band"], "lo": r["lo"], "hi": r["hi"], "v": Decimal(str(r["rate"])),
                "ev": {"doc": x["doc"]["ref"], "page": 1, "quote": r["quote"]}} for r in rows]
        cand = Cand("notice", out, 2, x["doc"]["ref"], x.get("ref") or "rate notice", learned=learned, eff=ef)
        key = (ef, x["doc"]["received_ts"])
        if best is None or key > best[0]:
            best = (key, cand)
    return best[1] if best else None


def resolve_rate(w: World, c: Contract, fb: Feedback, lane: str, pickup) -> Resolution:
    eff = pdate(c.term("effective_date"))
    if eff and pickup < eff:
        return Resolution("none", why="pickup before the contract took effect")

    # If user feedback explicitly accepted a rate for this contract and lane
    acc = fb.accepted_rate(c.id, lane, pickup)
    if acc:
        txt = (acc.get("fact", {}).get("evidence") or "") + " " + (acc.get("note") or "")
        m_r = re.search(r"(\d+(?:\.\d+)?)\s*(?:/kg|per kg|INR/kg|\$|USD)", txt)
        if m_r:
            rate_v = Decimal(m_r.group(1))
            m_b = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*kg", txt)
            lo = float(m_b.group(1)) if m_b else 0.0
            hi = float(m_b.group(2)) if m_b else None
            quote_text = acc.get("fact", {}).get("evidence") or acc.get("note") or ""
            out_rows = [{"band": f"{lo}-{hi}" if hi else f"{lo}+", "lo": lo, "hi": hi, "v": rate_v,
                         "ev": {"doc": c.msa_doc["ref"], "page": 1, "quote": quote_text[:120]}}]
            cand = Cand("feedback_rate", out_rows, 0, "feedback", "accepted rate", learned=acc, eff=pdate(acc.get("scope", {}).get("valid_from")))
            return Resolution("ok", cand=cand)

    # Check if there is an active revised annex notice that is missing
    for x in w.email_facts:
        if x.get("type") == "revised_annex_notice" and x.get("contract") == c.id:
            a_eff = pdate(x.get("effective_from"))
            if a_eff and a_eff <= pickup:
                ann_name = x.get("annex")
                has_annex = any(norm_name(af["data"].get("name")) == norm_name(ann_name) for _, af in c.annexes)
                if not has_annex:
                    return Resolution("missing", missing=("missing", ann_name, {"text": x["quote"], "name": ann_name}, x["doc"]))

    msa = _msa_cand(c, lane, pickup)
    amds = _amend_cands(w, c, lane, pickup)
    amd = None
    if amds:
        valid_amds = [x[2] for x in amds if isinstance(x[2], Cand)]
        if len(valid_amds) >= 2:
            cand_latest = valid_amds[-1]
            cand_prev = valid_amds[-2]
            if cand_latest.eff == cand_prev.eff:
                r1_rows = {r["band"]: r["v"] for r in cand_latest.rows}
                r2_rows = {r["band"]: r["v"] for r in cand_prev.rows}
                if any(band in r2_rows and r1_rows[band] != r2_rows[band] for band in r1_rows):
                    pref = fb.precedence(c.id, lane, pickup)
                    if pref:
                        use = (pref["fact"].get("value") or {}).get("use")
                        amd_target = (pref["fact"].get("value") or {}).get("amendment")
                        chosen = None
                        for ac in valid_amds:
                            if amd_target and (amd_target == ac.label or amd_target in ac.label or ac.label in amd_target or amd_target.split("/")[-1] in ac.label or amd_target in ac.doc_ref or amd_target.split("/")[-1] in ac.doc_ref):
                                chosen = ac
                                break
                        if not chosen:
                            chosen = cand_latest if use in ("amendment", "latest") else cand_prev
                        chosen.learned = pref
                        return Resolution("ok", cand=chosen)
                    return Resolution("conflict", cand=cand_prev, alt=cand_latest)

        top = amds[-1][2]
        if isinstance(top, tuple):
            return Resolution("missing", missing=top)
        amd = top

    notice = _notice_cand(w, c, fb, lane, pickup)
    if notice and notice.learned:
        return Resolution("ok", cand=notice)
    if amd and notice:
        pref = fb.precedence(c.id, lane, pickup)
        if pref:
            use = (pref["fact"].get("value") or {}).get("use")
            chosen = notice if use == "notice" else amd
            chosen.learned = pref
            return Resolution("ok", cand=chosen)
        rule = c.term("notice_vs_amendment", "unranked")
        if rule == "amendment_wins":
            return Resolution("ok", cand=amd)
        if rule == "notice_wins":
            return Resolution("ok", cand=notice)
        return Resolution("conflict", cand=amd, alt=notice)
    cand = notice or amd or msa
    if cand is None:
        return Resolution("none", why="no rate for this lane")
    return Resolution("ok", cand=cand)


# ---------------------------------------------------------------------------------------------------------------------
def norm_desc(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", s or "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())      # spaces dropped: OCR output has none


def code_of(c: Contract, desc: str) -> str | None:
    n = norm_desc(desc)
    best = None
    for cc in c.d.get("charge_codes", []):
        for lab in cc["labels"] + [cc["label"]]:
            ln = norm_desc(lab)
            if ln == n:
                return cc["code"]
            if ln and (ln in n or n in ln) and min(len(ln), len(n)) >= 4:
                if best is None or len(ln) > best[0]:
                    best = (len(ln), cc["code"])
    if best:
        return best[1]
    dlow = (desc or "").lower()
    for code, synonyms in [
        ("FRT", ["freight", "linehaul", "ocean freight", "air freight", "cargo", "carriage", "express air", "air", "express", "standard", "ground", "line haul"]),
        ("FUEL", ["fuel", "baf", "fsc", "fuel adjustment"]),
        ("SEC", ["security"]),
        ("DLV", ["delivery"]),
        ("CUSTOMS", ["customs", "clearance"]),
        ("DG", ["dangerous", "hazmat"]),
        ("DRYICE", ["dry ice", "dryice"]),
        ("PEAK", ["peak"]),
        ("STOR", ["storage", "demurrage"]),
        ("HDL", ["handling", "special handling", "handling fee"]),
    ]:
        if any(s in dlow for s in synonyms):
            return code
    return None


def fee_of(c: Contract, code: str, lane: str | None = None):
    for a in c.d.get("accessorials", []):
        if a["code"] == code or (code == "HDL" and a.get("code") in ("HDL", "HANDLING")):
            if not lane or not a.get("lane") or a.get("lane") == lane:
                return a
    return None


def fuel_pct(c: Contract, pickup, lane: str | None = None):
    m = pickup.strftime("%Y-%m") if pickup else None
    for r in c.d.get("fuel", []):
        if m and r.get("month") == m:
            return r
        if lane and r.get("lane") == lane:
            return r
    return None


class Priced:
    def __init__(self):
        self.lines = []              # dicts: line, code, correct, diff, ev(list), why
        self.evidence = []
        self.lanes = set()           # (lane, rate period idx)
        self.min_tier = 1            # weakest pickup source used (1 best .. 4 worst)
        self.learned = None
        self.missing = None
        self.conflicts = []          # (lane, Resolution)
        self.authority_ok = True
        self.skipped = []

    @property
    def diff(self) -> Decimal:
        return sum((l["diff"] for l in self.lines), Decimal(0))


def price_invoice(w: World, rec: dict, c: Contract, fb: Feedback, pick: dict | None = None, exclude: set | None = None) -> Priced:
    """Reprice a normal invoice. pick={'lane': 'cand'|'alt'} chooses the side of a conflict. exclude = line idx to leave out."""
    d = rec["d"]
    doc = rec["doc"]
    out = Priced()
    exclude = exclude or set()
    pick = pick or {}
    by_awb: dict[str, list[dict]] = {}
    for ln in d["lines"]:
        if ln["kind"] != "charge" or ln.get("idx") in exclude:
            continue
        if ln.get("awb"):
            by_awb.setdefault(ln["awb"], []).append(ln)
        else:
            by_awb.setdefault(None, []).append(ln)

    def inv_ev(ln):
        return {"doc": doc["ref"], "page": ln.get("page", 1), "quote": ln["raw"]}

    for awb, lines in by_awb.items():
        if awb is None:
            _price_statement_lines(w, c, rec, lines, out, inv_ev)
            continue
        lane = next((l["lane"] for l in lines if l.get("lane")), None) or d.get("lane")
        if not lane and doc.get("subject"):
            m_subj = re.search(r"\b([A-Z]{3,4}-[A-Z]{3,4})\b", doc.get("subject", ""))
            if m_subj:
                lane = m_subj.group(1).upper()
        if not lane:
            m_lane = re.search(r"\b([A-Z]{2,4}[A-Z0-9]*-[A-Z]{2,4}[A-Z0-9]*)\b", "\n".join(doc.get("pages", [])))
            lane = m_lane.group(1).upper() if m_lane else None
        if not lane and c:
            c_lanes = {r["lane"] for r in c.d.get("rates", [])} | {r["lane"] for _, af in c.amendments for r in af["data"].get("rates", [])}
            if len(c_lanes) == 1:
                lane = list(c_lanes)[0]
        if not lane:
            for ef in w.email_facts:
                if norm_awb(ef.get("awb") or "") == norm_awb(awb or "") and ef.get("lane"):
                    lane = ef["lane"]
                    break
        line_date = next((l["line_date"] for l in lines if l.get("line_date")), None) or d.get("invoice_date")
        pdt, tier, pev = w.pickup(awb, line_date)
        if pdt is None:
            pdt = pdate(d.get("invoice_date")) or pdate(doc.get("received"))
            tier, pev = 4, None
        if pdt is None:
            continue
        out.min_tier = max(out.min_tier, tier)
        res = resolve_rate(w, c, fb, lane, pdt) if lane else Resolution("none")
        if res.status == "missing":
            out.missing = res.missing
            continue
        cand = None
        if res.status == "conflict":
            out.conflicts.append((lane, res))
            cand = res.alt if pick.get(lane) == "alt" else res.cand
        elif res.status == "ok":
            cand = res.cand
        if cand and cand.learned:
            out.learned = cand.learned
        if cand and cand.level > 2:
            out.authority_ok = False
        period_idx = 0
        for i, p in enumerate(c.d["periods"]):
            if pdate(p["from"]) <= pdt:
                period_idx = i
        if lane:
            out.lanes.add((lane, period_idx))
        correct_freight = Decimal(0)
        freight_seen = False
        base_by_lane: dict[str, Decimal] = {}
        for ln in sorted(lines, key=lambda l: 0 if code_of(c, l["desc"]) == "FRT" else 1):
            code = code_of(c, ln["desc"])
            ln["_code"] = code
            billed = money(ln["amount"])
            corr, why, evs = None, "", []
            if code == "FRT" and cand and ln.get("unit") in ("kg", None) and ln.get("qty"):
                kg = float(ln["qty"])
                vdiv = c.term("volumetric_divisor")
                dims = d.get("dimensions")
                actual_gross = None
                for ef in w.email_facts:
                    if norm_awb(ef.get("awb") or "") == norm_awb(awb or ""):
                        if ef.get("actual_kg") is not None:
                            actual_gross = ef["actual_kg"]
                        if ef.get("dimensions") and not dims:
                            dims = ef["dimensions"]
                a_doc = w.awbs.get(awb) or w.awbs.get(norm_awb(awb or ""))
                if a_doc and a_doc.get("gross_weight"):
                    actual_gross = actual_gross or a_doc["gross_weight"]
                if vdiv and dims:
                    vol_kg = (dims["pcs"] * dims["l"] * dims["w"] * dims["h"]) / vdiv
                    correct_kg = max(actual_gross or 0.0, vol_kg)
                    if 0 < correct_kg < kg:
                        kg = correct_kg
                rate, mn, rev = cand.rate(kg)
                if rate is not None:
                    corr = money(rate * Decimal(str(kg)))
                    if mn is not None and corr < mn:
                        corr = mn
                    evs = rev + [e for e in (clause_ev(c, "3.2"), clause_ev(c, "3.4")) if e] + ([pev] if pev else [])
                    why = "rate"
                    correct_freight += corr
                    freight_seen = True
            elif code == "FUEL":
                fp = fuel_pct(c, pdt, lane)
                f_pct = Decimal(str(fp["pct"])) if fp else (Decimal(str(ln["pct"])) if ln.get("pct") else None)
                if f_pct is None:
                    for r in c.d.get("rates", []):
                        if r.get("lane") == lane and r.get("fuel_pct") is not None:
                            f_pct = Decimal(str(r["fuel_pct"]))
                            fp = {"page": r.get("page", 1), "line": r.get("line", "")}
                            break
                if f_pct is not None:
                    base = correct_freight if freight_seen else (money(ln["base"]) if ln.get("base") else None)
                    if base is not None:
                        corr = money(base * f_pct / 100)
                        evs = ([{"doc": c.msa_doc["ref"], "page": fp["page"], "quote": fp["line"]}] if fp else [inv_ev(ln)]) + [e for e in (clause_ev(c, "4.1"), clause_ev(c, "3.3")) if e] + ([pev] if pev else [])
                        why = "fuel"
            elif code == "SEC":
                fe = fee_of(c, "SEC")
                kg = ln.get("qty")
                if fe and kg:
                    corr = money(Decimal(str(fe["fee"])) * Decimal(str(kg)))
                    evs = [{"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}] + [e for e in (clause_ev(c, "4.2"),) if e]
                    why = "security"
                elif fe:
                    corr = money(Decimal(str(fe["fee"])))
                    evs = [{"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}] + [e for e in (clause_ev(c, "4.2"),) if e]
                    why = "security"
                else:
                    sec_fee = None
                    for r in c.d.get("rates", []):
                        if r.get("lane") == lane and r.get("security") is not None:
                            sec_fee = Decimal(str(r["security"]))
                            break
                    if sec_fee is not None:
                        corr = money(sec_fee)
                        evs = [e for e in (clause_ev(c, "3.4"),) if e]
                        why = "security"
                    else:
                        corr = billed
                        evs = [inv_ev(ln)]
                        why = "security"
            elif code in ("DG", "DRYICE"):
                corr, evs, why = _dg_line(w, c, awb, code, ln)
            elif code == "PEAK":
                corr, evs, why = _peak_line(w, c, ln, pdt)
            elif code == "STOR":
                corr, evs, why = _storage_line(w, c, awb, ln)
            elif code == "DLV":
                corr, evs, why = _delivery_line(w, c, awb, ln)
            elif code == "CUSTOMS":
                corr, evs, why = _customs_line(w, c, awb, ln)
            elif code in ("HDL", "HANDLING") or (code and fee_of(c, code, lane)):
                fe = fee_of(c, code or "HDL", lane)
                if fe:
                    corr = money(Decimal(str(fe["fee"])))
                    evs = [{"doc": c.msa_doc["ref"], "page": fe.get("page", 1), "quote": fe.get("line", "")}]
                    why = fe.get("name", code).lower()
                else:
                    corr = billed
                    evs = [inv_ev(ln)]
                    why = "handling"
            if corr is None:
                out.skipped.append(ln)
                continue
            diff = billed - corr
            out.lines.append({"line": ln, "code": code, "correct": corr, "billed": billed, "diff": diff, "why": why,
                              "ev": [inv_ev(ln)] + evs, "awb": awb, "lane": lane})
    return out


def _price_statement_lines(w, c, rec, lines, out, inv_ev):
    """Monthly programme / account fees: billed rate must equal the Annex D fee."""
    for ln in lines:
        code = code_of(c, ln["desc"])
        ln["_code"] = code
        fe = fee_of(c, code) if code else None
        if not fe or "month" not in (fe.get("basis") or ""):
            continue
        qty = Decimal(str(ln["qty"])) if ln.get("qty") else Decimal(1)
        corr = money(Decimal(str(fe["fee"])) * qty)
        billed = money(ln["amount"])
        out.lines.append({"line": ln, "code": code, "correct": corr, "billed": billed, "diff": billed - corr, "why": "fee",
                          "ev": [inv_ev(ln), {"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}], "awb": None, "lane": None})


def _dg_line(w, c, awb, code, ln):
    dg = w.dgds.get(awb) or w.dgds.get(norm_awb(awb))
    fe = fee_of(c, code)
    if not dg or not fe:
        return None, [], ""
    ev = [{"doc": dg["doc"]["ref"], "page": 1, "quote": _dgd_quote(w, dg)}]
    if dg["other_dg"]:
        expected = "DG"
        cl = clause_ev(c, "5.3") or clause_ev(c, "5.1")
    elif dg["refrigerant_only"]:
        expected = "DRYICE"
        cl = clause_ev(c, "5.2")
    else:
        return None, [], ""
    if cl:
        ev.append(cl)
    ev.append({"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]})
    if code != expected:
        # a fee for the wrong kind of goods. A replacement fee for the right kind is not charged here (undercharge is ignored)
        return money(0), ev, "dg_wrong_fee"
    return money(Decimal(str(fe["fee"]))), ev, "dg_fee"


def _dgd_quote(w, dg):
    pages = w.by_ref[dg["doc"]["ref"]]["pages"]
    txt = "\n".join(pages)
    m = re.search(r"UN\d{4}[^\n]*", txt)
    return m.group(0).strip() if m else "UN"


def _storage_line(w, c, awb, ln):
    ev_list = w.events(awb)
    free = c.term("storage_free_days")
    fe = fee_of(c, "STOR")
    if not ev_list or free is None or not fe:
        return None, [], ""
    release = next((e for e in ev_list if e["event"] in ("DELIVERED", "COLLECTED_BY_CONSIGNEE")), None)
    if not release:
        return None, [], ""
    arrivals = [e for e in ev_list if e["event"] == "ARRIVED_FACILITY" and e["date"] <= release["date"]]
    if not arrivals:
        return None, [], ""
    arr = arrivals[-1]
    days = max(0, (pdate(release["date"]) - pdate(arr["date"])).days - free)
    corr = money(Decimal(str(fe["fee"])) * days)
    ev = [{"doc": arr["doc"]["ref"], "page": arr["page"], "quote": arr["line"]},
          {"doc": release["doc"]["ref"], "page": release["page"], "quote": release["line"]},
          {"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}]
    cl = clause_ev(c, "6.1")
    if cl:
        ev.append(cl)
    return corr, ev, "storage"


def _delivery_line(w, c, awb, ln):
    ev_list = w.events(awb)
    fe = fee_of(c, "DLV")
    if not fe:
        return None, [], ""
    if not ev_list:
        return money(Decimal(str(fe["fee"]))), [{"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}], "delivery_fee"
    col = next((e for e in ev_list if e["event"] == "COLLECTED_BY_CONSIGNEE"), None)
    dlv = next((e for e in ev_list if e["event"] == "DELIVERED"), None)
    ev = []
    if col and not dlv:
        ev = [{"doc": col["doc"]["ref"], "page": col["page"], "quote": col["line"]}]
        cl = clause_ev(c, "6.2")
        if cl:
            ev.append(cl)
        return money(0), ev, "no_delivery"
    if dlv:
        return money(Decimal(str(fe["fee"]))), [{"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}], "delivery_fee"
    return None, [], ""


def _customs_line(w, c, awb, ln):
    fe = fee_of(c, "CUSTOMS")
    holds = [x for x in w.email_facts if x["type"] == "customs_hold" and norm_awb(x["awb"]) == norm_awb(awb) and not x.get("quoted")]
    if not fe or not holds:
        return None, [], ""
    h = holds[-1]
    txt = (h.get("reason") or "") + " " + (h.get("reason_quote") or "")
    carrier_fault = bool(re.search(r"carrier|error in documents|filed by the carrier|prepared by the carrier|omission", txt, re.I)) \
        and not re.search(r"shipper'?s? (?:import )?(?:permit|document)|SHIPPER_", txt, re.I)
    ev = [{"doc": h["doc"]["ref"], "page": 1, "quote": h.get("reason_quote") or h["quote"]}]
    cl = clause_ev(c, "6.3")
    if cl:
        ev.append(cl)
    if carrier_fault:
        return money(0), ev, "customs_carrier_fault"
    return money(Decimal(str(fe["fee"]))), ev, "customs_fee"


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}


def _peak_line(w, c, ln, pickup):
    fe = fee_of(c, "PEAK")
    if not fe or not ln.get("qty"):
        return None, [], ""
    text = " ".join(w.by_ref[c.msa_doc["ref"]]["pages"])
    m = re.search(r"PEAK[^\n]*?pickups in\s+([A-Za-z]+)\s+to\s+([A-Za-z]+)", re.sub(r"\s+", " ", text), re.I)
    if not m or m.group(1).lower() not in MONTHS or m.group(2).lower() not in MONTHS:
        return None, [], ""
    a, b = MONTHS[m.group(1).lower()], MONTHS[m.group(2).lower()]
    inside = (a <= pickup.month <= b) if a <= b else (pickup.month >= a or pickup.month <= b)
    ev = [{"doc": c.msa_doc["ref"], "page": fe["page"], "quote": fe["line"]}]
    if not inside:
        return money(0), ev, "peak_out_of_season"
    return money(Decimal(str(fe["fee"])) * Decimal(str(ln["qty"]))), ev, "peak"
