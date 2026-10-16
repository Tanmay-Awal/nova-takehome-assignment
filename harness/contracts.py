"""Contracts, amendments and annexes -> structured terms.

Two layers:
  1. tables.py parses the regular annex tables exactly (rates, fuel, accessorials, charge codes, FX, Schedule 1).
  2. Clause terms (term, rebate tiers, payment terms, late-fee rule ...) are read with strict patterns for the wordings
     we have seen. Any term the patterns cannot settle is listed in `unparsed` and sent to the model (llm.py), whose
     answer is only accepted if every number in it appears in the clause text it was shown.

Every term keeps the clause number it came from, so the engine can quote the clause as evidence.
"""
from __future__ import annotations

import re

import tables

DATE = r"\d{4}-\d{2}-\d{2}"
NUM = r"\d[\d,]*(?:\.\d+)?"


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def _date_in(text: str, which: int = -1) -> str | None:
    ds = re.findall(DATE, text)
    return ds[which] if ds else None


def _extract_date(text: str) -> str | None:
    from invoices import parse_date
    ds = re.findall(DATE, text)
    if ds:
        return ds[-1]
    for m in re.finditer(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", text, re.I):
        d = parse_date(m.group(0))
        if d:
            return d
    return None


def extract_days(text: str) -> int | None:
    m = re.search(r"\b(?:(\d+)|(one|two|three|four|five|six|seven|eight|nine|ten|fourteen|fifteen|twenty|thirty|forty|fifty|sixty|ninety))\s*(?:\((\d+)\)\s*)?[- ]?(?:calendar\s*)?days?\b", text, re.I)
    if not m:
        return None
    if m.group(1): return int(m.group(1))
    if m.group(3): return int(m.group(3))
    word_map = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'fourteen':14,'fifteen':15,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'ninety':90}
    return word_map.get(m.group(2).lower())


