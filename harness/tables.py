"""Deterministic parsers for the regular, tabular parts of the documents (no model involved).

Tables are the one place a model can silently mistype a number, and their format is stable across contracts, so they are
parsed with small tolerant parsers. Each parser returns [] when it finds nothing; understand.py then falls back to the
model for that table.

Everything returns the exact source line too (`line`), because evidence quotes must be copied from the document.
"""
from __future__ import annotations

import re
from datetime import date

DATE = r"\d{4}-\d{2}-\d{2}"
NUM = r"-?\d[\d,]*(?:\.\d+)?"


def n(s: str) -> float:
    return float(s.replace(",", ""))


def lines_of(pages: list[str]):
    for pi, p in enumerate(pages, 1):
        for ln in p.split("\n"):
            yield pi, ln.strip()


# ---- contract annexes --------------------------------------------------------------------------------------------------
def parse_periods(pages) -> list[dict]:
    """'Period P1: pickups 2034-10-20 to 2035-04-19'"""
    out = []
    for pi, ln in lines_of(pages):
        m = re.match(rf"^Period\s+(\w+)\s*:\s*pickups\s+({DATE})\s+to\s+({DATE})", ln, re.I)
        if m:
            out.append({"name": m.group(1).upper(), "from": m.group(2), "to": m.group(3), "page": pi, "line": ln})
    return out


