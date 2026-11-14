"""Download the public inputs for a scenario and write the small extracts the simulation reads.

Raw downloads go to data/raw/ (git-ignored) with SHA-256 sums in data/raw/SHA256SUMS. Extracts (rows for the
scenario's county and window only, no other changes) go to data/processed/ and are small enough to commit.

    uv run python scripts/fetch_data.py --scenario beryl_2024
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hearth.scenario import PROCESSED, RAW, load  # noqa: E402

EMPOWER = "https://empowerprogram.hhs.gov/2024_HHSemPOWERMapHistoricalDataset.xlsx"
FIGSHARE = "https://api.figshare.com/v2/articles/24237376"  # EAGLE-I recorded outages 2014-2025 (ORNL)
IEM = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
CMS_DME = "https://data.cms.gov/data-api/v1/dataset/27c150fd-8578-43b1-bba5-6388987e32af/data"  # DME by Geography and Service, 2024
CMS_DFR = "https://data.cms.gov/data-api/v1/dataset/f8610e87-ba25-43a3-a49e-927dbc8701ae/data"  # Medicare Dialysis Facilities FY2026
DEVICE_HCPCS = {"oxygen": ["E1390"], "ventilator": ["E0465", "E0466", "E0467"], "feeding_pump": ["B9002"]}
ZCTA = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/7/query"  # Census 2020 ZCTAs
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
http = httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "hearth-sim-fetch"})


def save(name: str, data: bytes) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_bytes(data)
    sums = RAW / "SHA256SUMS"
    lines = [l for l in (sums.read_text().splitlines() if sums.exists() else []) if not l.endswith(f"  {name}")]
    sums.write_text("\n".join(sorted(lines + [f"{hashlib.sha256(data).hexdigest()}  {name}"])) + "\n")
    print(f"raw  {name}  {len(data):,} bytes")
    return RAW / name


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with (PROCESSED / name).open("w", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows([header, *rows])
    print(f"proc {name}  {len(rows):,} rows")


# ---- emPOWER: xlsx read with the standard library (only one sheet, only three columns) ----
def empower(sc: dict) -> list[str]:
    path = RAW / "empower_2024.xlsx"
    if not path.exists():
        save(path.name, http.get(EMPOWER).raise_for_status().content)
    z = zipfile.ZipFile(path)
    rid = next(s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
               for s in ET.fromstring(z.read("xl/workbook.xml")).iter(NS + "sheet") if s.get("name") == "Zip Code")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    sheet = "xl/" + next(r.get("Target") for r in rels if r.get("Id") == rid)
    strings = ["".join(si.itertext()) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")]
    month = sc["empower_month"]
    want = ["Zip_Code", "FIPS_Code", f"{month}_Power_Dependent_Devices_DME", f"{month}_O2_Services_Any_DME"]
    cols, rows = None, []
    for _, el in ET.iterparse(z.open(sheet)):
        if el.tag != NS + "row":
            continue
        cells = {}
        for c in el.iter(NS + "c"):
            v = c.find(NS + "v")
            text = "" if v is None else (strings[int(v.text)] if c.get("t") == "s" else v.text)
            cells[re.match(r"[A-Z]+", c.get("r")).group()] = text.strip()  # the sheet pads keys and headers with spaces
        el.clear()
        if cols is None:
            cols = {name: letter for letter, name in cells.items()}
            continue
        row = [cells.get(cols[w], "") for w in want]
        if row[1] == sc["fips"]:
            rows.append(row)
    write_csv(f"empower_{sc['name']}.csv", want, sorted(rows))
    return sorted(r[0] for r in rows)


# ---- EAGLE-I: the 2024 file is sorted by FIPS, so fetch only our county's bytes by HTTP Range ----
def eaglei(sc: dict) -> None:
    year = sc["start"][:4]
    files = {f["name"]: f for f in http.get(FIGSHARE).raise_for_status().json()["files"]}
    mcc = save("MCC.csv", http.get(files["MCC.csv"]["download_url"]).raise_for_status().content)
    total = {r["County_FIPS"].lstrip("﻿").zfill(5): int(r["Customers"])
             for r in csv.DictReader(io.StringIO(mcc.read_text(encoding="utf-8-sig")))}[sc["fips"]]
    assert total == sc["customer_total"], f"MCC.csv says {total:,} customers, scenario says {sc['customer_total']:,}"
    f = files[f"eaglei_outages_{year}.csv"]
    url, size = str(http.head(f["download_url"]).url), f["size"]  # resolve the redirect once

    def get(lo: int, hi: int) -> bytes:
        return http.get(url, headers={"Range": f"bytes={lo}-{hi - 1}"}).raise_for_status().content

    def fips_at(off: int) -> tuple[int, str]:
        """(byte offset of the first full line at or after off, its FIPS)."""
        chunk = get(off, min(off + 4096, size))
        start = 0 if off == 0 else chunk.index(b"\n") + 1
        return off + start, chunk[start:start + 5].decode()

    def first_at_least(key: str) -> int:
        lo, hi = 0, size
        while hi - lo > 4096:
            mid = (lo + hi) // 2
            line_off, fips = fips_at(mid)
            lo, hi = (mid, hi) if fips < key or fips == "fips_" else (lo, mid)
        off, chunk = lo, get(lo, min(lo + 8192, size))  # finish linearly inside the last 4 KB
        lines = chunk.split(b"\n")
        pos = 0 if lo == 0 else len(lines[0]) + 1
        for line in lines[(0 if lo == 0 else 1):]:
            if line[:5].decode(errors="ignore") >= key and not line.startswith(b"fips"):
                return off + pos
            pos += len(line) + 1
        raise ValueError(key)

    lo, hi = first_at_least(sc["fips"]), first_at_least(str(int(sc["fips"]) + 1).zfill(5))
    header = get(0, 200).split(b"\n")[0]
    body = get(lo, hi)
    save(f"eaglei_outages_{year}_{sc['fips']}.csv", header + b"\n" + body)
    rows = [r for r in csv.reader(io.StringIO(body.decode())) if sc["start"][:10] <= r[4][:10] <= sc["end"][:10]]
    assert rows and all(r[0] == sc["fips"] for r in rows)
    write_csv(f"eaglei_{sc['name']}.csv", header.decode().split(","), rows)


# ---- Iowa Environmental Mesonet ASOS: routine hourly METARs, UTC ----
def weather(sc: dict) -> None:
    s, e = sc["start"], sc["end"]
    params = {"station": sc["weather_station"], "data": ["tmpf", "relh"], "tz": "Etc/UTC", "format": "onlycomma",
              "latlon": "no", "missing": "M", "trace": "T", "report_type": "3",
              "year1": s[:4], "month1": int(s[5:7]), "day1": int(s[8:10]),
              "year2": e[:4], "month2": int(e[5:7]), "day2": int(e[8:10]) + 1}
    text = http.get(IEM, params=params).raise_for_status().text
    save(f"iem_{sc['weather_station']}_{sc['name']}.csv", text.encode())
    rows = list(csv.reader(io.StringIO(text)))
    write_csv(f"weather_{sc['name']}.csv", rows[0], rows[1:])


# ---- Census TIGERweb ZCTA polygons for the emPOWER ZIPs (generalized to ~50 m) ----
def zcta(sc: dict, zips: list[str]) -> None:
    form = {"where": "ZCTA5 IN (" + ",".join(f"'{z}'" for z in zips) + ")", "outFields": "ZCTA5", "outSR": "4326",
            "maxAllowableOffset": "0.0005", "geometryPrecision": "5", "f": "geojson"}
    data = http.post(ZCTA, data=form).raise_for_status().content
    save(f"zcta_{sc['name']}.geojson", data)
    gj = json.loads(data)
    gj["features"] = sorted(({"type": "Feature", "properties": {"zip": f["properties"]["ZCTA5"]}, "geometry": f["geometry"]}
                             for f in gj["features"]), key=lambda f: f["properties"]["zip"])
    (PROCESSED / f"zcta_{sc['name']}.geojson").write_text(json.dumps(gj, separators=(",", ":")))
    missing = sorted(set(zips) - {f["properties"]["zip"] for f in gj["features"]})
    print(f"proc zcta_{sc['name']}.geojson  {len(gj['features'])} polygons; ZIPs without a ZCTA: {missing}")


# ---- device mix: CMS Medicare DME beneficiaries by HCPCS, and home dialysis from the dialysis facility reports ----
def device_counts(state_name: str = "Texas", state: str = "TX") -> dict:
    out, rows_kept = {}, []
    for device, codes in DEVICE_HCPCS.items():
        for code in codes:
            rows = http.get(CMS_DME, params={"filter[Rfrg_Prvdr_Geo_Desc]": state_name, "filter[HCPCS_Cd]": code}).raise_for_status().json()
            rows_kept += rows
            out[device] = out.get(device, 0) + sum(int(r["Tot_Suplr_Benes"]) for r in rows)  # rental and purchase rows
    fac = {}
    for m in ("ncmy4_f", "modhhdy4_f", "modccpdy4_f"):  # Medicare patients alive 12/31/2024; % home HD; % cycler PD
        rows = http.get(CMS_DFR, params={"filter[state]": state, "filter[Measure_ID]": m, "size": 5000}).raise_for_status().json()
        rows_kept += rows
        for r in rows:
            fac.setdefault(r["CCN"], {})[m] = float(r["Measure_Score"]) if r["Measure_Score"] not in ("", None) else None
    ok = [x for x in fac.values() if None not in (x.get("ncmy4_f"), x.get("modhhdy4_f"), x.get("modccpdy4_f"))]
    out["home_dialysis"] = round(sum(x["ncmy4_f"] * (x["modhhdy4_f"] + x["modccpdy4_f"]) / 100 for x in ok))
    save(f"cms_device_counts_{state}.json", json.dumps(rows_kept).encode())
    print(f"device counts {state} 2024: {out} ({len(ok)} dialysis facilities)")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="beryl_2024")
    p.add_argument("--device-counts", action="store_true", help="only print the CMS device counts for population.device_counts")
    args = p.parse_args()
    if args.device_counts:
        device_counts()
        sys.exit()
    sc = load(args.scenario)
    zips = empower(sc)
    zcta(sc, zips)
    eaglei(sc)
    weather(sc)