# ---- clause scalars ------------------------------------------------------------------------------------------------------
def parse_terms(clauses: dict[str, dict], text: str = "") -> tuple[dict, list[str]]:
    """-> (terms, unparsed). terms[name] = {'value': ..., 'clause': '10.2'} so the clause can be quoted."""
    T: dict[str, dict] = {}
    unparsed: list[str] = []

    def put(name, value, clause):
        T[name] = {"value": value, "clause": clause}

    def txt(c):
        return clauses[c]["text"] if c in clauses else ""

    # term
    t = txt("2.1")
    if t and _extract_date(t):
        put("effective_date", _extract_date(t), "2.1")
    else:
        for cnum, cl in clauses.items():
            if re.search(r"effective date|enters into force|commencing", cl["text"], re.I):
                ed = _extract_date(cl["text"])
                if ed:
                    put("effective_date", ed, cnum)
                    break
        else:
            if text:
                m_eff = re.search(r"\bEFFECTIVE DATE\s*:?\s*([A-Za-z0-9,\s]+?)(?:\n|$)", text, re.I)
                if m_eff:
                    ed = _extract_date(m_eff.group(1))
                    if ed:
                        put("effective_date", ed, "2.1")
            if "effective_date" not in T:
                unparsed.append("effective_date")

    t = txt("2.2")
    if t and _extract_date(t):
        put("term_end", _extract_date(t), "2.2")
        m = re.search(r"(\d+)\s*months?", t)
        if m:
            put("term_months", int(m.group(1)), "2.2")
    else:
        for cnum, cl in clauses.items():
            if re.search(r"remain in full force and effect until|expiration date|expire[s]? on", cl["text"], re.I):
                te = _extract_date(cl["text"])
                if te:
                    put("term_end", te, cnum)
                    break
        else:
            if text:
                m_end = re.search(r"\b(?:END DATE|EXPIRATION DATE|TERMINATION DATE)\s*:?\s*([A-Za-z0-9,\s]+?)(?:\n|$)", text, re.I)
                if m_end:
                    te = _extract_date(m_end.group(1))
                    if te:
                        put("term_end", te, "2.2")
            if "term_end" not in T:
                unparsed.append("term_end")

    # renewal / auto-renews
    found_renewal = False
    for cnum in ("2.3", "2.2", "2.1"):
        t = txt(cnum)
        if not t:
            continue
        neg = re.search(r"(?:does|will|shall|do) not (?:\w+ ){0,2}(?:renew|continue)|not renew|no automatic renewal|ends? at the end of the initial term", t, re.I)
        pos = re.search(r"(?<!not )\brenews? automatically|automatically renews?|renews? for (?:successive|further|additional|consecutive)|is renewed automatically", t, re.I)
        if neg and not re.search(r"(?<!not )\brenews? (?:for|automatically) (?:successive|further|additional|consecutive)", t, re.I):
            put("auto_renews", False, cnum)
            found_renewal = True
            break
        elif pos and not neg:
            put("auto_renews", True, cnum)
            found_renewal = True
            if re.search(r"one\s*\(\s*1\s*\)\s*year|1\s*year", t, re.I):
                put("renewal_term_months", 12, cnum)
            elif re.search(r"(\d+)\s*months?", t):
                put("renewal_term_months", int(re.search(r"(\d+)\s*months?", t).group(1)), cnum)
            nd = extract_days(t)
            if nd:
                put("notice_days", nd, cnum)
            nd_m = re.search(r"Notice Deadline:\s*([A-Za-z0-9,\s]+?)\)", t, re.I)
            if nd_m:
                from invoices import parse_date
                d = parse_date(nd_m.group(1))
                if d:
                    put("notice_deadline", d, cnum)
            break
    if not found_renewal:
        unparsed.append("auto_renewal")

    # free storage days
    m = re.search(r"-\s*(\d+)\s*free days", txt("6.1"))
    if m:
        put("storage_free_days", int(m.group(1)), "6.1")

    # volume rebate
    t = txt("7.1")
    tiers = [(_f(a), _f(b)) for a, b in re.findall(r"QS\s*>=\s*(?:USD|INR|EUR)?\s*(" + NUM + r")\s*:\s*(" + NUM + r")\s*%", t)]
    if tiers:
        put("rebate_tiers", sorted(tiers), "7.1")
        if re.search(r"applies to all (?:QS|Qualifying Spend)", t, re.I):
            put("rebate_basis", "all", "7.1")
        elif re.search(r"excess|incremental|marginal|portion|above the threshold|slice", t, re.I):
            put("rebate_basis", "marginal", "7.1")
        else:
            unparsed.append("rebate_basis")
    else:
        for cnum, cl in clauses.items():
            m_reb = re.search(r"quarterly volume rebate of\s*(" + NUM + r")\s*%.*?(?:reaches|exceeds)\s*[\$]?([\d,]+(?:\.\d+)?)", cl["text"], re.I)
            if m_reb:
                put("rebate_tiers", [(_f(m_reb.group(2)), _f(m_reb.group(1)))], cnum)
                put("rebate_basis", "all", cnum)
                break
        else:
            unparsed.append("rebate_tiers")

    m = re.search(r"(\d+)\s*days", txt("7.3"))
    if m:
        put("rebate_due_days", int(m.group(1)), "7.3")
    else:
        for cnum, cl in clauses.items():
            if re.search(r"rebate credit note", cl["text"], re.I):
                rd = extract_days(cl["text"])
                if rd:
                    put("rebate_due_days", rd, cnum)
                    break
        else:
            unparsed.append("rebate_due_days")

    # handling margin
    for c, nm in (("8.1", "handling_margin"), ("8.2", "margin_step_down")):
        t = txt(c)
        if t and re.search(r"not applicable", t, re.I):
            put(nm, None, c)
        elif t:
            unparsed.append(nm)

    # annual improvement credit
    t = txt("9.1")
    if t and re.search(r"not applicable", t, re.I):
        put("annual_credit_pct", None, "9.1")
    else:
        found_ac = False
        for cnum, cl in clauses.items():
            if re.search(r"annual\s*(?:improvement\s*)?credit|promised\s*credit", cl["text"], re.I):
                pm = re.search(r"(" + NUM + r")\s*%", cl["text"])
                dm = re.search(r"(\d+)\s*days", cl["text"])
                m_fix = re.search(r"(?:credit of|credit amount of)\s*(?:(USD|INR|EUR|GBP)\s*)?([0-9,]+(?:\.\d+)?)", cl["text"], re.I)
                m_cy = re.search(r"Contract Year\s*(\d+)\s*\((CY\d+)\)\s*runs from\s*([A-Za-z0-9, ]+?)\s*to\s*([A-Za-z0-9, ]+)", cl["text"], re.I)
                days_v = int(dm.group(1)) if dm else 45
                if pm:
                    put("annual_credit_pct", _f(pm.group(1)), cnum)
                    put("annual_credit_days", days_v, cnum)
                    found_ac = True
                elif m_fix:
                    put("annual_credit_amount", _f(m_fix.group(2)), cnum)
                    if m_fix.group(1):
                        put("annual_credit_currency", m_fix.group(1).upper(), cnum)
                    put("annual_credit_days", days_v, cnum)
                    if m_cy:
                        from invoices import parse_date
                        put("annual_credit_cy", {m_cy.group(2): (parse_date(m_cy.group(3)), parse_date(m_cy.group(4)))}, cnum)
                    found_ac = True
                break
        if not found_ac and t:
            unparsed.append("annual_credit")

    # payment terms
    m = re.search(r"(\d+)\s*days", txt("10.1"))
    if m:
        put("payment_days", int(m.group(1)), "10.1")
    else:
        for cnum, cl in clauses.items():
            nm = re.search(r"Net\s*(\d+)", cl["text"], re.I)
            if nm:
                put("payment_days", int(nm.group(1)), cnum)
                break
        else:
            unparsed.append("payment_days")

    # late fees
    t = txt("10.2")
    gm = re.search(r"more than\s*(\d+)\s*days", t, re.I)
    rm = re.search(r"(" + NUM + r")\s*%\s*per month", t, re.I)
    if gm and rm:
        put("late_fee_grace_days", int(gm.group(1)), "10.2")
        put("late_fee_pct_per_month", _f(rm.group(1)), "10.2")
    else:
        # Search across all clauses for interest and grace
        for cnum, cl in clauses.items():
            rm = re.search(r"(?:interest|fee|charge)\s*(?:at|of|:)?\s*(" + NUM + r")\s*%\s*per month", cl["text"], re.I) or re.search(r"(" + NUM + r")\s*%\s*per month", cl["text"], re.I)
            if rm:
                put("late_fee_pct_per_month", _f(rm.group(1)), cnum)
                if re.search(r"simple", cl["text"], re.I):
                    put("late_fee_compounds", False, cnum)
            if re.search(r"grace\s*period", cl["text"], re.I):
                gd = extract_days(cl["text"])
                if gd is not None:
                    put("late_fee_grace_days", gd, cnum)
        if "late_fee_pct_per_month" not in T:
            unparsed.append("late_fee")

    t = txt("10.3")
    if "late_fee_compounds" not in T:
        if re.search(r"simple|principal only|only on the principal|not compound|on the principal (?:amount )?only", t, re.I):
            put("late_fee_compounds", False, "10.3")
        elif re.search(r"principal plus|added to the (?:overdue )?balance|compound", t, re.I):
            put("late_fee_compounds", True, "10.3")
        else:
            unparsed.append("late_fee_compounds")

    # volumetric divisor
    for cnum, cl in clauses.items():
        div_m = re.search(r"volumetric weight.*?/\s*(\d{4,5})|formula.*?/\s*(\d{4,5})|divisor\s*(\d{4,5})", cl["text"], re.I)
        if div_m:
            put("volumetric_divisor", int(next(g for g in div_m.groups() if g)), cnum)
            break

    # who wins between a rate notice and an amendment
    t = (txt("13.3") + " " + txt("14.1") + " " + txt("14.2"))
    if re.search(r"neither prevails|resolve the difference jointly|does not rank", t, re.I):
        put("notice_vs_amendment", "unranked", "13.3")
    elif re.search(r"rate notice[^.]*prevail|notice prevails|correspondence prevails", t, re.I):
        put("notice_vs_amendment", "notice_wins", "14.2")
    elif re.search(r"amendment prevails over (?:any )?(?:rate )?notice|amendment[^.]*prevails[^.]*notice", t, re.I):
        put("notice_vs_amendment", "amendment_wins", "14.2")
    else:
        unparsed.append("notice_vs_amendment")
    m = re.search(r"within\s*(\d+)\s*days of the invoice date", txt("13.1"))
    if m:
        put("dispute_window_days", int(m.group(1)), "13.1")
    return T, unparsed