def parse_rates(pages, n_periods: int) -> list[dict]:
    """'USS2-INN1 0-44.5 kg 8.98 8.94' / 'USS2-INN1 minimum charge 91.00 91.00' / '300+ kg'.
    Also supports header-based lane sections ('Lane: DEL-SFO') and markdown pipe tables."""
    out = []
    lane_pat = r"([A-Z]{2,4}[A-Z0-9]*-[A-Z]{2,4}[A-Z0-9]*)"
    curr_lane = None
    n_vals = max(1, n_periods)
    curr_band = None

    for pi, raw_ln in lines_of(pages):
        lm = re.search(rf"\b(?:Lane|Route)\s*(?:[A-Z]\b)?\s*:?\s*\(?{lane_pat}\)?", raw_ln, re.I) or re.search(rf"\bLane\s*:?\s*{lane_pat}", raw_ln, re.I)
        if lm:
            curr_lane = lm.group(1).upper()
            curr_band = None
            continue

        # Prose: Rate for DEL-SFO (100.1 - 500 kg) per AMD-1 is INR 158.00/kg or Annex A Rate: DEL-SFO (100.1 - 500 kg)...
        m_prose = re.search(rf"(?:Annex\s+[A-Z]\s+)?Rate\s*(?:for|:)\s*{lane_pat}\s*\(\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:kg)?\)[^.]*?(?:is|at|to)\s*(?:(USD|INR|EUR|GBP)\s*)?({NUM})", raw_ln, re.I)
        m_direct = re.search(rf"^{lane_pat}\s*\(\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:kg)?\)\s*:\s*(?:Base\s*Rate\s*)?(?:(USD|INR|EUR|GBP)\s*)?({NUM})", raw_ln, re.I)
        m_match = m_prose or m_direct
        if m_match:
            p_lane = m_match.group(1).upper()
            curr_lane = p_lane
            p_lo = float(m_match.group(2))
            p_hi = float(m_match.group(3))
            p_cur = (m_match.group(4) or "USD").upper()
            p_val = n(m_match.group(5))
            out.append({"lane": p_lane, "band": f"{m_match.group(2)}-{m_match.group(3)}", "lo": p_lo, "hi": p_hi,
                        "values": [p_val], "currency": p_cur, "page": pi, "line": raw_ln})
            continue

        if curr_lane:
            m_wb = re.search(r"Weight\s*Band\s*:?\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:kg)?", raw_ln, re.I)
            if m_wb:
                curr_band = (float(m_wb.group(1)), float(m_wb.group(2)), f"{m_wb.group(1)}-{m_wb.group(2)}")
                continue
            m_base = re.search(rf"Base\s*Rate\s*:?\s*(?:(USD|INR|EUR|GBP)\s*)?({NUM})", raw_ln, re.I)
            if m_base and curr_band:
                b_cur = (m_base.group(1) or "USD").upper()
                b_val = n(m_base.group(2))
                out.append({"lane": curr_lane, "band": curr_band[2], "lo": curr_band[0], "hi": curr_band[1],
                            "values": [b_val], "currency": b_cur, "page": pi, "line": raw_ln})
                curr_band = None
                continue

            m_r = re.search(rf"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*kg\s*:\s*\$?\s*({NUM})", raw_ln, re.I)
            m_p = re.search(rf"^(\d+(?:\.\d+)?)\+\s*kg\s*:\s*\$?\s*({NUM})", raw_ln, re.I)
            m_f = re.search(r"Fuel\s*(?:surcharge)?\s*:\s*(\d+(?:\.\d+)?)\s*%", raw_ln, re.I)
            m_s = re.search(rf"(?:Cargo\s+)?(?:Security|Handling)(?:\s+Fee)?\s*:\s*(?:(USD|INR|EUR|GBP)\s*)?\$?\s*({NUM})", raw_ln, re.I)
            if m_r:
                out.append({"lane": curr_lane, "band": f"{m_r.group(1)}-{m_r.group(2)}", "lo": float(m_r.group(1)),
                            "hi": float(m_r.group(2)), "values": [n(m_r.group(3))], "currency": "USD", "page": pi, "line": raw_ln})
                continue
            elif m_p:
                out.append({"lane": curr_lane, "band": f"{m_p.group(1)}+", "lo": float(m_p.group(1)), "hi": None,
                            "values": [n(m_p.group(2))], "currency": "USD", "page": pi, "line": raw_ln})
                continue
            elif m_f:
                for entry in out:
                    if entry["lane"] == curr_lane:
                        entry["fuel_pct"] = n(m_f.group(1))
                continue
            elif m_s:
                for entry in out:
                    if entry["lane"] == curr_lane:
                        entry["security"] = n(m_s.group(2))
                continue

        if "|" in raw_ln:
            cells = [c.strip() for c in raw_ln.split("|") if c.strip()]
            if not cells or any(re.search(r"weight\s*band|base\s*rate|surcharge|security", c, re.I) for c in cells):
                continue
            first_cell = cells[0]
            l_cell = re.search(rf"^{lane_pat}", first_cell)
            lane_to_use = curr_lane
            band_str = first_cell
            if l_cell:
                lane_to_use = l_cell.group(1).upper()
                curr_lane = lane_to_use
                band_str = first_cell[l_cell.end():].strip()

            if lane_to_use and len(cells) >= 2:
                rate_m = re.search(rf"({NUM})", cells[1])
                if rate_m:
                    rate_val = n(rate_m.group(1))
                    cur_m = re.search(r"\b(USD|INR|EUR|GBP)\b", raw_ln, re.I)
                    cur_val = cur_m.group(1).upper() if cur_m else None

                    f_pct_val = None
                    if len(cells) >= 3:
                        fm = re.search(r"(\d+(?:\.\d+)?)\s*%", cells[2])
                        if fm:
                            f_pct_val = n(fm.group(1))
                    sec_val = None
                    if len(cells) >= 4:
                        sm = re.search(rf"({NUM})", cells[3])
                        if sm:
                            sec_val = n(sm.group(1))

                    m_min = re.search(r"\bmin(?:imum)?\b", band_str, re.I)
                    m_range = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:kg)?", band_str, re.I)
                    m_plus = re.search(r"(\d+(?:\.\d+)?)\+\s*(?:kg)?", band_str, re.I)
                    if m_min:
                        out.append({"lane": lane_to_use, "band": "min", "lo": None, "hi": None,
                                    "values": [rate_val], "currency": cur_val, "fuel_pct": f_pct_val, "security": sec_val, "page": pi, "line": raw_ln})
                        continue
                    elif m_range:
                        out.append({"lane": lane_to_use, "band": f"{m_range.group(1)}-{m_range.group(2)}",
                                    "lo": float(m_range.group(1)), "hi": float(m_range.group(2)),
                                    "values": [rate_val], "currency": cur_val, "fuel_pct": f_pct_val, "security": sec_val, "page": pi, "line": raw_ln})
                        continue
                    elif m_plus:
                        out.append({"lane": lane_to_use, "band": f"{m_plus.group(1)}+",
                                    "lo": float(m_plus.group(1)), "hi": None,
                                    "values": [rate_val], "currency": cur_val, "fuel_pct": f_pct_val, "security": sec_val, "page": pi, "line": raw_ln})
                        continue

        ln = re.sub(r"\|", " ", raw_ln).strip()
        m = re.match(rf"^{lane_pat}\s+minimum charge\s+({NUM})((?:\s+{NUM})*)\s*(USD|INR|EUR|GBP)?$", ln, re.I)
        if m:
            vals = ([n(m.group(2))] + [n(x) for x in m.group(3).split()])[:n_vals]
            curr_lane = m.group(1).upper()
            out.append({"lane": curr_lane, "band": "min", "lo": None, "hi": None, "values": vals,
                        "currency": (m.group(4) or "").upper() or None, "page": pi, "line": raw_ln})
            continue
        m = re.match(rf"^{lane_pat}\s+(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:kg)?\s+({NUM})((?:\s+{NUM})*)\s*(USD|INR|EUR|GBP)?$", ln, re.I)
        if m:
            vals = ([n(m.group(4))] + [n(x) for x in m.group(5).split()])[:n_vals]
            curr_lane = m.group(1).upper()
            out.append({"lane": curr_lane, "band": f"{m.group(2)}-{m.group(3)}", "lo": float(m.group(2)),
                        "hi": float(m.group(3)), "values": vals, "currency": (m.group(6) or "").upper() or None,
                        "page": pi, "line": raw_ln})
            continue
        m = re.match(rf"^{lane_pat}\s+(\d+(?:\.\d+)?)\+\s*(?:kg)?\s+({NUM})((?:\s+{NUM})*)\s*(USD|INR|EUR|GBP)?$", ln, re.I)
        if m:
            vals = ([n(m.group(3))] + [n(x) for x in m.group(4).split()])[:n_vals]
            curr_lane = m.group(1).upper()
            out.append({"lane": curr_lane, "band": f"{m.group(2)}+", "lo": float(m.group(2)), "hi": None,
                        "values": vals, "currency": (m.group(5) or "").upper() or None, "page": pi, "line": raw_ln})
            continue
        # Fallback if curr_lane is known and line has band and numbers
        if curr_lane:
            m = re.match(rf"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:kg)?\s+({NUM})((?:\s+{NUM})*)\s*(USD|INR|EUR|GBP)?$", ln, re.I)
            if m:
                vals = ([n(m.group(3))] + [n(x) for x in m.group(4).split()])[:n_vals]
                out.append({"lane": curr_lane, "band": f"{m.group(1)}-{m.group(2)}", "lo": float(m.group(1)),
                            "hi": float(m.group(2)), "values": vals, "currency": (m.group(5) or "").upper() or None,
                            "page": pi, "line": raw_ln})
                continue
            m = re.match(rf"^(\d+(?:\.\d+)?)\+\s*(?:kg)?\s+({NUM})((?:\s+{NUM})*)\s*(USD|INR|EUR|GBP)?$", ln, re.I)
            if m:
                vals = ([n(m.group(2))] + [n(x) for x in m.group(3).split()])[:n_vals]
                out.append({"lane": curr_lane, "band": f"{m.group(1)}+", "lo": float(m.group(1)), "hi": None,
                            "values": vals, "currency": (m.group(4) or "").upper() or None, "page": pi, "line": raw_ln})
                continue
    return out


