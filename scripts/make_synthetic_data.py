#!/usr/bin/env python3
"""Generate synthetic demo data for the coerced debt hackathon project.

Outputs (written to ../data relative to this script):
  credit_report.pdf  - a realistic, slightly messy credit report
  ground_truth.json  - correct labels for every account, for testing extraction and flagging
  dana_intake.json   - what Dana tells her advocate

Everything here is fictional: the person, the lenders, the credit bureau, the
addresses and the numbers. Phone numbers use the reserved 555-01XX range and
emails use example.com / example.net.

Run:  python3 scripts/make_synthetic_data.py
"""
import json
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

REPORT_DATE = date(2026, 10, 28)
LAW_CUTOFF = "2023-07-01"  # Civil Code 1798.97.5: notice process covers debts incurred on/after this date

PERSONA = {
    "name": "Dana M. Whitfield",
    "ssn_masked": "XXX-XX-4417",
    "year_of_birth": 1991,
    "phone": "(559) 555-0148",
    "email": "dana.whitfield@example.com",
    "addresses": [
        {"id": "A", "address": "88 Linden St Apt 3, Oakland, CA 94607", "from": "2019-01", "to": "2022-03"},
        {"id": "B", "address": "1427 Alder Creek Rd, Sacramento, CA 95819", "from": "2022-04", "to": "2025-01",
         "note": "lived with partner"},
        {"id": "C", "address": "610 Harmon Ave, Fresno, CA 93721", "from": "2025-02", "to": None},
    ],
    "relationship_with_abuser": {"from": "2022-04", "to": "2025-01"},
}

UNKNOWN_PHONE = "(916) 555-0193"