# ---- whole contract -------------------------------------------------------------------------------------------------------
def parse_msa(pages: list[str]) -> dict:
    text = "\n".join(pages)
    m = re.search(r"Agreement\s+No\.?\s*([A-Z0-9][A-Z0-9-]+)", text)
    if not m:
        m = re.search(r"(?:Agreement|Contract)\s*(?:No\.?|ID|Reference|#)\s*[:.]?\s*([A-Z0-9][A-Z0-9-]+)", text, re.I)
        if m and m.group(1).upper() in ("FOR", "AND", "THE", "BETWEEN", "WITH", "BY", "THIS", "DATED", "OF"):
            m = None
    if not m:
        m = re.search(r"\b([A-Z]{2,4}-[A-Z]{2,4}-[A-Z0-9-]+)\b", text)
    cid = m.group(1).upper() if m else None
    clauses = tables.split_clauses(pages)
    periods = tables.parse_periods(pages)
    rates = tables.parse_rates(pages, len(periods))
    cur = None
    cm = re.search(r"Annex A[^\n]*\((USD|INR|EUR|GBP)\s+per", text)
    if cm:
        cur = cm.group(1)
    if not cur:
        cm = re.search(r"\b(?:currency|rates\s+in|amounts\s+in)\s*[:.]?\s*([A-Z]{3})\b", text, re.I)
        if cm and cm.group(1).upper() in ("USD", "INR", "EUR", "GBP"):
            cur = cm.group(1).upper()
    if not cur:
        cm = re.search(r"\b(USD|INR|EUR|GBP)\b", text)
        if cm:
            cur = cm.group(1)
    terms, unparsed = parse_terms(clauses, text)
    sched = tables.parse_schedule1(pages)
    parties = re.findall(r"\n(?:\(\d\))?\s*([A-Z][^\n]*?)\s*,\s*whose principal office[^\n]*?\(the (Shipper|Carrier)\)", text)
    return {"doc_type": "msa", "contract_id": cid, "currency": cur, "periods": periods, "rates": rates,
            "fuel": tables.parse_fuel(pages), "accessorials": tables.parse_accessorials(pages),
            "charge_codes": tables.parse_charge_codes(pages), "fx": tables.parse_fx(pages), "schedule1": sched,
            "terms": terms, "unparsed": unparsed,
            "clauses": {k: v for k, v in clauses.items()}, "signed": bool(re.search(r"Signed for and on behalf", text))}