def parse_fuel(pages) -> list[dict]:
    """Annex C: '2034-10 17.49%' or Route: 'Fuel surcharge: 15% of base'"""
    out, in_c = [], False
    lane_pat = r"([A-Z]{2,4}[A-Z0-9]*-[A-Z]{2,4}[A-Z0-9]*)"
    curr_lane = None
    for pi, ln in lines_of(pages):
        lm = re.search(rf"\b(?:Lane|Route)\s*(?:[A-Z]\b)?\s*\(?{lane_pat}\)?", ln, re.I)
        if lm:
            curr_lane = lm.group(1).upper()
        if re.match(r"^Annex C", ln, re.I):
            in_c = True
        elif re.match(r"^Annex [D-Z]", ln, re.I):
            in_c = False
        m = re.match(r"^(\d{4}-\d{2})\s+(\d+(?:\.\d+)?)\s*%$", ln)
        if m and in_c:
            out.append({"month": m.group(1), "pct": n(m.group(2)), "page": pi, "line": ln})
        fm = re.search(r"Fuel\s*(?:surcharge)?\s*:\s*(\d+(?:\.\d+)?)\s*%", ln, re.I)
        if fm:
            out.append({"lane": curr_lane, "pct": n(fm.group(1)), "page": pi, "line": ln})
    return out


