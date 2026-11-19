#!/usr/bin/env python3
"""
Generates readable data exports in `exports/`:
1. exports/muir_family_tree.xlsx (Multi-sheet Excel workbook via pure-Python OpenXML)
2. exports/people.csv, exports/families.csv, exports/relationships.csv, exports/access_family_table.csv
3. exports/family_tree.xml (Structured XML)
4. exports/family_tree.json (Structured JSON)
5. exports/muir_family_tree.ged (Standard GEDCOM 5.5.1 for Ancestry.co.uk and genealogy software)
"""

import csv
import json
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.extract_data import ROOT_DIR, build_dataset

EXPORTS_DIR = os.path.join(ROOT_DIR, "exports")


def format_person_display_name(p):
    cn = p.get("cname", "").strip()
    sn = p.get("surname", "").strip()
    if sn and sn != "??":
        return f"{cn} {sn}".strip()
    return f"{cn} ({sn})".strip() if cn else sn


def split_date_and_place(raw_str):
    """Splits a string like '1872 Jan 21st Savannah, Ga, USA' or '1905 June 29th Shottemill' into (GEDCOM date, place)."""
    if not raw_str:
        return "", ""
    s = raw_str.strip()
    if s in ("????", "?", "-"):
        return "", ""

    months = {
        "jan": "JAN", "january": "JAN",
        "feb": "FEB", "february": "FEB",
        "mar": "MAR", "march": "MAR",
        "apr": "APR", "april": "APR",
        "may": "MAY",
        "jun": "JUN", "june": "JUN",
        "jul": "JUL", "july": "JUL",
        "aug": "AUG", "august": "AUG",
        "sep": "SEP", "sept": "SEP", "september": "SEP",
        "oct": "OCT", "october": "OCT",
        "nov": "NOV", "november": "NOV",
        "dec": "DEC", "december": "DEC",
    }

    # Pattern 1: YYYY Month DDth [Place]
    m = re.match(
        r"^(\d{4}(?:/\d{1,2})?)\s+([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+\d{4})?[\s,]*(.*)$",
        s,
    )
    if m:
        yr, mo_raw, day, rest = m.groups()
        mo = months.get(mo_raw.lower()[:3], mo_raw.upper())
        yr_clean = yr.split("/")[0]
        return f"{int(day)} {mo} {yr_clean}", rest.strip(" ,.")

    # Pattern 2: YYYY [Place]
    m2 = re.match(r"^(?:born\s+|c\.?\s*)?(\d{4})[\s,]*(.*)$", s, re.I)
    if m2:
        yr, rest = m2.groups()
        prefix = "ABT " if s.lower().startswith("c") else ""
        return f"{prefix}{yr}", rest.strip(" ,.")

    # Pattern 3: just contains a 4-digit year
    m3 = re.search(r"\b(1[4-9]\d\d|20\d\d)\b", s)
    if m3:
        yr = m3.group(1)
        rest = (s[: m3.start()] + " " + s[m3.end() :]).strip(" ,.-")
        return yr, rest

    return s, ""