def parse_amendment(pages: list[str]) -> dict:
    text = "\n".join(pages)
    flat = re.sub(r"\s+", " ", text)
    ref = re.search(r"Amendment\s*(?:reference|ID|No\.?|Number)?\s*:?\s*([A-Z0-9][A-Z0-9-]*/AMD-\d+|AMD-\d+)", flat, re.I)
    amd_ref = ref.group(1) if ref else None
    cid = amd_ref.split("/")[0] if amd_ref else (
        (re.search(r"Amendment No\.?\s*\d+\s+to\s+(?:Master Services Agreement \([^)]*\) )?([A-Z][A-Z0-9-]+)", flat) or [None, None])[1]
        or (re.search(r"([A-Z0-9-]+)[/_]AMD[-_]?\d+", flat) or [None, None])[1]
    )
    if cid and cid.upper() in ("FOR", "AND", "THE", "BETWEEN", "THIS", "OF", "TO"):
        cid = None
    if not cid:
        m = re.search(r"\b([A-Z]{2,4}-[A-Z]{2,4}-[A-Z0-9-]+)\b", flat)
        if m:
            cid = m.group(1).upper()

    eff_str = None
    eff_m = re.search(r"Effective\s*(?:Date|from)?\s*[:.]?\s*([A-Za-z0-9, /.-]+?)(?:\.|\n|$)", text, re.I)
    if eff_m:
        from invoices import parse_date
        eff_str = parse_date(eff_m.group(1).strip())
    if not eff_str:
        m_d = re.search(r"Effective from\s+(" + DATE + ")", flat) or re.search(r"\b(\d{4}-\d{2}-\d{2})\b", flat)
        if m_d:
            eff_str = m_d.group(1)

    rates = tables.parse_rates(pages, 1)

    # Prose rate revision clauses, e.g.:
    # "Annex A, Lane DEL-SFO, Weight Band 100.1 - 500 kg: The Base Rate is hereby changed from INR 165.00 per kg to INR 158.00 per kg"
    for pi, page_text in enumerate(pages, 1):
        for pm in re.finditer(
            r"Lane\s+([A-Z0-9-]+).*?Weight\s*Band\s*([0-9.]+)\s*-\s*([0-9.]+)\s*(?:kg)?.*?to\s+(?:INR|USD|EUR|GBP)?\s*([0-9.]+)",
            page_text, re.I | re.DOTALL
        ):
            lane_name = pm.group(1).upper()
            lo = float(pm.group(2))
            hi = float(pm.group(3))
            new_rate = float(pm.group(4))
            cur_m = re.search(r"\b(INR|USD|EUR|GBP)\b", pm.group(0), re.I)
            cur = cur_m.group(1).upper() if cur_m else None
            rates.append({
                "lane": lane_name,
                "band": f"{pm.group(2)}-{pm.group(3)}",
                "lo": lo,
                "hi": hi,
                "values": [new_rate],
                "currency": cur,
                "page": pi,
                "line": pm.group(0).strip()
            })

    # paragraph-level actions
    actions = []
    paras = re.split(r"(?:^|\n)(?=\d+\.\s)", text)
    for p in paras:
        pf = re.sub(r"\s+", " ", p).strip()
        if not re.match(r"\d+\.\s", pf):
            continue
        pf = re.split(r"\s(?=All other terms|This Amendment may|Executed by)", pf)[0].strip()
        pm = re.search(r"(Annex A rev \d+)\s*\(attached\)\s*applies from\s*(" + DATE + r")(?:\s*to\s*(" + DATE + r"))?\s*to lane\(s\)\s*([A-Z0-9, -]+?)\.?\s*$", pf) \
            or re.search(r"(Annex A rev \d+)\s*\(attached\)\s*applies from\s*(" + DATE + r")()\s*to lane\(s\)\s*([A-Z0-9, -]+?)\.?(?:\s|$)", pf)
        if pm:
            actions.append({"type": "annex_reference", "annex": pm.group(1), "from": pm.group(2),
                            "to": pm.group(3) or None,
                            "lanes": [x.strip() for x in re.split(r"[ ,]+", pm.group(4).strip()) if re.fullmatch(r"[A-Z0-9-]+", x.strip())],
                            "text": pf})
        elif (re.search(r"deleted and replaced with the following", pf, re.I) or re.search(r"(?:changed|revised|reduced|increased)\s+from.*?to", pf, re.I) or re.search(r"Base Rate is hereby changed", pf, re.I)) and rates:
            per = "every period" if re.search(r"for every period", pf, re.I) else None
            actions.append({"type": "replace_rates", "periods": per, "text": pf})
        elif re.search(r"extend|extended|extension", pf, re.I) and re.search(DATE, pf):
            actions.append({"type": "term_extension", "new_end": re.findall(DATE, pf)[-1], "text": pf})
        else:
            actions.append({"type": "other", "text": pf})

    if rates and not any(a["type"] == "replace_rates" for a in actions):
        actions.append({"type": "replace_rates", "text": "replace rates from amendment"})

    is_signed = bool(re.search(r"Signed for and on behalf|Executed by|Signed by|Agreed and accepted|By:", text, re.I)) or not bool(re.search(r"\b(?:draft|unsigned)\b", text, re.I))
    return {"doc_type": "amendment", "contract_id": cid, "amendment_ref": amd_ref, "effective_from": eff_str,
            "rates": rates, "actions": actions, "signed": is_signed}


def parse_annex(pages: list[str]) -> dict:
    """A separately delivered annex ('Annex A rev 2'): its name, the contract it belongs to, its rate rows and dates."""
    text = "\n".join(pages)
    flat = re.sub(r"\s+", " ", text)
    nm = re.search(r"(Annex [A-Z] rev \d+)", flat, re.I)
    cm = re.search(r"\b([A-Z]{2,4}-[A-Z]{2}-[A-Z]{2,4}-[A-Z0-9]+)\b", flat)
    periods = tables.parse_periods(pages)
    return {"doc_type": "annex", "name": nm.group(1) if nm else None, "contract_id": cm.group(1) if cm else None,
            "periods": periods, "rates": tables.parse_rates(pages, max(1, len(periods))),
            "effective_from": (re.search(r"(?:applies from|effective from|from)\s+(" + DATE + ")", flat, re.I) or [None, None])[1],
            "effective_to": (re.search(r"\bto\s+(" + DATE + ")", flat) or [None, None])[1],
            "lanes": sorted({r["lane"] for r in tables.parse_rates(pages, 1)})}