def parse_accessorials(pages) -> list[dict]:
    """Annex D: 'DG Dangerous goods fee 124.02 USD per shipment' or 'Handling: $150.00 flat'"""
    out, in_d = [], False
    lane_pat = r"([A-Z]{2,4}[A-Z0-9]*-[A-Z]{2,4}[A-Z0-9]*)"
    curr_lane = None
    for pi, ln in lines_of(pages):
        lm = re.search(rf"\b(?:Lane|Route)\s*(?:[A-Z]\b)?\s*\(?{lane_pat}\)?", ln, re.I)
        if lm:
            curr_lane = lm.group(1).upper()
        if re.match(r"^Annex D", ln, re.I):
            in_d = True
        elif re.match(r"^Annex [E-Z]", ln, re.I):
            in_d = False
        if in_d:
            m = re.match(rf"^([A-Z]{{2,10}})\s+(.+?)\s+({NUM})\s+(USD|INR|EUR|GBP)\s+(per .+)$", ln)
            if m:
                out.append({"code": m.group(1), "name": m.group(2), "fee": n(m.group(3)), "currency": m.group(4),
                            "basis": m.group(5), "page": pi, "line": ln})
        hm = re.search(rf"\b(?:Cargo\s+)?(Handling|Security)(?:\s+Fee)?\s*:\s*(?:(USD|INR|EUR|GBP)\s*)?\$?\s*({NUM})\s*(flat|per\s+shipment)?", ln, re.I)
        if hm:
            code = "HANDLING" if hm.group(1).upper() == "HANDLING" else "SEC"
            h_cur = (hm.group(2) or "USD").upper()
            out.append({"code": code, "name": hm.group(1), "fee": n(hm.group(3)), "currency": h_cur,
                        "basis": hm.group(4) or "flat", "lane": curr_lane, "page": pi, "line": ln})
    return out


def parse_charge_codes(pages) -> list[dict]:
    """Annex E: 'Code SEC: Security surcharge; also billed as: Screening fee, Screening fee (adj.)'"""
    out = []
    for pi, ln in lines_of(pages):
        m = re.match(r"^Code\s+([A-Z]+)\s*:\s*(.+?)(?:;\s*also billed as\s*:\s*(.+))?$", ln)
        if m:
            labels = [m.group(2).strip()] + ([x.strip() for x in re.split(r",\s*(?![^()]*\))", m.group(3))] if m.group(3) else [])
            out.append({"code": m.group(1), "label": m.group(2).strip(), "labels": labels, "page": pi, "line": ln})
    return out


