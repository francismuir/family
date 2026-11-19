#!/usr/bin/env python3
"""
Extracts and reconciles all genealogy data from:
1. Legacy Microsoft Access 97 database (Docs/family.mdb)
2. Original HTML 3.2 website (website/people/*.html, website/tree/*.html, website/misc/notes.html)
"""

import csv
import glob
import html as html_lib
import json
import os
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MDB_PATH = (
    os.path.join(ROOT_DIR, "docs", "family.mdb")
    if os.path.exists(os.path.join(ROOT_DIR, "docs", "family.mdb"))
    else os.path.join(ROOT_DIR, "Docs", "family.mdb")
)
WEBSITE_DIR = os.path.join(ROOT_DIR, "website")
MASTER_XLSX_PATH = os.path.join(ROOT_DIR, "exports", "muir_family_tree.xlsx")


def extract_access_mdb(mdb_path=MDB_PATH):
    """Pure-Python Jet 3 (Access 97) reader for Docs/family.mdb (TDEF page 19)."""
    with open(mdb_path, "rb") as f:
        data = f.read()

    psize = 2048
    p19 = data[19 * psize : 20 * psize]
    max_cols, var_cols, num_cols, num_idx, num_real_idx = struct.unpack_from("<HHHII", p19, 0x15)
    pos = 0x2B + num_real_idx * 8
    cols = []
    for c in range(num_cols):
        raw = p19[pos : pos + 18]
        ctype = raw[0]
        col_id, var_col_num, col_order = struct.unpack_from("<HHH", raw, 1)
        flags = raw[13]
        fixed_offset = struct.unpack_from("<H", raw, 14)[0]
        col_len = struct.unpack_from("<H", raw, 16)[0]
        cols.append(
            {
                "type": ctype,
                "id": col_id,
                "var_num": var_col_num,
                "order": col_order,
                "flags": flags,
                "fixed_off": fixed_offset,
                "len": col_len,
            }
        )
        pos += 18
    for c in range(num_cols):
        nlen = p19[pos]
        cols[c]["name"] = p19[pos + 1 : pos + 1 + nlen].decode("latin1")
        pos += 1 + nlen

    def decode_row_jet3(rb):
        ncols = rb[0]
        null_mask_len = (ncols + 7) // 8
        null_mask = rb[-null_mask_len:]

        def is_not_null(col_id):
            byte_idx = col_id // 8
            bit_idx = col_id % 8
            if byte_idx >= len(null_mask):
                return False
            return bool(null_mask[byte_idx] & (1 << bit_idx))

        var_pos = len(rb) - null_mask_len - 1
        num_var = rb[var_pos]
        num_jumps = (len(rb) - 1) // 256
        col_ptr = var_pos - num_jumps - 1
        jumps_used = 0
        offsets = []
        for i in range(num_var + 1):
            while jumps_used < num_jumps and i == rb[var_pos - jumps_used - 1]:
                jumps_used += 1
            offsets.append(rb[col_ptr - i] + (jumps_used * 256))

        rec = {}
        for c in cols:
            cid = c["id"]
            cname = c["name"]
            ctype = c["type"]
            is_fixed = bool(c["flags"] & 0x01)
            if ctype == 1:
                rec[cname] = is_not_null(cid)
            elif is_fixed:
                if not is_not_null(cid):
                    rec[cname] = None
                else:
                    foff = 1 + c["fixed_off"]
                    flen = c["len"]
                    fbytes = rb[foff : foff + flen]
                    if ctype == 7:
                        val = struct.unpack("<d", fbytes)[0]
                        rec[cname] = int(val) if val.is_integer() else val
                    elif ctype == 4:
                        rec[cname] = struct.unpack("<i", fbytes)[0]
                    elif ctype == 3:
                        rec[cname] = struct.unpack("<h", fbytes)[0]
                    else:
                        rec[cname] = fbytes[0]
            else:
                vnum = c["var_num"]
                if not is_not_null(cid) or vnum >= num_var:
                    rec[cname] = None
                else:
                    start = offsets[vnum]
                    end = offsets[vnum + 1]
                    vbytes = rb[start:end]
                    rec[cname] = vbytes.decode("cp1252", errors="replace").strip()
        return rec

    rows = []
    for pg in range(len(data) // psize):
        p = data[pg * psize : (pg + 1) * psize]
        if p[0] == 1 and p[1] == 1 and struct.unpack_from("<I", p, 4)[0] == 19:
            nrows = struct.unpack_from("<H", p, 8)[0]
            prev_end = psize
            for r in range(nrows):
                off = struct.unpack_from("<H", p, 10 + r * 2)[0]
                real_off = off & 0x0FFF
                rb = p[real_off:prev_end]
                prev_end = real_off
                if not (off & 0x8000) and not (off & 0x4000):
                    rows.append(decode_row_jet3(rb))

    col_names = [c["name"] for c in sorted(cols, key=lambda x: x["order"])]
    return col_names, rows


def clean_html_text(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&nbsp", " ")
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def norm_words(s):
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-zA-Z]+", " ", s).lower()
    stop = {
        "m",
        "div",
        "issue",
        "killed",
        "flying",
        "drowned",
        "at",
        "sea",
        "of",
        "in",
        "the",
        "her",
        "cousin",
        "grandson",
        "dr",
        "first",
        "rector",
        "grayswood",
        "born",
        "ob",
        "inf",
        "infancy",
        "sp",
        "nee",
    }
    return [w for w in s.split() if w and w not in stop]


def extract_years(s):
    if not s:
        return []
    return re.findall(r"\b(1[4-9]\d\d)\b", s)


def infer_gender(cname, title_or_notes="", role_hint=None):
    if role_hint in ("M", "F"):
        return role_hint
    text = f"{cname} {title_or_notes}".lower()
    words = re.findall(r"[a-z]+", text)
    female_markers = {
        "mary", "elizabeth", "helen", "helena", "margaret", "jane", "jean", "janet",
        "ann", "anne", "anna", "annetje", "agnes", "sarah", "catherine", "katherine",
        "marion", "isobel", "isobell", "isabella", "isabel", "joan", "joanna", "johanna",
        "alice", "dorothy", "beatrice", "carolina", "caroline", "louisa", "louise",
        "harriet", "harriett", "edith", "florence", "mabel", "lillian", "irma",
        "aimee", "marjorie", "marjory", "gwendolen", "ada", "evelyn", "christine",
        "lindsey", "penelope", "gillian", "samantha", "clara", "letitia", "alicia",
        "hester", "charlotte", "molly", "grace", "thomasine", "elinor", "eleanor",
        "gertruyd", "gertrude", "maria", "sophia", "cornelia", "eva", "catterina",
        "amelia", "euphemia", "jessie", "adrina", "logie", "bessie", "ebott", "jonat",
        "christian", "barbara", "patricia", "susan", "diana", "wendy", "fiona",
        "deborah", "rebecca", "rachel", "nicola", "jacqueline", "jennifer", "judith",
        "audrey", "kathleen", "sheila", "pamela", "valerie", "rosemary", "bridget",
        "veronica", "angela", "sandra", "pauline", "brenda", "maud", "mai", "amy",
        "eanswythe", "annabel", "lucy", "claire", "emma", "sophie", "hannah",
        "karen", "linda", "daphne", "iris", "olive", "ruby", "violet", "pearl",
        "woman", "wife", "daughter", "sister", "aunt", "lady", "mrs", "miss",
    }
    male_markers = {
        "john", "william", "james", "thomas", "richard", "robert", "ALEXANDER".lower(),
        "francis", "edward", "george", "charles", "henry", "STEPHEN".lower(), "stephanus",
        "david", "andrew", "peter", "philip", "michael", "christopher", "nicholas",
        "anthony", "antonio", "frederick", "ernest", "arthur", "walter", "patrick",
        "archibald", "gavin", "joseph", "samuel", "benjamin", "daniel", "matthew",
        "mark", "luke", "paul", "simon", "timothy", "jonathan", "jeremy", "julian",
        "adrian", "alan", "alastair", "alistair", "colin", "CRAIG".lower(), "derek", "donald",
        "douglas", "DUNCAN".lower(), "gordon", "graham", "grant", "hugh", "ian", "keith",
        "kenneth", "malcolm", "martin", "neil", "nigel", "oliver", "owen", "ralph",
        "raymond", "reginald", "roger", "ronald", "roy", "russell", "stewart", "stuart",
        "terence", "trevor", "victor", "vincent", "wilfred", "edmond", "edmund",
        "oloff", "jacob", "jacobus", "johannes", "jeremias", "andries", "brandt",
        "kiliaen", "domenico", "dominico", "giacomo", "pakenham", "cecil", "vernon",
        "clinton", "guy", "rowlett", "jock", "sheridan", "alp", "arslan", "elliot",
        "rev", "sir", "col", "maj", "capt", "lieut", "gen", "lord", "king", "duke",
        "earl", "abbot", "bishop", "mr", "esq",
    }
    for w in words:
        if w in female_markers:
            return "F"
        if w in male_markers:
            return "M"
    return "U"


def build_dataset():
    mdb_cols, mdb_rows = extract_access_mdb()

    # 1. Parse website/people/index.html (Direct ancestors & FullRef mapping)
    with open(os.path.join(WEBSITE_DIR, "people", "index.html"), "r", encoding="cp1252", errors="replace") as f:
        idx_direct_html = f.read()

    ref_to_pid = {}
    pid_to_ref = {}
    direct_index_order = []
    for tr in re.findall(r"<TR>(.*?)</TR>", idx_direct_html, re.S | re.I):
        tds = re.findall(r"<TD[^>]*>(.*?)</TD>", tr, re.S | re.I)
        if len(tds) == 3:
            ref_txt = clean_html_text(tds[0])
            m = re.search(r'HREF="([0-9]+)\.html"', tds[1], re.I)
            dates_txt = clean_html_text(tds[2])
            if m:
                pid = m.group(1)
                direct_index_order.append((ref_txt, pid, dates_txt))
                if ref_txt.startswith(":"):
                    ref_to_pid[ref_txt] = pid
                    pid_to_ref[pid] = ref_txt

    mdb_by_pid = {}
    for r in mdb_rows:
        fr = r.get("FullRef")
        if fr and fr in ref_to_pid:
            mdb_by_pid[ref_to_pid[fr]] = r

    # 2. Parse all 138 individual pages in website/people/[0-9]*.html
    people_files = sorted(glob.glob(os.path.join(WEBSITE_DIR, "people", "[0-9]*.html")))
    people_pages = {}
    for fpath in people_files:
        pid = os.path.basename(fpath).replace(".html", "")
        with open(fpath, "r", encoding="cp1252", errors="replace") as f:
            html = f.read()
        tree_m = re.search(r'HREF="\.\./tree/([0-9]+)\.html"', html, re.I)
        tree_id = tree_m.group(1) if tree_m else None
        h1_m = re.search(r"<H1>(.*?)</H1>", html, re.S | re.I)
        h1_txt = clean_html_text(h1_m.group(1)) if h1_m else ""
        trs = re.findall(r"<TR>(.*?)</TR>", html, re.S | re.I)
        rec = {
            "id": pid,
            "h1": h1_txt,
            "tree_id": tree_id,
            "spouses_raw": [],
            "marriages_raw": [],
            "issue_raw": [],
        }
        for tr in trs:
            tds = re.findall(r"<TD[^>]*>(.*?)</TD>", tr, re.S | re.I)
            if len(tds) == 2:
                k = clean_html_text(tds[0])
                v = tds[1].strip()
                if k == "Spouse":
                    rec["spouses_raw"].append(v)
                elif k == "Marriage":
                    rec["marriages_raw"].append(clean_html_text(v))
                elif k == "Issue":
                    rec["issue_raw"].append(v)
                else:
                    rec[k] = clean_html_text(v)
        people_pages[pid] = rec

    # 3. Parse website/people/index[a-z].html
    index_files = sorted(glob.glob(os.path.join(WEBSITE_DIR, "people", "index[a-z].html")))
    index_entries = []
    for fpath in index_files:
        letter = os.path.basename(fpath)[5].upper()
        with open(fpath, "r", encoding="cp1252", errors="replace") as f:
            html = f.read()
        trs = re.findall(r"<TR>(.*?)</TR>", html, re.S | re.I)
        for tr in trs:
            if "<TH>" in tr.upper():
                continue
            tds = re.findall(r"<TD[^>]*>(.*?)</TD>", tr, re.S | re.I)
            if len(tds) == 4:
                name_cell, dates_cell, gen_cell, tree_cell = [x.strip() for x in tds]
                p_m = re.search(r'HREF="([0-9]+)\.html"', name_cell, re.I)
                pid = p_m.group(1) if p_m else None
                name_txt = clean_html_text(name_cell)
                dates_txt = clean_html_text(dates_cell)
                gen_txt = clean_html_text(gen_cell)
                t_m = re.search(r'HREF="\.\./tree/([0-9]+)\.html"', tree_cell, re.I)
                tid = t_m.group(1) if t_m else None
                index_entries.append(
                    {
                        "name": name_txt,
                        "pid": pid,
                        "dates": dates_txt,
                        "gen": gen_txt,
                        "tid": tid,
                        "letter": letter,
                    }
                )

    # Link the 3 unlinked index entries that actually have people/[0-9]*.html files
    for e in index_entries:
        if not e["pid"]:
            if e["name"] == "LEAKE, Rev. John Sherlock" and e["gen"] == "2":
                e["pid"] = "00000170"
            elif e["name"] == "WHITEWAY, Philip" and e["gen"] == "4":
                e["pid"] = "00000492"
            elif e["name"] == "WHITEWAY, Stephen Evan Angelo" and e["gen"] == "2":
                e["pid"] = "00000502"

    # Deduplicate the 5 exact duplicate rows in index_entries
    dedup_index = []
    by_key = {}
    for e in index_entries:
        k = (e["name"], e["dates"], e["gen"])
        if k in by_key:
            if e["tid"] and not by_key[k]["tid"]:
                by_key[k]["tid"] = e["tid"]
            elif e["tid"] == by_key[k]["tid"]:
                pass
            else:
                dedup_index.append(e)
        else:
            by_key[k] = e
            dedup_index.append(e)

    # Build master people dict
    people = {}
    next_p_num = 1001

    for e in dedup_index:
        pid = e["pid"]
        raw_name = e["name"]
        is_direct = "**" in raw_name
        clean_name = raw_name.replace("**", "").strip()
        if "," in clean_name:
            sn, cn = [x.strip() for x in clean_name.split(",", 1)]
        else:
            sn, cn = clean_name, ""
        if not pid:
            pid = f"P{next_p_num:04d}"
            next_p_num += 1
        people[pid] = {
            "id": pid,
            "has_original_page": pid in people_pages,
            "surname": sn,
            "cname": cn,
            "is_direct_ancestor": is_direct,
            "ahnentafel": pid_to_ref.get(pid, ""),
            "dates": e["dates"],
            "birth": "",
            "death": "",
            "marriage": "",
            "profession": "",
            "notes": "",
            "generation": e["gen"],
            "tree_id": e["tid"],
            "trees_appeared": [e["tid"]] if e["tid"] else [],
            "index_letter": e["letter"],
            "gender": "U",
            "parents": [],
            "spouses": [],
            "children": [],
            "siblings": [],
        }

    # Add the 7 people_pages that were not in index[a-z].html
    for pid in sorted(set(people_pages.keys()) - set(people.keys())):
        p = people_pages[pid]
        raw_sn = p.get("Surname", "")
        is_direct = "**" in raw_sn or pid in pid_to_ref
        sn = raw_sn.replace("**", "").strip() or "??"
        cn = p.get("CName", "").strip()
        b = p.get("Birth", "").strip() or "????"
        d = p.get("Death", "").strip() or "????"
        tid = p.get("tree_id")
        people[pid] = {
            "id": pid,
            "has_original_page": True,
            "surname": sn,
            "cname": cn,
            "is_direct_ancestor": is_direct,
            "ahnentafel": pid_to_ref.get(pid, ""),
            "dates": f"{b}-{d}",
            "birth": p.get("Birth", ""),
            "death": p.get("Death", ""),
            "marriage": "; ".join(m for m in p.get("marriages_raw", []) if m),
            "profession": p.get("Profession", ""),
            "notes": p.get("Notes", ""),
            "generation": p.get("Generation", ""),
            "tree_id": tid,
            "trees_appeared": [tid] if tid else [],
            "index_letter": sn[0].upper() if sn and sn[0].isalpha() else "Other",
            "gender": "U",
            "parents": [],
            "spouses": [],
            "children": [],
            "siblings": [],
        }

    # Enrich people with people_pages and mdb_by_pid details
    for pid, person in people.items():
        if pid in people_pages:
            pp = people_pages[pid]
            if "**" in pp.get("Surname", "") or pid in pid_to_ref:
                person["is_direct_ancestor"] = True
            if pp.get("Birth"):
                person["birth"] = pp["Birth"]
            if pp.get("Death"):
                person["death"] = pp["Death"]
            if pp.get("Profession"):
                person["profession"] = pp["Profession"]
            if pp.get("Notes"):
                person["notes"] = pp["Notes"]
            marriages = [m for m in pp.get("marriages_raw", []) if m]
            if marriages:
                person["marriage"] = "; ".join(marriages)
            if pp.get("tree_id") and not person["tree_id"]:
                person["tree_id"] = pp["tree_id"]
                if pp["tree_id"] not in person["trees_appeared"]:
                    person["trees_appeared"].append(pp["tree_id"])

        if pid in mdb_by_pid:
            mr = mdb_by_pid[pid]
            person["is_direct_ancestor"] = True
            if mr.get("FullRef"):
                person["ahnentafel"] = mr["FullRef"]
            # Prefer longer/richer strings from Access DB if HTML page truncated or omitted them
            if mr.get("Birth") and len(mr["Birth"]) > len(person["birth"]):
                person["birth"] = mr["Birth"]
            if mr.get("Death") and len(mr["Death"]) > len(person["death"]):
                person["death"] = mr["Death"]
            if mr.get("Marriage") and len(mr["Marriage"]) > len(person["marriage"]):
                person["marriage"] = mr["Marriage"]
            mdb_prof = ((mr.get("Prof") or "") + " " + (mr.get("Prof2") or "")).strip()
            if mdb_prof and len(mdb_prof) > len(person["profession"]):
                person["profession"] = mdb_prof
            if mr.get("Notes") and len(mr["Notes"]) > len(person["notes"]):
                person["notes"] = mr["Notes"]

        # If birth/death are still empty, parse from dates (e.g. "1839-1912" or "1848 Aug 15th-1944")
        if not person["birth"] and not person["death"] and person["dates"]:
            parts = person["dates"].split("-", 1)
            if len(parts) == 2:
                b_part, d_part = parts[0].strip(), parts[1].strip()
                if b_part and b_part != "????" and b_part != "?":
                    person["birth"] = b_part
                if d_part and d_part != "????" and d_part != "?":
                    person["death"] = d_part
        person["dates"] = compute_life_dates(person["birth"], person["death"])

    # 4. Parse misc/notes.html
    notes_map = {}
    with open(os.path.join(WEBSITE_DIR, "misc", "notes.html"), "r", encoding="cp1252", errors="replace") as f:
        notes_html = f.read()
    for m in re.finditer(r'<LI><A NAME="(note\d+)">(.*?)</A>', notes_html, re.S | re.I):
        notes_map[m.group(1).lower()] = clean_html_text(m.group(2))

    # 5. Parse all 61 tree pages in website/tree/[0-9]*.html
    tree_files = sorted(glob.glob(os.path.join(WEBSITE_DIR, "tree", "[0-9]*.html")))
    trees = {}

    def match_or_create_person(txt, explicit_pid, cur_gen, tid):
        nonlocal next_p_num
        # Fix known bug in original 00000118.html where John Endacott (-1691) in gen 9 linked to 00000122 (his son Thomas)
        if tid == "00000118" and cur_gen == "9" and explicit_pid == "00000122" and "john" in txt.lower():
            explicit_pid = "00000118"

        if explicit_pid and explicit_pid in people:
            if tid and tid not in people[explicit_pid]["trees_appeared"]:
                people[explicit_pid]["trees_appeared"].append(tid)
            if not people[explicit_pid]["tree_id"]:
                people[explicit_pid]["tree_id"] = tid
            return explicit_pid

        # Clean placeholder spouses like "??" or "???"
        stripped = re.sub(r"[\?\s]+", "", txt)
        if not stripped:
            return None

        w_seg = set(norm_words(txt))
        y_seg = set(extract_years(txt))
        best_id = None
        best_score = -1

        for cand_id, cand in people.items():
            score = 0
            if cand["generation"] == str(cur_gen):
                score += 10
            elif cur_gen is not None:
                continue  # Must match generation on tree!
            if cand["tree_id"] == tid:
                score += 15
            w_cand = set(norm_words(cand["surname"] + " " + cand["cname"]))
            common_w = w_seg & w_cand
            if not common_w and w_seg and w_cand:
                continue
            score += len(common_w) * 10
            score -= len(w_seg ^ w_cand) * 2
            y_cand = set(extract_years(cand["dates"] + " " + cand["birth"] + " " + cand["death"]))
            if y_seg and y_cand:
                if y_seg & y_cand:
                    score += 12
                else:
                    score -= 12
            if score > best_score:
                best_score = score
                best_id = cand_id

        if best_score >= 15 and best_id:
            if tid and tid not in people[best_id]["trees_appeared"]:
                people[best_id]["trees_appeared"].append(tid)
            if not people[best_id]["tree_id"]:
                people[best_id]["tree_id"] = tid
            return best_id

        # Create a new person record for the 6 unindexed individuals on trees (e.g. Brenda ?, Johanna, Rannald, An Indian Woman, Elizabeth ??, 10 others ob. infancy)
        # Check if we already created one with the same name & gen
        for cand_id, cand in people.items():
            if cand["generation"] == str(cur_gen) and cand.get("raw_tree_label") == txt:
                if tid and tid not in cand["trees_appeared"]:
                    cand["trees_appeared"].append(tid)
                return cand_id

        new_pid = f"P{next_p_num:04d}"
        next_p_num += 1
        if "infancy" in txt.lower():
            sn, cn = "VAN CORTLANDT", txt
        elif "freer" in txt.lower():
            sn, cn = "FREER", "Capt. Noah"
        elif "chester" in txt.lower():
            sn, cn = "CHESTER", "Daughter of Capt. Chester RN"
        elif "?" in txt:
            cn = txt.replace("?", "").strip()
            sn = "??"
        else:
            sn, cn = "??", txt.strip()
        people[new_pid] = {
            "id": new_pid,
            "has_original_page": False,
            "surname": sn,
            "cname": cn,
            "raw_tree_label": txt,
            "is_direct_ancestor": False,
            "ahnentafel": "",
            "dates": "????-????",
            "birth": "",
            "death": "ob. infancy" if "infancy" in txt.lower() else "",
            "marriage": "",
            "profession": "",
            "notes": "",
            "generation": str(cur_gen),
            "tree_id": tid,
            "trees_appeared": [tid] if tid else [],
            "index_letter": sn[0].upper() if sn and sn[0].isalpha() else "Other",
            "gender": "U",
            "parents": [],
            "spouses": [],
            "children": [],
            "siblings": [],
        }
        return new_pid

    def parse_segment(raw_seg_html, cur_gen, tid):
        up_m = re.search(
            r'<A\s+HREF="([0-9]+)\.html"[^>]*>\s*<IMG[^>]*butt_up[^>]*>\s*</A>',
            raw_seg_html,
            flags=re.I,
        )
        up_tree = up_m.group(1) if up_m else None
        h = re.sub(
            r'<A\s+HREF="[0-9]+\.html"[^>]*>\s*<IMG[^>]*>\s*</A>',
            "",
            raw_seg_html,
            flags=re.I,
        )
        h = re.sub(r"<IMG[^>]*>", "", h, flags=re.I)
        notes = re.findall(
            r'<A\s+HREF="[^"]*notes\.html#(note\d+)"[^>]*>(.*?)</A>', h, flags=re.I
        )

        def repl_note(m):
            txt = m.group(2).strip()
            if re.match(r"^Note\s*\d+$", txt, re.I):
                return ""
            return txt

        h = re.sub(
            r'<A\s+HREF="[^"]*notes\.html#(note\d+)"[^>]*>(.*?)</A>',
            repl_note,
            h,
            flags=re.I,
        )
        p_m = re.search(r'<A\s+HREF="\.\./people/([0-9]+)\.html"[^>]*>', h, flags=re.I)
        explicit_pid = p_m.group(1) if p_m else None
        h = re.sub(r"<BR\s*/?>", "\n", h, flags=re.I)
        h = re.sub(r"<[^>]+>", "", h).replace("&nbsp;", " ").replace("&quot;", '"').replace("&nbsp", " ")
        lines = [l.strip() for l in h.split("\n") if l.strip()]
        has_issue = False
        issue_text = ""
        clean_lines = []
        for l in lines:
            if l.lower().startswith("-- issue") or l.lower().startswith("--issue"):
                has_issue = True
                issue_text = l
            else:
                clean_lines.append(l)
        full_txt = re.sub(r"\s+", " ", " ".join(clean_lines)).strip()
        order_m = re.match(r"^\(([123])\)\s*(.*)$", full_txt)
        marriage_order = int(order_m.group(1)) if order_m else None
        if order_m:
            full_txt = order_m.group(2).strip()
        pid = match_or_create_person(full_txt, explicit_pid, cur_gen, tid)
        return {
            "pid": pid,
            "up_tree": up_tree,
            "notes": [n[0].lower() for n in notes],
            "has_issue": has_issue,
            "issue_text": issue_text,
            "lines": clean_lines,
            "text": full_txt,
            "marriage_order": marriage_order,
        }

    for fpath in tree_files:
        tid = os.path.basename(fpath).replace(".html", "")
        with open(fpath, "r", encoding="cp1252", errors="replace") as f:
            html = f.read()
        title_m = re.search(r"<TITLE>(.*?)</TITLE>", html, re.S | re.I)
        title = clean_html_text(title_m.group(1)) if title_m else f"Family Tree {tid}"
        doc_notes = [
            m.group(1).lower()
            for m in re.finditer(r"<P>Document notes:.*?</P>", html, re.S | re.I)
            for m in re.finditer(r"notes\.html#(note\d+)", m.group(0), re.I)
        ]
        has_angelos_link = "angelos.html" in html.lower()
        trs = re.findall(r"<TR[^>]*>(.*?)</TR>", html, re.S | re.I)

        gen_rows = []
        down_links_by_col = {}

        for tr_idx, tr in enumerate(trs):
            tds = re.findall(r"<TD([^>]*)>(.*?)</TD>", tr, re.S | re.I)
            gen_num = None
            row_cells = []
            for col_idx, (attrs, content) in enumerate(tds):
                # Check for down arrow in this cell
                dn_m = re.search(
                    r'<A\s+HREF="([0-9]+)\.html"[^>]*>\s*<IMG[^>]*butt_dn[^>]*>\s*</A>',
                    content,
                    flags=re.I,
                )
                if dn_m:
                    down_links_by_col[col_idx] = dn_m.group(1)
                elif "butt_dn" in content.lower() and tid == "00000179":
                    # Fix unlinked butt_dn.gif in 00000179.html under Alexander Logan (00000177)
                    down_links_by_col[col_idx] = "00000177"

                m = re.search(r'BGCOLOR="?([^"\s>]+)"?', attrs, re.I)
                if m:
                    color = m.group(1).upper()
                    if color == "SILVER":
                        g = clean_html_text(content)
                        if g:
                            gen_num = g
                    else:
                        row_cells.append((col_idx, color, content))
            if gen_num is not None and row_cells:
                gen_rows.append({"gen": gen_num, "raw_cells": row_cells, "nodes": []})

        # Parse cells in each generation row, merging continuation 2nd-marriage cells
        for r_idx, grow in enumerate(gen_rows):
            cur_gen = grow["gen"]
            nodes = []
            for col_idx, color, content in grow["raw_cells"]:
                raw_parts = re.split(
                    r"(?:<BR\s*/?>|\n)\s*m\.\s*(?:<BR\s*/?>|\n)", content, flags=re.I
                )
                # Check if this cell is a continuation 2nd-marriage cell for the previous node in the same row
                first_clean = clean_html_text(content)
                is_continuation = (
                    first_clean.startswith("(2)")
                    or first_clean.lower().startswith("m. (2)")
                ) and len(nodes) > 0

                if is_continuation:
                    prev_node = nodes[-1]
                    # Strip leading "m." if present
                    cont_html = re.sub(r"^\s*m\.\s*(?:<BR\s*/?>)?", "", content.strip(), flags=re.I)
                    sp_seg = parse_segment(cont_html, cur_gen, tid)
                    sp_seg["color"] = color
                    sp_seg["col_idx"] = col_idx
                    prev_node["spouses"].append(sp_seg)
                    prev_node["colors"].append((color, col_idx, len(prev_node["spouses"]) - 1))
                else:
                    primary_seg = parse_segment(raw_parts[0], cur_gen, tid)
                    spouses_list = []
                    for sp_part in raw_parts[1:]:
                        h_sp = re.sub(r"<BR\s*/?>", "\n", sp_part, flags=re.I)
                        subparts = re.split(r"(?:^|\n)\s*(?=\([123]\)\s)", h_sp)
                        for sub in subparts:
                            if not sub.strip():
                                continue
                            sp_seg = parse_segment(sub, cur_gen, tid)
                            sp_seg["color"] = color
                            sp_seg["col_idx"] = col_idx
                            spouses_list.append(sp_seg)

                    node = {
                        "node_id": f"{tid}_g{cur_gen}_c{col_idx}",
                        "col_idx": col_idx,
                        "color": color,
                        "colors": [(color, col_idx, 0 if spouses_list else None)],
                        "gen": cur_gen,
                        "primary": primary_seg,
                        "spouses": spouses_list,
                        "down_tree": None,
                        "parent_node_id": None,
                        "parent_spouse_idx": None,
                    }
                    nodes.append(node)
            grow["nodes"] = nodes
            del grow["raw_cells"]

        # Attach down_tree links to the bottom row (or matching column)
        if gen_rows and down_links_by_col:
            bottom_nodes = gen_rows[-1]["nodes"]
            for col_idx, dn_tid in down_links_by_col.items():
                # Find node in bottom_nodes with matching or closest col_idx
                best_node = min(bottom_nodes, key=lambda n: abs(n["col_idx"] - col_idx))
                best_node["down_tree"] = dn_tid

        # Link parent nodes between consecutive generation rows
        for r_idx in range(1, len(gen_rows)):
            prev_nodes = gen_rows[r_idx - 1]["nodes"]
            cur_nodes = gen_rows[r_idx]["nodes"]
            if not prev_nodes:
                continue
            if len(prev_nodes) == 1 and len(prev_nodes[0]["colors"]) == 1:
                pnode = prev_nodes[0]
                for cnode in cur_nodes:
                    cnode["parent_node_id"] = pnode["node_id"]
                    cnode["parent_spouse_idx"] = 0 if pnode["spouses"] else None
            else:
                # Match by (color, closest col_idx)
                color_candidates = []
                for pnode in prev_nodes:
                    for c_val, c_col, sp_idx in pnode["colors"]:
                        color_candidates.append((c_val, c_col, pnode, sp_idx))
                for cnode in cur_nodes:
                    c_color = cnode["color"]
                    c_col = cnode["col_idx"]
                    matching = [x for x in color_candidates if x[0] == c_color]
                    if matching:
                        chosen = min(matching, key=lambda x: abs(x[1] - c_col))
                    else:
                        chosen = min(color_candidates, key=lambda x: abs(x[1] - c_col))
                    cnode["parent_node_id"] = chosen[2]["node_id"]
                    cnode["parent_spouse_idx"] = chosen[3]

        trees[tid] = {
            "id": tid,
            "title": title,
            "doc_notes": doc_notes,
            "has_angelos_link": has_angelos_link,
            "rows": gen_rows,
        }

    # 6. Build global parent-child and spouse-spouse relationships from trees AND people_pages
    parent_child_pairs = set()  # (parent_pid, child_pid)
    spouse_pairs = []  # list of dicts: (p1_pid, p2_pid, marriage_info, tree_id)
    spouse_pair_set = set()

    def add_spouse_pair(p1, p2, marriage_info="", tid=None):
        if not p1 or not p2 or p1 == p2:
            return
        key = tuple(sorted([p1, p2]))
        if key not in spouse_pair_set:
            spouse_pair_set.add(key)
            spouse_pairs.append(
                {"p1": p1, "p2": p2, "marriage": marriage_info, "tree_id": tid}
            )
        if p2 not in people[p1]["spouses"]:
            people[p1]["spouses"].append(p2)
        if p1 not in people[p2]["spouses"]:
            people[p2]["spouses"].append(p1)

    def add_parent_child(parent_pid, child_pid):
        if not parent_pid or not child_pid or parent_pid == child_pid:
            return
        parent_child_pairs.add((parent_pid, child_pid))
        if parent_pid not in people[child_pid]["parents"]:
            people[child_pid]["parents"].append(parent_pid)
        if child_pid not in people[parent_pid]["children"]:
            people[parent_pid]["children"].append(child_pid)

    # Extract relationships from all 61 trees
    for tid, tdata in trees.items():
        node_by_id = {}
        for row in tdata["rows"]:
            for node in row["nodes"]:
                node_by_id[node["node_id"]] = node
                p1 = node["primary"]["pid"]
                for sp in node["spouses"]:
                    p2 = sp["pid"]
                    if p1 and p2:
                        m_info = people[p1].get("marriage", "") or people[p2].get("marriage", "")
                        add_spouse_pair(p1, p2, m_info, tid)

        for row in tdata["rows"]:
            for node in row["nodes"]:
                child_pid = node["primary"]["pid"]
                pnode_id = node["parent_node_id"]
                if child_pid and pnode_id and pnode_id in node_by_id:
                    pnode = node_by_id[pnode_id]
                    parent1_pid = pnode["primary"]["pid"]
                    add_parent_child(parent1_pid, child_pid)
                    sp_idx = node["parent_spouse_idx"]
                    if sp_idx is not None and 0 <= sp_idx < len(pnode["spouses"]):
                        # If parent had multiple spouses in a single cell (like 00000176 James Logan m. (1) ??? (2) Katherine Steuart),
                        # prefer the direct ancestor spouse or single spouse
                        if len(pnode["spouses"]) == 1:
                            add_parent_child(pnode["spouses"][0]["pid"], child_pid)
                        elif len(pnode["colors"]) > 1:
                            add_parent_child(pnode["spouses"][sp_idx]["pid"], child_pid)
                        else:
                            # Multiple spouses in same cell: check if one is direct ancestor or has non-empty pid
                            valid_sps = [s["pid"] for s in pnode["spouses"] if s["pid"]]
                            if len(valid_sps) == 1:
                                add_parent_child(valid_sps[0], child_pid)

    # Also extract relationships from the 138 people_pages (Spouse & Issue rows)
    for pid, rec in people_pages.items():
        p_gen_str = rec.get("Generation", "")
        p_gen = int(p_gen_str) if p_gen_str.lstrip("-").isdigit() else None
        child_gen = str(p_gen - 1) if p_gen is not None else None

        resolved_spouses = []
        for idx, sp_raw in enumerate(rec["spouses_raw"]):
            if sp_raw == "&nbsp;" or not sp_raw:
                resolved_spouses.append(None)
                continue
            m = re.search(r'HREF="([0-9]+)\.html"', sp_raw, re.I)
            if m and m.group(1) in people:
                sp_pid = m.group(1)
            else:
                txt = clean_html_text(sp_raw)
                sp_pid = match_or_create_person(txt, None, p_gen_str, rec.get("tree_id"))
            resolved_spouses.append(sp_pid)
            m_info = rec["marriages_raw"][idx] if idx < len(rec["marriages_raw"]) else ""
            add_spouse_pair(pid, sp_pid, m_info, rec.get("tree_id"))

        for idx, iss_block in enumerate(rec["issue_raw"]):
            if iss_block == "&nbsp;" or not iss_block:
                continue
            sp_for_issue = resolved_spouses[idx] if idx < len(resolved_spouses) else (resolved_spouses[0] if resolved_spouses else None)
            lines = re.split(r"<BR\s*/?>", iss_block, flags=re.I)
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                m = re.search(r'HREF="([0-9]+)\.html"', line, re.I)
                if m and m.group(1) in people:
                    c_pid = m.group(1)
                else:
                    txt = clean_html_text(line).replace("**", "")
                    c_pid = match_or_create_person(txt, None, child_gen, rec.get("tree_id"))
                if c_pid:
                    add_parent_child(pid, c_pid)
                    if sp_for_issue:
                        add_parent_child(sp_for_issue, c_pid)

    # Also check Access DB child spouse fields (AS..PS) for families without trees (like Hall :18/4:)
    for pid, mr in mdb_by_pid.items():
        p_gen = int(mr["Level"]) if mr.get("Level") is not None else None
        child_gen = str(p_gen - 1) if p_gen is not None else None
        for let in "ABCDEFGHIJKLMNOP":
            c_str = mr.get(let)
            cs_str = mr.get(let + "S")
            if c_str and cs_str:
                # Find child in people[pid]["children"]
                c_words = set(norm_words(c_str))
                matched_child = None
                for cid in people[pid]["children"]:
                    cw = set(norm_words(people[cid]["cname"]))
                    if c_words & cw:
                        matched_child = cid
                        break
                if matched_child and not people[matched_child]["spouses"]:
                    # Try to match cs_str in child_gen
                    cs_clean = re.sub(r"\b(sp|issue|div)\b", "", cs_str, flags=re.I).strip()
                    sp_pid = match_or_create_person(cs_clean, None, child_gen, people[pid]["tree_id"])
                    if sp_pid and sp_pid != matched_child:
                        add_spouse_pair(matched_child, sp_pid, "", people[pid]["tree_id"])

    # Compute siblings and infer gender for all people
    for pid, person in people.items():
        person["gender"] = infer_gender(person["cname"], person["profession"] + " " + person["notes"])

    # Second pass gender inference using spouses (if one spouse is M, the other is F)
    for pair in spouse_pairs:
        p1, p2 = people[pair["p1"]], people[pair["p2"]]
        if p1["gender"] == "M" and p2["gender"] == "U":
            p2["gender"] = "F"
        elif p1["gender"] == "F" and p2["gender"] == "U":
            p2["gender"] = "M"
        elif p2["gender"] == "M" and p1["gender"] == "U":
            p1["gender"] = "F"
        elif p2["gender"] == "F" and p1["gender"] == "U":
            p1["gender"] = "M"

    # Compute siblings
    for pid, person in people.items():
        sibs = []
        for par_id in person["parents"]:
            for cid in people[par_id]["children"]:
                if cid != pid and cid not in sibs:
                    sibs.append(cid)
        person["siblings"] = sibs

    # Build structured families list (for GEDCOM & Excel export)
    families = []
    fam_by_spouses = {}
    for idx, pair in enumerate(spouse_pairs, 1):
        p1_id, p2_id = pair["p1"], pair["p2"]
        p1, p2 = people[p1_id], people[p2_id]
        # Order husband (M) first, wife (F) second where known
        if p2["gender"] == "M" and p1["gender"] != "M":
            husb_id, wife_id = p2_id, p1_id
        else:
            husb_id, wife_id = p1_id, p2_id
        shared_children = [
            cid for cid in people[husb_id]["children"] if cid in people[wife_id]["children"]
        ]
        fid = f"F{idx:04d}"
        fam = {
            "id": fid,
            "husband_id": husb_id,
            "wife_id": wife_id,
            "marriage": pair["marriage"] or people[husb_id]["marriage"] or people[wife_id]["marriage"],
            "children": shared_children,
            "tree_id": pair["tree_id"] or people[husb_id]["tree_id"] or people[wife_id]["tree_id"],
        }
        families.append(fam)
        fam_by_spouses[tuple(sorted([husb_id, wife_id]))] = fam

    # Also add single-parent family units for children who only have 1 known parent in the dataset
    for pid, person in people.items():
        if len(person["parents"]) == 1:
            par_id = person["parents"][0]
            # Check if par_id has a family where child is already listed
            already_in_fam = any(pid in f["children"] for f in families)
            if not already_in_fam:
                # Check if we already created a single-parent family for par_id
                existing = next(
                    (f for f in families if (f["husband_id"] == par_id and not f["wife_id"]) or (f["wife_id"] == par_id and not f["husband_id"])),
                    None,
                )
                if existing:
                    if pid not in existing["children"]:
                        existing["children"].append(pid)
                else:
                    fid = f"F{len(families) + 1:04d}"
                    par = people[par_id]
                    is_f = par["gender"] == "F"
                    families.append(
                        {
                            "id": fid,
                            "husband_id": None if is_f else par_id,
                            "wife_id": par_id if is_f else None,
                            "marriage": par["marriage"],
                            "children": [pid],
                            "tree_id": par["tree_id"],
                        }
                    )

    # Apply user-requested updates for Richard Francis Muir (d. 2019) and Christine Mary Gosling (d. 2021)
    if "00000282" in people:
        people["00000282"]["death"] = "2019"
        people["00000282"]["dates"] = "1930-2019"
    if "00000140" in people:
        people["00000140"]["death"] = "2021"
        people["00000140"]["dates"] = "1935-2021"

    direct_index_order = [
        (
            ref_txt,
            pid,
            "1930-2019"
            if pid == "00000282"
            else ("1935-2021" if pid == "00000140" else dates_txt),
        )
        for ref_txt, pid, dates_txt in direct_index_order
    ]

    for tdata in trees.values():
        for grow in tdata["rows"]:
            for node in grow["nodes"]:
                for seg in [node["primary"]] + node["spouses"]:
                    if seg.get("pid") == "00000282":
                        seg["lines"] = [
                            re.sub(r"\(\s*1930\s*-\s*(?:\?+|\s*)\)", "(1930-2019)", l)
                            for l in seg["lines"]
                        ]
                        seg["text"] = re.sub(
                            r"\(\s*1930\s*-\s*(?:\?+|\s*)\)", "(1930-2019)", seg["text"]
                        )
                    elif seg.get("pid") == "00000140":
                        seg["lines"] = [
                            re.sub(r"\(\s*1935\s*-\s*(?:\?+|\s*)\)", "(1935-2021)", l)
                            for l in seg["lines"]
                        ]
                        seg["text"] = re.sub(
                            r"\(\s*1935\s*-\s*(?:\?+|\s*)\)", "(1935-2021)", seg["text"]
                        )

    for mr in mdb_rows:
        if mr.get("Reference") == ":2/1:":
            if mr.get("A"):
                mr["A"] = re.sub(r"1930-\s*", "1930-2019 ", mr["A"])
            if mr.get("AS"):
                mr["AS"] = re.sub(r"1935-\s*$", "1935-2021", mr["AS"])

    ds = {
        "mdb_cols": mdb_cols,
        "mdb_rows": mdb_rows,
        "people": people,
        "trees": trees,
        "families": families,
        "notes_map": notes_map,
        "direct_index_order": direct_index_order,
    }
    if os.path.exists(MASTER_XLSX_PATH):
        apply_excel_overrides(ds, MASTER_XLSX_PATH)
    return ds


def read_xlsx_sheet(filepath, target_sheet_name="People"):
    """Pure-Python reader for an OpenXML (.xlsx) worksheet (handles sharedStrings, inlineStr, numbers, and sparse columns)."""
    def col_to_idx(col_str):
        idx = 0
        for ch in col_str:
            if "A" <= ch <= "Z":
                idx = idx * 26 + (ord(ch) - 64)
        return idx - 1

    with zipfile.ZipFile(filepath, "r") as zf:
        namelist = set(zf.namelist())
        shared_strings = []
        if "xl/sharedStrings.xml" in namelist:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                texts = [
                    t.text or ""
                    for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                ]
                shared_strings.append("".join(texts))

        # Find target worksheet path via workbook.xml and workbook.xml.rels
        sheet_path = "xl/worksheets/sheet1.xml"
        if "xl/workbook.xml" in namelist and "xl/_rels/workbook.xml.rels" in namelist:
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rid_to_target = {}
            for rel in rels_root:
                rid = rel.attrib.get("Id")
                targ = rel.attrib.get("Target", "")
                if rid and targ:
                    targ_clean = targ.lstrip("/")
                    if not targ_clean.startswith("xl/"):
                        targ_clean = "xl/" + targ_clean
                    rid_to_target[rid] = targ_clean
            for sh in wb_root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
                name = sh.attrib.get("name", "")
                rid = sh.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                if name.strip().lower() == target_sheet_name.lower() and rid in rid_to_target:
                    sheet_path = rid_to_target[rid]
                    break

        if sheet_path not in namelist:
            return [], []

        ws_root = ET.fromstring(zf.read(sheet_path))
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        all_rows = []
        for row_el in ws_root.iter(f"{ns}row"):
            row_dict = {}
            max_c = -1
            cur_c = 0
            for c_el in row_el.findall(f"{ns}c"):
                r_ref = c_el.attrib.get("r", "")
                m_col = re.match(r"^([A-Z]+)", r_ref)
                c_idx = col_to_idx(m_col.group(1)) if m_col else cur_c
                cur_c = c_idx + 1
                max_c = max(max_c, c_idx)

                c_type = c_el.attrib.get("t", "")
                val = ""
                if c_type == "inlineStr":
                    texts = [t.text or "" for t in c_el.iter(f"{ns}t")]
                    val = "".join(texts)
                else:
                    v_el = c_el.find(f"{ns}v")
                    v_txt = v_el.text if (v_el is not None and v_el.text is not None) else ""
                    if c_type == "s":
                        if v_txt.isdigit() and int(v_txt) < len(shared_strings):
                            val = shared_strings[int(v_txt)]
                    elif c_type == "b":
                        val = "Yes" if v_txt == "1" else "No"
                    else:
                        if re.match(r"^-?\d+\.0$", v_txt):
                            val = v_txt[:-2]
                        else:
                            val = v_txt
                row_dict[c_idx] = val.strip()
            if max_c >= 0:
                all_rows.append([row_dict.get(i, "") for i in range(max_c + 1)])

        if not all_rows:
            return [], []
        headers = all_rows[0]
        data_rows = []
        for r in all_rows[1:]:
            if any(cell != "" for cell in r):
                padded = r + [""] * max(0, len(headers) - len(r))
                data_rows.append(dict(zip(headers, padded)))
        return headers, data_rows


def extract_year_label(date_str):
    if not date_str:
        return ""
    s = date_str.strip()
    if re.match(r"^\?+$", s):
        return "????"
    m = re.search(r"\b(1[4-9]\d\d(?:/\d{1,2})?|20\d\d)\b", s)
    if m:
        prefix = "c" if re.match(r"^c\.?\s*\d", s, re.I) else ""
        return prefix + m.group(1)
    return s


def compute_life_dates(birth_str, death_str):
    b_yr = extract_year_label(birth_str)
    d_yr = extract_year_label(death_str)
    if b_yr and d_yr:
        return f"{b_yr}-{d_yr}"
    elif b_yr and not d_yr:
        return f"{b_yr}-"
    elif not b_yr and d_yr:
        return f"????-{d_yr}"
    return ""


def apply_excel_overrides(ds, xlsx_path):
    """
    Applies edits and newly added people/children/spouses from the 'People' sheet
    of exports/muir_family_tree.xlsx into the dataset.
    """
    try:
        headers, rows = read_xlsx_sheet(xlsx_path, "People")
    except Exception as e:
        print(f"Warning: Could not read {xlsx_path}: {e}")
        return

    if not rows or "Surname" not in headers:
        return

    people = ds["people"]
    trees = ds["trees"]
    direct_index_order = ds["direct_index_order"]

    # Determine next available Pxxxx ID for new rows without a Person_ID
    max_p_num = 1500
    for pid in people:
        if pid.startswith("P") and pid[1:].isdigit():
            max_p_num = max(max_p_num, int(pid[1:]))

    # First pass: create any new people and update scalar fields on existing people
    excel_rels = {}  # pid -> (par_tokens, sp_tokens, ch_tokens)
    new_pids = []
    updated_pids = set()

    for r in rows:
        pid = r.get("Person_ID", "").strip()
        sn = r.get("Surname", "").strip()
        cn = r.get("Given_Names", "").strip()
        if not pid and not sn and not cn:
            continue

        is_new = False
        if not pid or pid not in people:
            is_new = True
            if not pid:
                max_p_num += 1
                pid = f"P{max_p_num}"
                r["Person_ID"] = pid
            new_pids.append(pid)

        da_str = r.get("Direct_Ancestor", "").strip().lower()
        is_da = da_str in ("yes", "true", "1", "y", "**")
        ahn = r.get("Ahnentafel_Ref", "").strip()
        gen = r.get("Generation", "").strip()
        sex = r.get("Gender", "").strip().upper()
        life_dates = r.get("Life_Dates", "").strip()
        birth = r.get("Birth", "").strip()
        death = r.get("Death", "").strip()
        marriage = r.get("Marriage", "").strip()
        prof = r.get("Profession", "").strip()
        notes = r.get("Notes", "").strip()
        tree_page = r.get("Primary_Tree_Page", "").strip()
        tid = ""
        if tree_page:
            tid = os.path.basename(tree_page).replace(".html", "")

        if not is_new:
            orig = people[pid]
            old_b, old_d, old_dates = orig["birth"], orig["death"], orig["dates"]
            old_cn, old_sn = orig["cname"], orig["surname"]

            # Compute Life_Dates strictly from Birth and Death (blank Death -> 'YYYY-', explicit '????' in Death -> 'YYYY-????')
            life_dates = compute_life_dates(birth, death)

            if (
                sn != old_sn
                or cn != old_cn
                or life_dates != old_dates
                or birth != old_b
                or death != old_d
                or notes != orig["notes"]
                or prof != orig["profession"]
                or marriage != orig["marriage"]
            ):
                updated_pids.add(pid)

            orig["surname"] = sn or orig["surname"]
            orig["cname"] = cn
            orig["is_direct_ancestor"] = is_da
            orig["ahnentafel"] = ahn
            if gen != "":
                orig["generation"] = gen
            if sex in ("M", "F", "U"):
                orig["gender"] = sex
            orig["dates"] = life_dates
            orig["birth"] = birth
            orig["death"] = death
            orig["marriage"] = marriage
            orig["profession"] = prof
            orig["notes"] = notes
            if tid:
                orig["tree_id"] = tid
                if tid not in orig["trees_appeared"]:
                    orig["trees_appeared"].append(tid)
        else:
            life_dates = compute_life_dates(birth, death)
            if sex not in ("M", "F"):
                sex = infer_gender(cn, prof + " " + notes)
            people[pid] = {
                "id": pid,
                "has_person_page": False,
                "surname": sn or "??",
                "cname": cn or "Unknown",
                "is_direct_ancestor": is_da,
                "ahnentafel": ahn,
                "generation": gen,
                "dates": life_dates,
                "birth": birth,
                "death": death,
                "marriage": marriage,
                "profession": prof,
                "notes": notes,
                "tree_id": tid or None,
                "trees_appeared": [tid] if tid else [],
                "parents": [],
                "spouses": [],
                "children": [],
                "siblings": [],
                "gender": sex,
                "mdb_record": None,
            }
            updated_pids.add(pid)

        def split_tokens(s):
            if not s:
                return []
            return [t.strip() for t in re.split(r"[;,]", s) if t.strip()]

        par_tokens = split_tokens(r.get("Parent_IDs", "")) or split_tokens(r.get("Parent_Names", ""))
        sp_tokens = split_tokens(r.get("Spouse_IDs", "")) or split_tokens(r.get("Spouse_Names", ""))
        ch_tokens = split_tokens(r.get("Child_IDs", "")) or split_tokens(r.get("Child_Names", ""))
        excel_rels[pid] = (par_tokens, sp_tokens, ch_tokens)

    # Helper to resolve either a Person_ID or a full name to a valid pid
    name_to_pid = {}
    for xid, xp in people.items():
        disp = f"{xp['cname']} {xp['surname']}".strip().lower()
        rev = f"{xp['surname']}, {xp['cname']}".strip().lower()
        name_to_pid[disp] = xid
        name_to_pid[rev] = xid

    def resolve_ref(tok):
        if tok in people:
            return tok
        tl = tok.lower()
        if tl in name_to_pid:
            return name_to_pid[tl]
        return None

    # Rebuild relationships from Excel rows and ensure two-way consistency
    for pid in excel_rels:
        people[pid]["parents"] = []
        people[pid]["spouses"] = []
        people[pid]["children"] = []

    for pid, (par_toks, sp_toks, ch_toks) in excel_rels.items():
        for t in par_toks:
            par_id = resolve_ref(t)
            if par_id and par_id != pid:
                if par_id not in people[pid]["parents"]:
                    people[pid]["parents"].append(par_id)
                if pid not in people[par_id]["children"]:
                    people[par_id]["children"].append(pid)
        for t in sp_toks:
            sp_id = resolve_ref(t)
            if sp_id and sp_id != pid:
                if sp_id not in people[pid]["spouses"]:
                    people[pid]["spouses"].append(sp_id)
                if pid not in people[sp_id]["spouses"]:
                    people[sp_id]["spouses"].append(pid)
        for t in ch_toks:
            ch_id = resolve_ref(t)
            if ch_id and ch_id != pid:
                if ch_id not in people[pid]["children"]:
                    people[pid]["children"].append(ch_id)
                if pid not in people[ch_id]["parents"]:
                    people[ch_id]["parents"].append(pid)

    # Fill in missing Generation or tree_id for newly added people from their parents or spouse
    for pid in new_pids:
        p = people[pid]
        if not p["generation"]:
            for par_id in p["parents"]:
                pg = str(people[par_id]["generation"])
                if pg.lstrip("-").isdigit():
                    p["generation"] = str(int(pg) - 1)
                    break
        if not p["generation"]:
            for sp_id in p["spouses"]:
                sg = str(people[sp_id]["generation"])
                if sg:
                    p["generation"] = sg
                    break
        if not p["tree_id"]:
            for rel_id in p["parents"] + p["spouses"] + p["children"]:
                if people[rel_id].get("tree_id"):
                    p["tree_id"] = people[rel_id]["tree_id"]
                    if p["tree_id"] not in p["trees_appeared"]:
                        p["trees_appeared"].append(p["tree_id"])
                    break

    # Recompute siblings
    for pid, person in people.items():
        sibs = []
        for par_id in person["parents"]:
            for cid in people[par_id]["children"]:
                if cid != pid and cid not in sibs:
                    sibs.append(cid)
        person["siblings"] = sibs

    # Rebuild families list
    new_families = []
    seen_sp_pairs = set()
    for pid, p in people.items():
        for sp_id in p["spouses"]:
            key = tuple(sorted([pid, sp_id]))
            if key in seen_sp_pairs:
                continue
            seen_sp_pairs.add(key)
            p1, p2 = people[pid], people[sp_id]
            if p2["gender"] == "M" and p1["gender"] != "M":
                husb_id, wife_id = sp_id, pid
            else:
                husb_id, wife_id = pid, sp_id
            shared_children = [
                cid for cid in people[husb_id]["children"] if cid in people[wife_id]["children"]
            ]
            fid = f"F{len(new_families) + 1:04d}"
            new_families.append(
                {
                    "id": fid,
                    "husband_id": husb_id,
                    "wife_id": wife_id,
                    "marriage": people[husb_id]["marriage"] or people[wife_id]["marriage"],
                    "children": shared_children,
                    "tree_id": people[husb_id]["tree_id"] or people[wife_id]["tree_id"],
                }
            )
    for pid, person in people.items():
        if len(person["parents"]) == 1:
            par_id = person["parents"][0]
            if not any(pid in f["children"] for f in new_families):
                existing = next(
                    (
                        f
                        for f in new_families
                        if (f["husband_id"] == par_id and not f["wife_id"])
                        or (f["wife_id"] == par_id and not f["husband_id"])
                    ),
                    None,
                )
                if existing:
                    if pid not in existing["children"]:
                        existing["children"].append(pid)
                else:
                    fid = f"F{len(new_families) + 1:04d}"
                    par = people[par_id]
                    is_f = par["gender"] == "F"
                    new_families.append(
                        {
                            "id": fid,
                            "husband_id": None if is_f else par_id,
                            "wife_id": par_id if is_f else None,
                            "marriage": par["marriage"],
                            "children": [pid],
                            "tree_id": par["tree_id"],
                        }
                    )
    ds["families"] = new_families

    # Update direct_index_order dates for all direct ancestors
    ds["direct_index_order"] = [
        (
            ref_txt,
            pid,
            people[pid]["dates"] if pid in people and people[pid]["dates"] else dates_txt,
        )
        for ref_txt, pid, dates_txt in direct_index_order
    ]

    # Update 3-generation tree cards for all people AND append any newly added spouses/children
    for tid, tdata in trees.items():
        existing_tree_pids = set()
        for grow in tdata["rows"]:
            for node in grow["nodes"]:
                for seg in [node["primary"]] + node["spouses"]:
                    spid = seg.get("pid")
                    if spid:
                        existing_tree_pids.add(spid)
                    if spid and spid in people:
                        up_p = people[spid]
                        disp_name = (
                            f"{up_p['cname']} {up_p['surname']}".strip()
                            if up_p["surname"] != "??"
                            else up_p["cname"]
                        )
                        if up_p["dates"]:
                            seg["lines"] = [disp_name, f"({up_p['dates']})"]
                            seg["text"] = f"{disp_name} ({up_p['dates']})"
                        else:
                            seg["lines"] = [disp_name]
                            seg["text"] = disp_name

        # Check if any primary node on this tree has a newly added spouse or newly added child
        for r_idx, grow in enumerate(list(tdata["rows"])):
            for node in grow["nodes"]:
                prim_pid = node["primary"].get("pid")
                if not prim_pid or prim_pid not in people:
                    continue
                # 1. Newly added spouses for prim_pid
                node_sp_pids = {s.get("pid") for s in node["spouses"] if s.get("pid")}
                for sp_id in people[prim_pid]["spouses"]:
                    if sp_id in new_pids and sp_id not in node_sp_pids:
                        sp_p = people[sp_id]
                        disp_name = (
                            f"{sp_p['cname']} {sp_p['surname']}".strip()
                            if sp_p["surname"] != "??"
                            else sp_p["cname"]
                        )
                        node["spouses"].append(
                            {
                                "pid": sp_id,
                                "up_tree": None,
                                "notes": [],
                                "has_issue": False,
                                "issue_text": "",
                                "lines": [disp_name, f"({sp_p['dates']})"],
                                "text": f"{disp_name} ({sp_p['dates']})",
                                "marriage_order": None,
                                "color": node.get("color", "#8080FF"),
                                "col_idx": node.get("col_idx", 1),
                            }
                        )
                        existing_tree_pids.add(sp_id)

                # 2. Newly added children for prim_pid
                for ch_id in people[prim_pid]["children"]:
                    if ch_id in new_pids and ch_id not in existing_tree_pids:
                        ch_p = people[ch_id]
                        disp_name = (
                            f"{ch_p['cname']} {ch_p['surname']}".strip()
                            if ch_p["surname"] != "??"
                            else ch_p["cname"]
                        )
                        # Find or create child row (r_idx + 1)
                        if r_idx + 1 < len(tdata["rows"]):
                            target_row = tdata["rows"][r_idx + 1]
                        elif tid == (ch_p.get("tree_id") or people[prim_pid].get("tree_id")):
                            child_gen = ch_p["generation"] or str(int(grow["gen"]) - 1) if str(grow["gen"]).lstrip("-").isdigit() else ""
                            target_row = {"gen": child_gen, "nodes": []}
                            tdata["rows"].append(target_row)
                        else:
                            continue

                        new_col_idx = len(target_row["nodes"]) + 1
                        new_node = {
                            "node_id": f"{tid}_g{target_row['gen']}_c{new_col_idx}_{ch_id}",
                            "col_idx": new_col_idx,
                            "color": node.get("color", "#8080FF"),
                            "colors": [(node.get("color", "#8080FF"), new_col_idx, None)],
                            "gen": target_row["gen"],
                            "primary": {
                                "pid": ch_id,
                                "up_tree": None,
                                "notes": [],
                                "has_issue": False,
                                "issue_text": "",
                                "lines": [disp_name, f"({ch_p['dates']})"],
                                "text": f"{disp_name} ({ch_p['dates']})",
                                "marriage_order": None,
                            },
                            "spouses": [],
                            "down_tree": None,
                            "parent_node_id": node["node_id"],
                            "parent_spouse_idx": 0 if node["spouses"] else None,
                        }
                        target_row["nodes"].append(new_node)
                        existing_tree_pids.add(ch_id)
                        if tid not in ch_p["trees_appeared"]:
                            ch_p["trees_appeared"].append(tid)


if __name__ == "__main__":
    ds = build_dataset()
    print(f"Access MDB rows: {len(ds['mdb_rows'])} (cols: {len(ds['mdb_cols'])})")
    print(f"Total unified people: {len(ds['people'])}")
    print(f"Total tree pages: {len(ds['trees'])}")
    print(f"Total family units: {len(ds['families'])}")
    with_parents = sum(1 for p in ds["people"].values() if p["parents"])
    with_spouses = sum(1 for p in ds["people"].values() if p["spouses"])
    with_children = sum(1 for p in ds["people"].values() if p["children"])
    print(f"People with parents: {with_parents}, with spouses: {with_spouses}, with children: {with_children}")