# Payment history window shown on the report: 24 months, 11/2024 through 10/2026.
WINDOW = [(2024 + (10 + i) // 12, (10 + i) % 12 + 1) for i in range(24)]


def history(change_points):
    """change_points: list of ("YYYY-MM", code). Each code holds until the next change point."""
    out = []
    for y, m in WINDOW:
        ym = f"{y:04d}-{m:02d}"
        code = "--"
        for start, c in change_points:
            if ym >= start:
                code = c
        out.append(code)
    return out


# ---------------------------------------------------------------------------
# Accounts. Display fields are deliberately inconsistent (dates, names,
# addresses) so extraction isn't trivial. Label fields drive ground_truth.json.
# ---------------------------------------------------------------------------
ACCOUNTS = [
    {
        "id": 5, "section": "negative",
        "creditor": "SUMMIT RECOVERY GROUP",
        "creditor_contact": "PO Box 40912, Irvine, CA 92623 · (800) 555-0161",
        "account_number": "XXXX-8820",
        "account_type": "Collection",
        "responsibility": "Individual",
        "name_on_account": "DANA WHITFIELD",
        "date_opened_display": "Jun 2025", "date_opened": "2025-06",
        "date_reported": "10/2026",
        "amounts": [("Original amount", 6400), ("Balance", 6912), ("Past due", 6912)],
        "status": "Collection",
        "original_creditor": "PACIFIC CREST CRD",
        "address_reported": "1427 ALDER CREEK ROAD, SACRAMENTO CA 95819", "address_id": "B",
        "phone_reported": UNKNOWN_PHONE,
        "history": history([("2025-06", "C")]),
        "remarks": "Placed for collection. Balance includes fees.",
        "secured": False,
    },
    {
        "id": 4, "section": "negative",
        "creditor": "PACIFIC CREST CARD",
        "creditor_contact": "PO Box 7720, Portland, OR 97208 · (800) 555-0127",
        "account_number": "XXXX-3391",
        "account_type": "Revolving - Credit card",
        "responsibility": "Individual",
        "name_on_account": "WHITFIELD, DANA",
        "date_opened_display": "2023-08-14", "date_opened": "2023-08-14",
        "date_reported": "06/2025",
        "amounts": [("Credit limit", 7000), ("High balance", 6400), ("Balance", 0), ("Past due", 0)],
        "status": "Charged off · Sold to another lender",
        "date_closed": "05/2025",
        "address_reported": "1427 Alder Crk Rd, Sacramento CA 95819", "address_id": "B",
        "phone_reported": UNKNOWN_PHONE,
        "history": history([("2023-08", "OK"), ("2024-12", "30"), ("2025-01", "60"), ("2025-02", "90"),
                            ("2025-03", "120"), ("2025-04", "150"), ("2025-05", "CO"), ("2025-06", "--")]),
        "remarks": "Charged off as bad debt. Transferred/sold.",
        "secured": False,
    },
    {
        "id": 7, "section": "negative",
        "creditor": "QUICKFUND PERSONAL LOAN",
        "creditor_contact": "2200 Market Pl Ste 400, San Jose, CA 95113 · (888) 555-0174",
        "account_number": "XXXX-6605",
        "account_type": "Installment - Personal loan (unsecured)",
        "responsibility": "Individual",
        "name_on_account": "DANA M WHITFIELD",
        "date_opened_display": "2025-03-04", "date_opened": "2025-03-04",
        "date_reported": "10/2026",
        "amounts": [("Original amount", 5000), ("Balance", 3500), ("Past due", 640), ("Monthly payment", 160)],
        "status": "120 days past due",
        "address_reported": "PO BOX 2291, SACRAMENTO CA 95812", "address_id": None,
        "phone_reported": UNKNOWN_PHONE,
        "history": history([("2025-03", "OK"), ("2026-07", "30"), ("2026-08", "60"), ("2026-09", "90"),
                            ("2026-10", "120")]),
        "remarks": "",
        "secured": False,
    },
    {
        "id": 6, "section": "negative",
        "creditor": "VALLEY AUTO FINANCE",
        "creditor_contact": "5100 Gateway Blvd, Stockton, CA 95210 · (209) 555-0135",
        "account_number": "XXXX-7142",
        "account_type": "Installment - Auto loan",
        "responsibility": "Joint",
        "name_on_account": "DANA M WHITFIELD",
        "date_opened_display": "11/05/2023", "date_opened": "2023-11-05",
        "date_reported": "10/2026",
        "amounts": [("Original amount", 21800), ("Balance", 14200), ("Past due", 812), ("Monthly payment", 406)],
        "status": "60 days past due",
        "collateral": "2021 compact SUV (secured)",
        # The "secured" detail lands on the next page, so the eligibility check has to stitch the block together.
        "force_page_break_before": "Collateral",
        "address_reported": "1427 ALDER CREEK ROAD, SACRAMENTO CA 95819", "address_id": "B",
        "phone_reported": PERSONA["phone"],
        "history": history([("2023-11", "OK"), ("2026-09", "30"), ("2026-10", "60")]),
        "remarks": "",
        "secured": True,
    },
    {
        "id": 3, "section": "negative",
        "creditor": "TECHMART FINANCING",
        "creditor_contact": "PO Box 1188, Columbus, OH 43216 · (800) 555-0152",
        "account_number": "XXXX-0573",
        "account_type": "Revolving - Store card",
        "responsibility": "Individual",
        "name_on_account": "DANA M WHITFIELD",
        "date_opened_display": "02/18/2023", "date_opened": "2023-02-18",
        "date_reported": "10/2026",
        "amounts": [("Credit limit", 1500), ("High balance", 1480), ("Balance", 1240), ("Past due", 1240)],
        "status": "Charged off · In collection",
        "date_closed": "12/2024",
        "address_reported": "1427 Alder Crk Rd, Sacramento CA 95819", "address_id": "B",
        "phone_reported": PERSONA["phone"],
        "history": history([("2023-02", "OK"), ("2024-06", "30"), ("2024-07", "60"), ("2024-08", "90"),
                            ("2024-09", "120"), ("2024-10", "150"), ("2024-11", "180"), ("2024-12", "C")]),
        "remarks": "Internal collection.",
        "secured": False,
    },
    {
        "id": 1, "section": "good",
        "creditor": "GOLDEN STATE STUDENT LENDING",
        "creditor_contact": "PO Box 900, Sacramento, CA 95812 · (800) 555-0110",
        "account_number": "XXXX-2280",
        "account_type": "Installment - Student loan",
        "responsibility": "Individual",
        "name_on_account": "DANA M WHITFIELD",
        "date_opened_display": "09/2016", "date_opened": "2016-09",
        "date_reported": "10/2026",
        "amounts": [("Original amount", 28500), ("Balance", 11420), ("Past due", 0), ("Monthly payment", 312)],
        "status": "Pays as agreed",
        "address_reported": "610 HARMON AVE, FRESNO CA 93721", "address_id": "C",
        "phone_reported": PERSONA["phone"],
        "history": history([("2016-09", "OK")]),
        "remarks": "",
        "secured": False,
    },
    {
        "id": 2, "section": "good",
        "creditor": "BAYLINE BANK VISA",
        "creditor_contact": "PO Box 3301, San Francisco, CA 94119 · (800) 555-0118",
        "account_number": "XXXX-9014",
        "account_type": "Revolving - Credit card",
        "responsibility": "Individual",
        "name_on_account": "WHITFIELD, DANA",
        "date_opened_display": "May 2018", "date_opened": "2018-05",
        "date_reported": "10/2026",
        "amounts": [("Credit limit", 5000), ("High balance", 2140), ("Balance", 820), ("Monthly payment", 35)],
        "status": "Pays as agreed",
        "address_reported": "610 Harmon Ave, Fresno CA 93721", "address_id": "C",
        "phone_reported": PERSONA["phone"],
        "history": history([("2018-05", "OK")]),
        "remarks": "",
        "secured": False,
    },
    {
        "id": 8, "section": "good",
        "creditor": "FRESNO COMMUNITY CREDIT UNION",
        "creditor_contact": "1450 Tulare St, Fresno, CA 93721 · (559) 555-0186",
        "account_number": "XXXX-4471",
        "account_type": "Revolving - Credit card",
        "responsibility": "Individual",
        "name_on_account": "DANA M WHITFIELD",
        "date_opened_display": "04/2025", "date_opened": "2025-04",
        "date_reported": "10/2026",
        "amounts": [("Credit limit", 2000), ("High balance", 640), ("Balance", 310), ("Monthly payment", 25)],
        "status": "Pays as agreed",
        "address_reported": "610 HARMON AVE, FRESNO CA 93721", "address_id": "C",
        "phone_reported": PERSONA["phone"],
        "history": history([("2025-04", "OK")]),
        "remarks": "",
        "secured": False,
    },
]

INQUIRIES = [
    ("FRESNO COMMUNITY CREDIT UNION", "04/10/2025"),
    ("QUICKFUND PERSONAL LOAN", "03/02/2025"),
    ("VALLEY AUTO FINANCE", "11/05/2023"),
    ("PACIFIC CREST CARD", "08/13/2023"),
    ("TECHMART FINANCING", "02/18/2023"),
]

# ---------------------------------------------------------------------------
# Ground truth labels
# ---------------------------------------------------------------------------
LABELS = {
    1: {"label": "legit"},
    2: {"label": "legit"},
    3: {"label": "coerced", "mechanism": "duress (pressured to open the card, which he used)",
        "eligible_for_notice": False,
        "exclusion_reason": "Incurred before July 1, 2023 (Civil Code 1798.97.5). The notice process doesn't "
                            "apply, though she could still raise coerced debt in a cross-complaint if sued.",
        "detection_signals": ["Opened during the relationship", "Creditor still reports address B, which she left in 2025-01",
                              "Dana names it in her intake story"]},
    4: {"label": "coerced", "mechanism": "fraud (opened without her knowledge)",
        "eligible_for_notice": True,
        "current_holder_account_id": 5,
        "notes": "Original creditor sold the debt; the notice goes to the current holder, Summit Recovery Group.",
        "detection_signals": ["Phone on file (916) 555-0193 is not hers",
                              "Opened during the relationship, at the shared address",
                              "Creditor still reports address B after she left"]},
    5: {"label": "coerced", "mechanism": "same debt as account 4 (collection)",
        "eligible_for_notice": True, "linked_account_id": 4, "notice_recipient": True,
        "detection_signals": ["Original creditor field matches account 4 (name abbreviated)",
                              "Original amount matches account 4's high balance ($6,400)",
                              "Same unknown phone (916) 555-0193"]},
    6: {"label": "coerced", "mechanism": "duress (pressured to co-sign)",
        "eligible_for_notice": False,
        "exclusion_reason": "Secured debt (Civil Code 1798.97.4(a)).",
        "detection_signals": ["Opened during the relationship", "Dana names it in her intake story"]},
    7: {"label": "coerced", "mechanism": "fraud (opened without her knowledge)",
        "eligible_for_notice": True, "notice_recipient": True,
        "detection_signals": ["Opened 2025-03-04, after she moved out in 2025-01",
                              "Address is a PO box she never had", "Phone on file (916) 555-0193 is not hers",
                              "Hard inquiry 03/02/2025"]},
    8: {"label": "legit",
        "notes": "False-positive trap: opened after she moved, but at her own new address with her own phone."},
}


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = letter
LEFT, RIGHT = 48, PAGE_W - 48
TOP, BOTTOM = PAGE_H - 44, 64
GRAY = HexColor("#E9ECEF")
DARK = HexColor("#343A40")
MID = HexColor("#6C757D")
RED = HexColor("#B02A37")


class NumberedCanvas(canvas.Canvas):
    """Canvas that adds 'Page X of N' footers once the total page count is known."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(MID)
            self.drawString(LEFT, 36, "SYNTHETIC DATA for a hackathon demo. Not a real person, lender, or credit bureau. "
                                      "Any resemblance to real entities is coincidental.")
            self.drawRightString(RIGHT, 36, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


class ReportWriter:
    def __init__(self, path):
        self.c = NumberedCanvas(str(path), pagesize=letter)
        self.c.setTitle("Sample Credit Report - Synthetic Data")
        self.c.setAuthor("Northfield Credit Data (fictional)")
        self.split_accounts = []
        self._header()

    # --- page furniture -------------------------------------------------
    def _header(self):
        c = self.c
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LEFT, TOP, "SAMPLE CREDIT REPORT — SYNTHETIC DATA")
        c.setFillColor(DARK)
        c.setFont("Helvetica", 8)
        c.drawString(LEFT, TOP - 12, f"Northfield Credit Data (fictional)  ·  Report date {REPORT_DATE:%m/%d/%Y}  ·  "
                                     "Report # NCD-2026-10-48213  ·  Prepared for: DANA M WHITFIELD")
        c.setStrokeColor(MID)
        c.setLineWidth(0.6)
        c.line(LEFT, TOP - 18, RIGHT, TOP - 18)
        self.y = TOP - 32

    def new_page(self):
        self.c.showPage()
        self._header()

    def room(self, h):
        return self.y - h >= BOTTOM

    def need(self, h):
        if not self.room(h):
            self.new_page()

    # --- primitives -----------------------------------------------------
    def section(self, title):
        self.need(72)  # header plus the start of the first block, so headers never sit alone
        c = self.c
        c.setFillColor(DARK)
        c.rect(LEFT, self.y - 4, RIGHT - LEFT, 15, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(LEFT + 6, self.y, title)
        c.setFillColor(black)
        self.y -= 22

    def text(self, s, size=8.5, bold=False, indent=0, color=black, h=None):
        self.need(h or size + 3.5)
        self.c.setFillColor(color)
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(LEFT + indent, self.y, s)
        self.c.setFillColor(black)
        self.y -= h or size + 3.5

    def kv(self, label, value, x, y, label_w=82):
        self.c.setFont("Helvetica", 7.5)
        self.c.setFillColor(MID)
        self.c.drawString(x, y, label)
        self.c.setFont("Helvetica", 8.5)
        self.c.setFillColor(black)
        self.c.drawString(x + label_w, y, value)

    # --- account block (rows can break across pages, like real reports) --
    def account(self, a):
        rows = self._account_rows(a)
        title_h = rows[0][0]
        # Don't strand a title alone at the bottom of a page.
        if not self.room(title_h + rows[1][0] + rows[2][0]):
            self.new_page()
        split = False
        for i, (h, draw) in enumerate(rows):
            target = a.get("force_page_break_before")
            forced = target is not None and getattr(draw, "tag", None) == target
            if forced or not self.room(h):
                self.new_page()
                split = True
                self.text(f"{a['creditor']}  (continued)", size=8, bold=True, color=MID, h=13)
            draw(self.y)
            self.y -= h
        if split:
            self.split_accounts.append(a["id"])
        self.y -= 10

    def _account_rows(self, a):
        c = self.c
        rows = []

        def title(y):
            c.setFillColor(GRAY)
            c.rect(LEFT, y - 4, RIGHT - LEFT, 15, stroke=0, fill=1)
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(LEFT + 5, y, a["creditor"])
            c.setFont("Helvetica", 8.5)
            c.drawRightString(RIGHT - 5, y, f"Account # {a['account_number']}")
        rows.append((19, title))

        def contact(y):
            c.setFont("Helvetica", 7.5)
            c.setFillColor(MID)
            c.drawString(LEFT + 5, y, a["creditor_contact"])
            c.setFillColor(black)
        rows.append((13, contact))

        left = [("Account type", a["account_type"]),
                ("Responsibility", a["responsibility"]),
                ("Date opened", a["date_opened_display"]),
                ("Date reported", a["date_reported"]),
                ("Name on account", a["name_on_account"])]
        if a.get("date_closed"):
            left.append(("Date closed", a["date_closed"]))
        right = [(k, f"${v:,}") for k, v in a["amounts"]] + [("Status", a["status"])]
        col2 = LEFT + (RIGHT - LEFT) / 2 + 20
        for i in range(max(len(left), len(right))):
            l = left[i] if i < len(left) else None
            r = right[i] if i < len(right) else None

            def kvrow(y, l=l, r=r):
                if l:
                    self.kv(l[0], l[1], LEFT + 5, y)
                if r:
                    self.kv(r[0], r[1], col2, y, label_w=78)
            rows.append((12, kvrow))

        full = []
        if a.get("original_creditor"):
            full.append(("Original creditor", a["original_creditor"]))
        if a.get("collateral"):
            full.append(("Collateral", a["collateral"]))
        full.append(("Address reported", a["address_reported"]))
        full.append(("Phone reported", a["phone_reported"]))
        if a.get("remarks"):
            full.append(("Remarks", a["remarks"]))
        for k, v in full:
            def fullrow(y, k=k, v=v):
                self.kv(k, v, LEFT + 5, y)
            fullrow.tag = k  # lets an account force a page break right before a given field
            rows.append((12, fullrow))

        # 24-month payment history: two rows of 12 months.
        def hist_label(y):
            c.setFont("Helvetica", 7.5)
            c.setFillColor(MID)
            c.drawString(LEFT + 5, y, "Payment history (OK = on time, 30-180 = days late, CO = charged off, "
                                      "C = collection, -- = no data)")
            c.setFillColor(black)
        rows.append((18, hist_label))
        for half in (0, 1):
            months = WINDOW[half * 12:(half + 1) * 12]
            codes = a["history"][half * 12:(half + 1) * 12]

            def hrow(y, months=months, codes=codes):
                x0, w = LEFT + 5, (RIGHT - LEFT - 10) / 12
                for j, ((yy, mm), code) in enumerate(zip(months, codes)):
                    x = x0 + j * w
                    c.setFont("Courier", 6.5)
                    c.setFillColor(MID)
                    c.drawString(x, y + 7, f"{mm:02d}/{yy % 100:02d}")
                    c.setFont("Courier-Bold", 7.5)
                    c.setFillColor(RED if code not in ("OK", "--") else black)
                    c.drawString(x, y - 1, code)
                c.setFillColor(black)
            rows.append((21, hrow))
        return rows

    def save(self):
        self.c.showPage()
        self.c.save()


def build_pdf(path):
    r = ReportWriter(path)

    r.section("PERSONAL INFORMATION")
    r.text("Names reported:  DANA M WHITFIELD;  WHITFIELD, DANA;  DANA WHITFIELD")
    r.text(f"SSN:  {PERSONA['ssn_masked']}        Year of birth:  {PERSONA['year_of_birth']}")
    r.text("Addresses reported:", bold=True)
    for addr, first in [("610 HARMON AVE, FRESNO CA 93721  (current)", "02/2025"),
                        ("PO BOX 2291, SACRAMENTO CA 95812", "03/2025"),
                        ("1427 Alder Crk Rd, Sacramento CA 95819", "08/2023"),
                        ("1427 ALDER CREEK ROAD, SACRAMENTO CA 95819", "04/2022"),
                        ("88 LINDEN ST APT 3, OAKLAND CA 94607", "01/2019")]:
        r.text(f"{addr}  —  first reported {first}", indent=12)
    r.text(f"Phone numbers reported:  {PERSONA['phone']};  {UNKNOWN_PHONE}")
    r.text("Employers reported:  VALLEY HOME HEALTH SVCS (fictional)")
    r.y -= 6

    negative = [a for a in ACCOUNTS if a["section"] == "negative"]
    good = [a for a in ACCOUNTS if a["section"] == "good"]
    total_balance = sum(dict(a["amounts"]).get("Balance", 0) for a in ACCOUNTS)
    r.section("SUMMARY")
    r.text(f"Total accounts: {len(ACCOUNTS)}     Accounts with negative information: {len(negative)}     "
           f"Collection accounts: 1     Accounts in good standing: {len(good)}")
    r.text(f"Total balances: ${total_balance:,}     Public records: 0     Hard inquiries: {len(INQUIRIES)}")
    r.y -= 6

    r.section("ACCOUNTS WITH NEGATIVE INFORMATION")
    for a in negative:
        r.account(a)

    r.section("ACCOUNTS IN GOOD STANDING")
    for a in good:
        r.account(a)

    r.section("HARD INQUIRIES (companies that requested your credit report)")
    for name, d in INQUIRIES:
        r.text(f"{name}  —  {d}", indent=6)
    r.y -= 6

    r.section("PUBLIC RECORDS AND CONSUMER STATEMENT")
    r.text("Public records: none reported.     Consumer statement: none.")
    r.y -= 8
    r.text("End of report.", color=MID)
    r.save()
    return r.split_accounts


def build_ground_truth(split_accounts):
    accounts = []
    for a in sorted(ACCOUNTS, key=lambda a: a["id"]):
        amounts = dict(a["amounts"])
        entry = {
            "id": a["id"],
            "creditor": a["creditor"],
            "account_number": a["account_number"],
            "account_type": a["account_type"],
            "secured": a["secured"],
            "date_opened": a["date_opened"],
            "status": a["status"],
            "balance": amounts.get("Balance"),
            "address_reported": a["address_reported"],
            "address_matches_persona": a["address_id"],
            "phone_reported": a["phone_reported"],
            "phone_is_hers": a["phone_reported"] == PERSONA["phone"],
            "split_across_page_break": a["id"] in split_accounts,
        }
        if a.get("original_creditor"):
            entry["original_creditor"] = a["original_creditor"]
        entry.update(LABELS[a["id"]])
        accounts.append(entry)

    by_id = {a["id"]: a for a in ACCOUNTS}
    return {
        "_note": "Synthetic data. Correct answers for testing extraction, linking, flagging and eligibility.",
        "report_date": REPORT_DATE.isoformat(),
        "law_cutoff_date": LAW_CUTOFF,
        "persona": PERSONA,
        "accounts": accounts,
        "expected_letters": [
            {"recipient": by_id[5]["creditor"], "recipient_contact": by_id[5]["creditor_contact"],
             "account_ids": [4, 5], "amount": 6912,
             "why": "Coerced (fraud), unsecured, incurred 2023-08-14. Debt was sold, so the notice goes to the collector."},
            {"recipient": by_id[7]["creditor"], "recipient_contact": by_id[7]["creditor_contact"],
             "account_ids": [7], "amount": 3500,
             "why": "Coerced (fraud), unsecured, incurred 2025-03-04."},
        ],
        "expected_exclusions": [
            {"account_id": 3, "reason": "Incurred before 2023-07-01"},
            {"account_id": 6, "reason": "Secured debt"},
        ],
        "expected_legit": [1, 2, 8],
    }


INTAKE = {
    "_note": "Synthetic data. What Dana tells her advocate at intake.",
    "client": {
        "name": PERSONA["name"],
        "phone": PERSONA["phone"],
        "email": PERSONA["email"],
        "mailing_address": "610 Harmon Ave, Fresno, CA 93721",
        "contact_preference": "Written communication only, by mail",
    },
    "address_history": PERSONA["addresses"],
    "relationship": {"from": "2022-04", "to": "2025-01", "note": "Lived together at 1427 Alder Creek Rd, Sacramento"},
    "story": ("He handled all our money and pressured me to sign things. He made me co-sign the car loan and open "
              "a TechMart card that he used. I left in January 2025. Since then, collectors have been calling about "
              "a credit card and a loan I never opened. I don't know what else is out there."),
    "safety": {
        "name_the_abuser": False,
        "reason": "Disclosing his identity is likely to lead to further abuse.",
    },
    "documentation_available": [
        {"type": "qualified_third_party_certification",
         "provider": "Domestic violence counselor, Central Valley Family Safety Center (fictional)",
         "status": "Counselor has agreed to sign a certification"},
    ],
    "credit_report_file": "credit_report.pdf",
}


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    split = build_pdf(DATA / "credit_report.pdf")
    (DATA / "ground_truth.json").write_text(json.dumps(build_ground_truth(split), indent=2) + "\n")
    (DATA / "dana_intake.json").write_text(json.dumps(INTAKE, indent=2) + "\n")
    print(f"Wrote {DATA}/credit_report.pdf, ground_truth.json, dana_intake.json")
    print(f"Accounts split across a page break: {split or 'none'}")


if __name__ == "__main__":
    main()