def parse_fx(pages) -> list[dict]:
    """Annex F: 'INR per 1 USD' rows. Accepts '2035-01 83.12', 'August 2034 | 83.50', or tables."""
    out, in_f = [], False
    months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
              "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
    for pi, ln in lines_of(pages):
        if re.search(r"\bAnnex F\b", ln, re.I):
            in_f = True
            continue
        elif in_f and re.search(r"\b(?:Schedule|Annex [A-EG-Z]|ARTICLE)\b", ln, re.I):
            in_f = False
        if not in_f:
            continue
        parts = [p.strip() for p in ln.split("|") if p.strip()]
        if len(parts) >= 2:
            m_part, r_part = parts[0], parts[1]
            ym = None
            m1 = re.search(r"\b(\d{4})-(\d{2})\b", m_part)
            if m1:
                ym = f"{m1.group(1)}-{m1.group(2)}"
            else:
                m2 = re.search(r"\b([A-Za-z]{3})[a-z]*\s*(\d{4})\b", m_part)
                if m2 and m2.group(1).lower() in months:
                    ym = f"{m2.group(2)}-{months[m2.group(1).lower()]}"
            m_rate = re.search(rf"\b({NUM})\b", r_part)
            if ym and m_rate:
                out.append({"month": ym, "inr_per_usd": n(m_rate.group(1)), "page": pi, "line": ln})
        else:
            ym = None
            end_pos = 0
            m1 = re.search(r"\b(\d{4})-(\d{2})\b", ln)
            if m1:
                ym = f"{m1.group(1)}-{m1.group(2)}"
                end_pos = m1.end()
            else:
                m2 = re.search(r"\b([A-Za-z]{3})[a-z]*\s*(\d{4})\b", ln)
                if m2 and m2.group(1).lower() in months:
                    ym = f"{m2.group(2)}-{months[m2.group(1).lower()]}"
                    end_pos = m2.end()
            if ym:
                m_rate = re.search(rf"\b({NUM})\b", ln[end_pos:])
                if m_rate:
                    out.append({"month": ym, "inr_per_usd": n(m_rate.group(1)), "page": pi, "line": ln})
    return out