def write_xlsx(filepath, sheets):
    """
    Pure-Python OpenXML (.xlsx) writer with styled header rows, auto-filters, frozen top row, and column widths.
    sheets: list of (sheet_name, headers, rows)
    """

    def col_letter(n):
        res = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            res = chr(65 + rem) + res
        return res

    with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        sheet_overrides = "\n".join(
            f'  <Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheet_overrides}
</Types>"""
        zf.writestr("[Content_Types].xml", content_types)

        # _rels/.rels
        rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
        zf.writestr("_rels/.rels", rels)

        # xl/_rels/workbook.xml.rels
        wb_rels_items = "\n".join(
            f'  <Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(sheets) + 1)
        )
        style_rid = len(sheets) + 1
        wb_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{wb_rels_items}
  <Relationship Id="rId{style_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)

        # xl/workbook.xml
        sheet_tags = "\n".join(
            f'    <sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (name, _, _) in enumerate(sheets, 1)
        )
        workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheet_tags}
  </sheets>
</workbook>"""
        zf.writestr("xl/workbook.xml", workbook_xml)

        # xl/styles.xml
        styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1E3A5F"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FFD9D9D9"/></left>
      <right style="thin"><color rgb="FFD9D9D9"/></right>
      <top style="thin"><color rgb="FFD9D9D9"/></top>
      <bottom style="thin"><color rgb="FFD9D9D9"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment vertical="center" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">
      <alignment vertical="top" wrapText="1"/>
    </xf>
  </cellXfs>
</styleSheet>"""
        zf.writestr("xl/styles.xml", styles_xml)

        # xl/worksheets/sheet{i}.xml
        for s_idx, (sname, headers, rows) in enumerate(sheets, 1):
            ncols = len(headers)
            last_col = col_letter(ncols)
            total_rows = len(rows) + 1

            # Calculate column widths
            col_widths = []
            for c_i, h in enumerate(headers):
                max_len = len(str(h))
                for r in rows[:200]:
                    if c_i < len(r) and r[c_i] is not None:
                        max_len = max(max_len, min(55, len(str(r[c_i]))))
                col_widths.append(max(12, min(55, max_len + 4)))

            cols_xml = "\n".join(
                f'    <col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
                for i, w in enumerate(col_widths, 1)
            )

            row_xml_parts = []
            # Header row
            h_cells = []
            for c_i, h_val in enumerate(headers, 1):
                c_ref = f"{col_letter(c_i)}1"
                val_esc = xml_escape(str(h_val))
                h_cells.append(
                    f'<c r="{c_ref}" s="1" t="inlineStr"><is><t>{val_esc}</t></is></c>'
                )
            row_xml_parts.append(f'    <row r="1" ht="24" customHeight="1">{"".join(h_cells)}</row>')

            for r_i, r_vals in enumerate(rows, 2):
                r_cells = []
                for c_i, val in enumerate(r_vals, 1):
                    c_ref = f"{col_letter(c_i)}{r_i}"
                    if val is None or val == "":
                        r_cells.append(f'<c r="{c_ref}" s="2"/>')
                    elif isinstance(val, (int, float)) and not isinstance(val, bool):
                        r_cells.append(f'<c r="{c_ref}" s="2"><v>{val}</v></c>')
                    else:
                        s_val = str(val)
                        # Strip any invalid XML control chars
                        s_val = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s_val)
                        val_esc = xml_escape(s_val)
                        r_cells.append(
                            f'<c r="{c_ref}" s="2" t="inlineStr"><is><t xml:space="preserve">{val_esc}</t></is></c>'
                        )
                row_xml_parts.append(f'    <row r="{r_i}">{"".join(r_cells)}</row>')

            sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <cols>
{cols_xml}
  </cols>
  <sheetData>
{chr(10).join(row_xml_parts)}
  </sheetData>
  <autoFilter ref="A1:{last_col}{total_rows}"/>
</worksheet>"""
            zf.writestr(f"xl/worksheets/sheet{s_idx}.xml", sheet_xml)


def generate_all_exports(ds=None):
    if ds is None:
        ds = build_dataset()

    os.makedirs(EXPORTS_DIR, exist_ok=True)
    people = ds["people"]
    families = ds["families"]
    trees = ds["trees"]
    mdb_cols = ds["mdb_cols"]
    mdb_rows = ds["mdb_rows"]

    # Sort people by surname, then cname, then generation
    sorted_pids = sorted(
        people.keys(),
        key=lambda pid: (
            0 if people[pid]["surname"] != "??" else 1,
            people[pid]["surname"].upper(),
            people[pid]["cname"].upper(),
            pid,
        ),
    )

    # 1. exports/access_family_table.csv
    access_csv_path = os.path.join(EXPORTS_DIR, "access_family_table.csv")
    with open(access_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(mdb_cols)
        for r in mdb_rows:
            writer.writerow([r.get(c, "") if r.get(c) is not None else "" for c in mdb_cols])

    # 2. exports/people.csv
    people_headers = [
        "Person_ID",
        "Surname",
        "Given_Names",
        "Full_Name",
        "Direct_Ancestor",
        "Ahnentafel_Ref",
        "Generation",
        "Gender",
        "Life_Dates",
        "Birth",
        "Death",
        "Marriage",
        "Profession",
        "Notes",
        "Parent_IDs",
        "Parent_Names",
        "Spouse_IDs",
        "Spouse_Names",
        "Child_IDs",
        "Child_Names",
        "Primary_Tree_Page",
        "Person_Page",
    ]
    people_rows = []
    for pid in sorted_pids:
        p = people[pid]
        par_names = "; ".join(format_person_display_name(people[x]) for x in p["parents"])
        sp_names = "; ".join(format_person_display_name(people[x]) for x in p["spouses"])
        ch_names = "; ".join(format_person_display_name(people[x]) for x in p["children"])
        gen_val = int(p["generation"]) if str(p["generation"]).lstrip("-").isdigit() else p["generation"]
        people_rows.append(
            [
                pid,
                p["surname"],
                p["cname"],
                format_person_display_name(p),
                "Yes" if p["is_direct_ancestor"] else "No",
                p["ahnentafel"],
                gen_val,
                p["gender"],
                p["dates"],
                p["birth"],
                p["death"],
                p["marriage"],
                p["profession"],
                p["notes"],
                "; ".join(p["parents"]),
                par_names,
                "; ".join(p["spouses"]),
                sp_names,
                "; ".join(p["children"]),
                ch_names,
                f"tree/{p['tree_id']}.html" if p["tree_id"] else "",
                f"people/{pid}.html",
            ]
        )

    people_csv_path = os.path.join(EXPORTS_DIR, "people.csv")
    with open(people_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(people_headers)
        writer.writerows(people_rows)

    # 3. exports/families.csv
    fam_headers = [
        "Family_ID",
        "Partner1_ID",
        "Partner1_Name",
        "Partner2_ID",
        "Partner2_Name",
        "Marriage_Details",
        "Children_Count",
        "Child_IDs",
        "Child_Names",
        "Tree_Page",
    ]
    fam_rows = []
    for fam in families:
        h_id = fam["husband_id"]
        w_id = fam["wife_id"]
        h_name = format_person_display_name(people[h_id]) if h_id else ""
        w_name = format_person_display_name(people[w_id]) if w_id else ""
        c_names = "; ".join(format_person_display_name(people[cid]) for cid in fam["children"])
        fam_rows.append(
            [
                fam["id"],
                h_id or "",
                h_name,
                w_id or "",
                w_name,
                fam["marriage"],
                len(fam["children"]),
                "; ".join(fam["children"]),
                c_names,
                f"tree/{fam['tree_id']}.html" if fam["tree_id"] else "",
            ]
        )

    families_csv_path = os.path.join(EXPORTS_DIR, "families.csv")
    with open(families_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fam_headers)
        writer.writerows(fam_rows)

    # 4. exports/relationships.csv
    rel_headers = [
        "Relationship_Type",
        "Source_Person_ID",
        "Source_Person_Name",
        "Target_Person_ID",
        "Target_Person_Name",
        "Source_Generation",
        "Target_Generation",
        "Details",
    ]
    rel_rows = []
    for pid in sorted_pids:
        p = people[pid]
        for sp_id in p["spouses"]:
            if pid < sp_id:
                sp = people[sp_id]
                rel_rows.append(
                    [
                        "SPOUSE",
                        pid,
                        format_person_display_name(p),
                        sp_id,
                        format_person_display_name(sp),
                        p["generation"],
                        sp["generation"],
                        p["marriage"] or sp["marriage"],
                    ]
                )
        for ch_id in p["children"]:
            ch = people[ch_id]
            rel_rows.append(
                [
                    "PARENT_CHILD",
                    pid,
                    format_person_display_name(p),
                    ch_id,
                    format_person_display_name(ch),
                    p["generation"],
                    ch["generation"],
                    "Parent -> Child",
                ]
            )

    rel_csv_path = os.path.join(EXPORTS_DIR, "relationships.csv")
    with open(rel_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(rel_headers)
        writer.writerows(rel_rows)

    # 5. exports/muir_family_tree.xlsx (Multi-sheet Excel file)
    mdb_sheet_rows = [
        [r.get(c, "") if r.get(c) is not None else "" for c in mdb_cols]
        for r in mdb_rows
    ]
    how_to_headers = ["Step / Topic", "How to Update Your Family Tree"]
    how_to_rows = [
        [
            "1. Editing Existing People",
            "On the 'People' tab, edit any person's Surname, Given_Names, Birth, Death, Marriage, Profession, or Notes. If you update Birth or Death, Life_Dates (e.g. 1930-2019) updates automatically when you rebuild.",
        ],
        [
            "2. Adding a New Child",
            "Add a new row at the bottom of the 'People' tab. Fill in Surname, Given_Names, Gender (M/F), and Birth. In the 'Parent_IDs' column, enter their parents' Person_IDs separated by a semicolon (for example: 00000242; 00000333). You can leave Person_ID, Generation, and Child_IDs blank — they will be filled in automatically!",
        ],
        [
            "3. Adding a New Spouse",
            "Add a new row at the bottom of the 'People' tab with Surname, Given_Names, Gender (M/F), Birth/Death, and Marriage date. In the 'Spouse_IDs' column, enter their partner's Person_ID (for example: 00000567).",
        ],
        [
            "4. Updating the Website & GEDCOM",
            "Save and close this Excel file (exports/muir_family_tree.xlsx), then double-click 'Update Website.command' in your Family Tree folder. All website pages (docs/), 3-generation trees, interactive explorer, CSV/XML/JSON exports, and the Ancestry.co.uk GEDCOM (.ged) file will update automatically.",
        ],
    ]
    xlsx_path = os.path.join(EXPORTS_DIR, "muir_family_tree.xlsx")
    write_xlsx(
        xlsx_path,
        [
            ("People", people_headers, people_rows),
            ("Families & Marriages", fam_headers, fam_rows),
            ("Relationships", rel_headers, rel_rows),
            ("Access DB (Family Table)", mdb_cols, mdb_sheet_rows),
            ("How to Edit", how_to_headers, how_to_rows),
        ],
    )

    # 6. exports/family_tree.xml
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<MuirFamilyTree>",
        "  <Metadata>",
        "    <Title>The Muir Family Tree &amp; Genealogy Archive</Title>",
        f"    <TotalPeople>{len(people)}</TotalPeople>",
        f"    <TotalFamilies>{len(families)}</TotalFamilies>",
        f"    <TotalTreePages>{len(trees)}</TotalTreePages>",
        f"    <AccessDatabaseRecords>{len(mdb_rows)}</AccessDatabaseRecords>",
        "  </Metadata>",
        "  <People>",
    ]
    for pid in sorted_pids:
        p = people[pid]
        xml_lines.append(
            f'    <Person id="{xml_escape(pid)}" directAncestor="{"true" if p["is_direct_ancestor"] else "false"}" ahnentafel="{xml_escape(p["ahnentafel"])}" generation="{xml_escape(str(p["generation"]))}" gender="{xml_escape(p["gender"])}">'
        )
        xml_lines.append(f"      <Surname>{xml_escape(p['surname'])}</Surname>")
        xml_lines.append(f"      <GivenNames>{xml_escape(p['cname'])}</GivenNames>")
        xml_lines.append(f"      <FullName>{xml_escape(format_person_display_name(p))}</FullName>")
        xml_lines.append(f"      <LifeDates>{xml_escape(p['dates'])}</LifeDates>")
        if p["birth"]:
            xml_lines.append(f"      <Birth>{xml_escape(p['birth'])}</Birth>")
        if p["death"]:
            xml_lines.append(f"      <Death>{xml_escape(p['death'])}</Death>")
        if p["marriage"]:
            xml_lines.append(f"      <Marriage>{xml_escape(p['marriage'])}</Marriage>")
        if p["profession"]:
            xml_lines.append(f"      <Profession>{xml_escape(p['profession'])}</Profession>")
        if p["notes"]:
            xml_lines.append(f"      <Notes>{xml_escape(p['notes'])}</Notes>")
        if p["tree_id"]:
            xml_lines.append(f"      <PrimaryTreePage>tree/{xml_escape(p['tree_id'])}.html</PrimaryTreePage>")
        xml_lines.append(f"      <ProfilePage>people/{xml_escape(pid)}.html</ProfilePage>")
        if p["parents"]:
            xml_lines.append("      <Parents>")
            for par_id in p["parents"]:
                xml_lines.append(
                    f'        <Parent ref="{xml_escape(par_id)}">{xml_escape(format_person_display_name(people[par_id]))}</Parent>'
                )
            xml_lines.append("      </Parents>")
        if p["spouses"]:
            xml_lines.append("      <Spouses>")
            for sp_id in p["spouses"]:
                xml_lines.append(
                    f'        <Spouse ref="{xml_escape(sp_id)}">{xml_escape(format_person_display_name(people[sp_id]))}</Spouse>'
                )
            xml_lines.append("      </Spouses>")
        if p["children"]:
            xml_lines.append("      <Children>")
            for ch_id in p["children"]:
                xml_lines.append(
                    f'        <Child ref="{xml_escape(ch_id)}">{xml_escape(format_person_display_name(people[ch_id]))}</Child>'
                )
            xml_lines.append("      </Children>")
        xml_lines.append("    </Person>")
    xml_lines.append("  </People>")

    xml_lines.append("  <Families>")
    for fam in families:
        xml_lines.append(
            f'    <Family id="{xml_escape(fam["id"])}" treeId="{xml_escape(fam["tree_id"] or "")}">'
        )
        if fam["husband_id"]:
            xml_lines.append(
                f'      <Partner1 ref="{xml_escape(fam["husband_id"])}">{xml_escape(format_person_display_name(people[fam["husband_id"]]))}</Partner1>'
            )
        if fam["wife_id"]:
            xml_lines.append(
                f'      <Partner2 ref="{xml_escape(fam["wife_id"])}">{xml_escape(format_person_display_name(people[fam["wife_id"]]))}</Partner2>'
            )
        if fam["marriage"]:
            xml_lines.append(f"      <Marriage>{xml_escape(fam['marriage'])}</Marriage>")
        if fam["children"]:
            xml_lines.append("      <Children>")
            for cid in fam["children"]:
                xml_lines.append(
                    f'        <Child ref="{xml_escape(cid)}">{xml_escape(format_person_display_name(people[cid]))}</Child>'
                )
            xml_lines.append("      </Children>")
        xml_lines.append("    </Family>")
    xml_lines.append("  </Families>")

    xml_lines.append("  <AccessDatabaseRecords table=\"Family\">")
    for idx, r in enumerate(mdb_rows, 1):
        xml_lines.append(f'    <Record index="{idx}">')
        for c in mdb_cols:
            val = r.get(c)
            if val is not None and val != "" and val is not False:
                xml_lines.append(f"      <{c}>{xml_escape(str(val))}</{c}>")
        xml_lines.append("    </Record>")
    xml_lines.append("  </AccessDatabaseRecords>")
    xml_lines.append("</MuirFamilyTree>")

    xml_path = os.path.join(EXPORTS_DIR, "family_tree.xml")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_lines) + "\n")

    # 7. exports/family_tree.json
    json_path = os.path.join(EXPORTS_DIR, "family_tree.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "title": "The Muir Family Tree & Genealogy Archive",
                    "total_people": len(people),
                    "total_families": len(families),
                    "total_trees": len(trees),
                    "access_db_rows": len(mdb_rows),
                },
                "people": [people[pid] for pid in sorted_pids],
                "families": families,
                "access_db_family_table": mdb_rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # 8. exports/muir_family_tree.ged (Standard GEDCOM 5.5.1 for Ancestry.co.uk)
    # Map each person to FAMC (families where they are a child) and FAMS (families where they are a spouse)
    famc_by_pid = {pid: [] for pid in people}
    fams_by_pid = {pid: [] for pid in people}
    for fam in families:
        fid = fam["id"]
        if fam["husband_id"]:
            fams_by_pid[fam["husband_id"]].append(fid)
        if fam["wife_id"]:
            fams_by_pid[fam["wife_id"]].append(fid)
        for cid in fam["children"]:
            famc_by_pid[cid].append(fid)

    ged_lines = [
        "0 HEAD",
        "1 SOUR MUIR_FAMILY_TREE",
        "2 NAME The Muir Family Tree Archive",
        "2 VERS 2.0",
        "1 DEST ANCESTRY",
        "1 DATE 11 NOV 2026",
        "1 SUBM @SUBM1@",
        "1 FILE muir_family_tree.ged",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "0 @SUBM1@ SUBM",
        "1 NAME Francis Muir",
    ]

    for pid in sorted_pids:
        p = people[pid]
        ged_id = f"@I{pid}@"
        ged_lines.append(f"0 {ged_id} INDI")
        sn = p["surname"] if p["surname"] != "??" else ""
        cn = p["cname"] or "Unknown"
        ged_lines.append(f"1 NAME {cn} /{sn}/")
        if cn:
            ged_lines.append(f"2 GIVN {cn}")
        if sn:
            ged_lines.append(f"2 SURN {sn}")
        if p["gender"] in ("M", "F"):
            ged_lines.append(f"1 SEX {p['gender']}")

        b_date, b_plac = split_date_and_place(p["birth"])
        if b_date or b_plac:
            ged_lines.append("1 BIRT")
            if b_date:
                ged_lines.append(f"2 DATE {b_date}")
            if b_plac:
                ged_lines.append(f"2 PLAC {b_plac}")

        d_date, d_plac = split_date_and_place(p["death"])
        if d_date or d_plac:
            ged_lines.append("1 DEAT")
            if d_date:
                ged_lines.append(f"2 DATE {d_date}")
            if d_plac:
                ged_lines.append(f"2 PLAC {d_plac}")
        elif p["death"].strip() in ("????", "?"):
            ged_lines.append("1 DEAT Y")

        if p["profession"]:
            ged_lines.append(f"1 OCCU {p['profession'][:240]}")

        note_parts = []
        if p["is_direct_ancestor"]:
            note_parts.append(
                f"Direct Ancestor ({p['ahnentafel']})" if p["ahnentafel"] else "Direct Ancestor (**)"
            )
        if p["generation"] != "":
            note_parts.append(f"Generation: {p['generation']}")
        if p["notes"]:
            note_parts.append(p["notes"])
        if note_parts:
            full_note = " | ".join(note_parts)
            ged_lines.append(f"1 NOTE {full_note}")

        for fid in famc_by_pid[pid]:
            ged_lines.append(f"1 FAMC @{fid}@")
        for fid in fams_by_pid[pid]:
            ged_lines.append(f"1 FAMS @{fid}@")

    for fam in families:
        fid = fam["id"]
        ged_lines.append(f"0 @{fid}@ FAM")
        if fam["husband_id"]:
            ged_lines.append(f"1 HUSB @I{fam['husband_id']}@")
        if fam["wife_id"]:
            ged_lines.append(f"1 WIFE @I{fam['wife_id']}@")
        if fam["marriage"]:
            m_date, m_plac = split_date_and_place(fam["marriage"])
            ged_lines.append("1 MARR")
            if m_date:
                ged_lines.append(f"2 DATE {m_date}")
            if m_plac:
                ged_lines.append(f"2 PLAC {m_plac}")
        for cid in fam["children"]:
            ged_lines.append(f"1 CHIL @I{cid}@")

    ged_lines.append("0 TRLR")
    ged_path = os.path.join(EXPORTS_DIR, "muir_family_tree.ged")
    with open(ged_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ged_lines) + "\n")

    return {
        "xlsx": xlsx_path,
        "people_csv": people_csv_path,
        "families_csv": families_csv_path,
        "relationships_csv": rel_csv_path,
        "access_csv": access_csv_path,
        "xml": xml_path,
        "json": json_path,
        "ged": ged_path,
    }


if __name__ == "__main__":
    paths = generate_all_exports()
    for k, v in paths.items():
        print(f"{k:18s}: {v} ({os.path.getsize(v):,} bytes)")