def parse_schedule1(pages) -> list[dict]:
    """Parse Schedule 1 authorised contacts across single-line and multi-line formats."""
    out = []
    on = False
    cur_party = None
    cur_role = None
    pending = None
    for pi, ln in lines_of(pages):
        raw_ln = ln.strip()
        if not raw_ln:
            continue
        if re.match(r"^(?:#+\s*)?Schedule\s+1\b", raw_ln, re.I):
            # Avoid matching Table of Contents entries like 'Schedule 1 Authorised Persons 11'
            if not re.search(r"\bSchedule\s+1\b.*\b\d+$", raw_ln, re.I):
                on = True
                continue
        if not on:
            continue
        if re.match(r"^(Annex\s+[A-Z]|Schedule\s+[2-9]|IN\s+WITNESS|Execution|---)", raw_ln, re.I) and not re.search(r"Schedule\s+1\b", raw_ln, re.I):
            on = False
            if pending:
                out.append(pending)
                pending = None
            continue

        pm = re.match(r"^(Customer|Carrier|Shipper)\s*\((?:[^,)]+,)?\s*([A-Z0-9-]+)\)\s*:", raw_ln, re.I)
        if pm:
            if pending:
                out.append(pending)
                pending = None
            cur_role = pm.group(1).title()
            cur_party = pm.group(2).strip()
            continue

        # Party: Name (categories) – email
        m_p_contact = re.match(r"^([A-Za-z0-9 ,.-]+?)\s*:\s*([A-Za-z .]+?)\s*\(([^)]+)\)\s*(?:[—–-]|at)\s*<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?", raw_ln)
        if m_p_contact:
            if pending:
                out.append(pending)
                pending = None
            pty = m_p_contact.group(1).strip()
            role = "Carrier" if any(w in pty.lower() for w in ["cargo", "carrier", "freight", "apex", "logistics", "airline", "express", "transport"]) else "Shipper"
            cats = [c.strip().replace("-", "_") for c in m_p_contact.group(3).split(",") if c.strip()]
            out.append({
                "name": m_p_contact.group(2).strip(),
                "title": "",
                "party": pty,
                "party_role": role,
                "categories": cats,
                "email": m_p_contact.group(4).strip().lower(),
                "page": pi,
                "line": ln
            })
            continue

        # Party header e.g. "Apex Cargo Solutions:" or "Meridian Biotech:"
        m_party_hdr = re.match(r"^([A-Za-z0-9 ,.-]+?)\s*:$", raw_ln)
        if m_party_hdr and not any(k in raw_ln.lower() for k in ["schedule", "annex", "contact", "email", "phone", "party", "name", "rate"]):
            if pending:
                out.append(pending)
                pending = None
            cur_party = m_party_hdr.group(1).strip()
            cur_role = "Carrier" if any(w in cur_party.lower() for w in ["cargo", "carrier", "freight", "apex", "logistics", "airline", "express", "transport"]) else "Shipper"
            continue

        # Name (categories) – email (under cur_party)
        m_sub_contact = re.match(r"^\s*([A-Za-z .]+?)\s*\(([^)]+)\)\s*(?:[—–-]|at)\s*<?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)>?", raw_ln)
        if m_sub_contact:
            if pending:
                out.append(pending)
                pending = None
            cats = [c.strip().replace("-", "_") for c in m_sub_contact.group(2).split(",") if c.strip()]
            out.append({
                "name": m_sub_contact.group(1).strip(),
                "title": "",
                "party": cur_party,
                "party_role": cur_role,
                "categories": cats,
                "email": m_sub_contact.group(3).strip().lower(),
                "page": pi,
                "line": ln
            })
            continue

        m_single = re.match(r"^(.+?),\s*(.+?),\s*([A-Z0-9][A-Z0-9-]*)\s*:\s*(.+?)\s*<([^>]+)>\s*$", raw_ln)
        if m_single:
            if pending:
                out.append(pending)
                pending = None
            cats = [c.strip().replace("-", "_") for c in m_single.group(4).split(",") if c.strip()]
            out.append({
                "name": m_single.group(1).strip(),
                "title": m_single.group(2).strip(),
                "party": m_single.group(3).strip(),
                "party_role": cur_role,
                "categories": cats,
                "email": m_single.group(5).strip().lower(),
                "page": pi,
                "line": ln
            })
            continue

        email_m = re.search(r"(?:<)?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)(?:>)?", raw_ln)
        if pending and email_m and not re.search(r"[—:\-]\s*[a-z_]+", raw_ln):
            pending["email"] = email_m.group(1).strip().lower()
            out.append(pending)
            pending = None
            continue

        m_name = re.match(r"^\s*([A-Z][a-zA-Z\s.]+?)\s+[^a-zA-Z0-9\s]+\s+([a-zA-Z0-9_,\s-]+?)(?:\s*\(([^)]+)\))?\s*$", raw_ln)
        if m_name:
            if pending:
                out.append(pending)
                pending = None
            name = m_name.group(1).strip()
            cats_raw = m_name.group(2).strip()
            title = m_name.group(3).strip() if m_name.group(3) else ""
            cats = [c.strip().replace("-", "_") for c in cats_raw.split(",") if c.strip()]
            pending = {
                "name": name,
                "title": title,
                "party": cur_party,
                "party_role": cur_role,
                "categories": cats,
                "email": "",
                "page": pi,
                "line": ln
            }
            if email_m:
                pending["email"] = email_m.group(1).strip().lower()
                out.append(pending)
                pending = None
            continue

    if pending:
        out.append(pending)
    return out


# ---- clause splitting (for quotes and for the model) -------------------------------------------------------------------
def split_clauses(pages) -> dict[str, dict]:
    """{'10.2': {'page': 4, 'text': '10.2 Late fee. ...'}} with page headers/footers dropped."""
    out: dict[str, dict] = {}
    cur = None
    for pi, p in enumerate(pages, 1):
        for ln in p.split("\n"):
            s = ln.strip()
            if not s or s.startswith(("Initials", "Confidential")) or re.match(r"^Page \d+ of \d+", s):
                continue
            m = re.match(r"^(?:Section\s+|Article\s+)?(\d{1,2}\.\d{1,2})\s*[:.—–\-\u2013\u2014\ufffd]?\s+[A-Za-z]", s)
            top = re.match(r"^(?:Section\s+|Article\s+)?(\d{1,2})\s*[:.—–\-\u2013\u2014\ufffd]?\s+[A-Z][A-Za-z ,&-]+$", s)       # a bare section heading: '8 Handling margin' or 'Section 2: Term and Renewal'
            if m:
                cur = m.group(1)
                out[cur] = {"page": pi, "text": s}
            elif re.match(r"^(Annex [A-Z]\b(?!,)|Schedule \d|Execution|IN WITNESS)", s) and len(s) < 90 and not s.endswith("."):
                cur = None
            elif top and not s.endswith("."):
                cur = None
            elif cur:
                out[cur]["text"] += " " + s
    return out


# ---- spreadsheets --------------------------------------------------------------------------------------------------------
def parse_tracking(pages) -> list[dict]:
    """'TX23827044 | PICKED_UP | 2034-11-04 | USS2 | -'"""
    out = []
    for pi, ln in lines_of(pages):
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) >= 3 and re.match(r"^[A-Z0-9]{6,}$", cells[0]) and re.match(r"^[A-Z_]+$", cells[1]) \
                and re.match(DATE, cells[2]):
            out.append({"awb": cells[0], "event": cells[1], "date": cells[2], "station": cells[3] if len(cells) > 3 else "",
                        "reason": cells[4] if len(cells) > 4 else "", "page": pi, "line": ln})
    return out


def parse_register(pages) -> list[dict]:
    """'TX-US-2034-0379 | 2034-11-26 | due 2035-01-10 | USD 1243.96 | paid | 2035-01-03'
    Tolerant: finds the invoice number, dates, an amount with currency and a status word wherever they sit."""
    out = []
    for pi, ln in lines_of(pages):
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) < 4 or not re.search(r"\d", cells[0]) or cells[0].lower().startswith("invoice"):
            continue
        dates = [re.search(DATE, c).group(0) if re.search(DATE, c) else None for c in cells]
        due = next((re.search(DATE, c).group(0) for c in cells if re.match(r"^due\b", c, re.I) and re.search(DATE, c)), None)
        amt = next((re.match(rf"^([A-Z]{{3}})\s*({NUM})$", c) for c in cells[1:] if re.match(rf"^[A-Z]{{3}}\s*{NUM}$", c)), None)
        status = next((c.lower() for c in cells if c.lower() in ("paid", "open", "unpaid", "scheduled", "disputed", "partial", "partially paid", "credited")), None)
        plain_dates = [re.search(DATE, c).group(0) for c in cells[1:] if re.fullmatch(DATE, c)]
        inv_date = plain_dates[0] if plain_dates else None
        paid_date = plain_dates[-1] if (status in ("paid", "partial", "partially paid") and len(plain_dates) >= 2) else None
        if amt and status:
            out.append({"invoice_no": cells[0], "invoice_date": inv_date, "due_date": due, "currency": amt.group(1),
                        "amount": n(amt.group(2)), "status": status, "paid_date": paid_date, "page": pi, "line": ln})
    return out


def parse_statement(pages) -> dict | None:
    """Monthly statement spreadsheet that carries its own number. Charge | Reference | Quantity | Rate | Amount rows."""
    head = "\n".join(pages)
    mnum = re.search(r"STATEMENT OF ACCOUNT\s+(\S+)", head, re.I)
    mdate = re.search(rf"Statement date\s+({DATE})", head, re.I)
    mdue = re.search(rf"Due date\s+({DATE})", head, re.I)
    mc = re.search(r"Contract reference\s+(\S+)", head, re.I)
    if not (mnum and mdate):
        return None
    lines = []
    for pi, ln in lines_of(pages):
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) == 5 and re.match(NUM + "$", cells[4]) and not cells[0].lower().startswith("charge"):
            lines.append({"description": cells[0], "reference": cells[1], "qty_text": cells[2], "rate": n(cells[3]),
                          "amount": n(cells[4]), "page": pi, "line": ln})
    total = re.search(rf"Total\s+([A-Z]{{3}})\s*\|\s*({NUM})", head)
    return {"invoice_id_raw": mnum.group(1), "invoice_date": mdate.group(1), "due_date": mdue.group(1) if mdue else None,
            "contract_ref": mc.group(1) if mc else None, "lines": lines,
            "currency": total.group(1) if total else "USD", "total": n(total.group(2)) if total else None}
