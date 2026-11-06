#!/usr/bin/env python3
"""Render Dana's same 8 accounts in a layout modeled on the structure of a TransUnion
consumer disclosure, under a fictional bureau name.

What follows TransUnion's structure: section order (Personal Information, Accounts with
Adverse Information, Satisfactory Accounts, Collections, Regular / Promotional / Account Review
Inquiries), field labels, ">bracketed<" adverse values, the rating codes (OK, 30-120, COL, C/O, X),
masked and sometimes spaced account numbers, and creditor (not consumer) address/phone per account.
What does not: no TransUnion name, logo, colors, URLs or wording. Every page is marked synthetic.

Realism differences from credit_report.pdf that matter for the pipeline:
  - Accounts carry the CREDITOR's address and phone, not the consumer's. Unknown addresses and
    phones only appear in Personal Information, so Claude has to connect them by timing.
  - "Secured" isn't stated; it has to be inferred from Loan Type (AUTOMOBILE).
  - Hard inquiries older than two years have dropped off.
  - The collection sits in its own section, far from the original Pacific Crest entry.

Outputs: data/credit_report_tu_style.pdf, data/ground_truth_tu_style.json
Run:     python3 scripts/make_tu_style_report.py
"""
import importlib.util
import json
import re
from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("base", HERE / "make_synthetic_data.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

DATA = base.DATA
BUREAU = "Meridian Credit Bureau (fictional)"
BASE = {a["id"]: a for a in base.ACCOUNTS}


def contact(i):
    addr, phone = BASE[i]["creditor_contact"].split(" · ")
    return addr.upper(), phone


# Per-account fields in TransUnion-style labels. ">...<" marks adverse values.
TU = {
    4: dict(section="adverse", number="XXXX-3391", opened="08/14/2023", resp="Individual Account",
            acct_type="Revolving Account", loan_type="CREDIT CARD", balance="$0", updated="06/2025",
            pay_status=">Charged Off<", terms="Minimum $195 per month", high="$6,400", limit="$7,000",
            past_due="$0", closed="05/2025", remarks=">PURCHASED BY ANOTHER LENDER<"),
    7: dict(section="adverse", number="X X X X - 6 6 0 5", opened="03/04/2025", resp="Individual Account",
            acct_type="Installment Account", loan_type="UNSECURED", balance="$3,500", updated="10/2026",
            pay_status=">Account 120 Days Past Due Date<", terms="$160 per month, paid Monthly for 36 months",
            high="$5,000", past_due=">$640<", monthly="$160"),
    3: dict(section="adverse", number="XXXX-0573", opened="02/18/2023", resp="Individual Account",
            acct_type="Revolving Account", loan_type="CHARGE ACCOUNT", balance="$1,240", updated="10/2026",
            pay_status=">Collection/Charge-off<", terms="Minimum $40 per month", high="$1,480", limit="$1,500",
            past_due=">$1,240<", closed="12/2024", remarks=">UNPAID BALANCE CHARGED OFF<"),
    6: dict(section="adverse", number="XXXX-7142", opened="11/05/2023", resp="Joint Account",
            acct_type="Installment Account", loan_type="AUTOMOBILE", balance="$14,200", updated="10/2026",
            pay_status=">Account 60 Days Past Due Date<", terms="$406 per month, paid Monthly for 72 months",
            high="$21,800", past_due=">$812<", monthly="$406"),
    2: dict(section="satisfactory", number="XXXX-9014", opened="05/22/2018", resp="Individual Account",
            acct_type="Revolving Account", loan_type="CREDIT CARD", balance="$820", updated="10/2026",
            pay_status="Current; Paid or Paying as Agreed", terms="Minimum $35 per month", high="$2,140",
            limit="$5,000", monthly="$35"),
    8: dict(section="satisfactory", number="XXXX-4471", opened="04/12/2025", resp="Individual Account",
            acct_type="Revolving Account", loan_type="CREDIT CARD", balance="$310", updated="10/2026",
            pay_status="Current; Paid or Paying as Agreed", terms="Minimum $25 per month", high="$640",
            limit="$2,000", monthly="$25"),
    1: dict(section="satisfactory", number="XXXX-2280", opened="09/01/2016", resp="Individual Account",
            acct_type="Installment Account", loan_type="STUDENT LOAN", balance="$11,420", updated="10/2026",
            pay_status="Current; Paid or Paying as Agreed", terms="$312 per month, paid Monthly for 120 months",
            high="$28,500", monthly="$312"),
    5: dict(section="collections", number="XXXX-8820", placed="06/2025", resp="Individual Account",
            acct_type="Open Account", loan_type="COLLECTION AGENCY/ATTORNEY", balance="$6,912", updated="10/2026",
            pay_status=">Collection Account<", original_creditor="PACIFIC CREST CRD", original="$6,400",
            past_due=">$6,912<", remarks=">PLACED FOR COLLECTION<"),
}

NAMES = {i: BASE[i]["creditor"] for i in BASE}
ORDER = {s: sorted([i for i in TU if TU[i]["section"] == s], key=lambda i: NAMES[i])
         for s in ("adverse", "satisfactory", "collections")}

REGULAR_INQ = [  # hard inquiries stay on file for two years, so older ones have dropped off
    ("FRESNO COMMUNITY CREDIT UNION", "1450 TULARE ST, FRESNO, CA 93721", "04/10/2025", "(559) 555-0186"),
    ("QUICKFUND PERSONAL LOAN", "2200 MARKET PL STE 400, SAN JOSE, CA 95113", "03/02/2025", "(888) 555-0174"),
]
PROMO_INQ = [
    ("BRIGHTWATER CARD SERVICES", "PO BOX 5510, RENO, NV 89513", "09/14/2026", "(800) 555-0140"),
    ("LANTERN INSURANCE AGENCY", "77 CEDAR ST, MODESTO, CA 95354", "07/02/2026", "(209) 555-0172"),
]
REVIEW_INQ = [
    ("BAYLINE BANK VISA", "PO BOX 3301, SAN FRANCISCO, CA 94119", "08/19/2026", "(800) 555-0118"),
    ("GOLDEN STATE STUDENT LENDING", "PO BOX 900, SACRAMENTO, CA 95812", "07/07/2026", "(800) 555-0110"),
    ("BAYLINE BANK VISA", "PO BOX 3301, SAN FRANCISCO, CA 94119", "05/20/2026", "(800) 555-0118"),
]

CODE_MAP = {"CO": "C/O", "C": "COL", "--": ""}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PAGE_W, PAGE_H = letter
LEFT, RIGHT = 48, PAGE_W - 48
TOP, BOTTOM = PAGE_H - 44, 64
GRAY, LINE, MID = HexColor("#F1F3F5"), HexColor("#ADB5BD"), HexColor("#6C757D")
RED, TEAL = HexColor("#B02A37"), HexColor("#1F4E5F")


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(MID)
            self.drawString(LEFT, 36, "SYNTHETIC DATA for a hackathon demo. Fictional bureau, person and lenders. "
                                      "Layout modeled on a real consumer disclosure's structure.")
            self.drawRightString(RIGHT, 36, f"{self._pageNumber}/{n}")
            super().showPage()
        super().save()


class Writer:
    def __init__(self, path):
        self.c = NumberedCanvas(str(path), pagesize=letter)
        self.c.setTitle("Sample Credit Report (TU-style layout) - Synthetic Data")
        self.split = []
        self._header()

    def _header(self):
        c = self.c
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(LEFT, TOP, "SAMPLE CREDIT REPORT — SYNTHETIC DATA")
        c.setFillColor(black)
        c.setFont("Helvetica", 8)
        c.drawString(LEFT, TOP - 12, f"{BUREAU}  ·  Personal Credit Report for DANA M WHITFIELD")
        c.drawRightString(RIGHT, TOP - 12, "File Number: 448-201-7735   Date Created: 10/28/2026")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(LEFT, TOP - 18, RIGHT, TOP - 18)
        self.y = TOP - 34

    def new_page(self):
        self.c.showPage()
        self._header()

    def room(self, h):
        return self.y - h >= BOTTOM

    def need(self, h):
        if not self.room(h):
            self.new_page()

    def h1(self, title, note=None):
        if self.y < TOP - 40:
            self.y -= 10
        self.need(80)
        c = self.c
        c.setFillColor(TEAL)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(LEFT, self.y, title)
        c.setStrokeColor(TEAL)
        c.setLineWidth(1.2)
        c.line(LEFT, self.y - 5, RIGHT, self.y - 5)
        self.y -= 18
        if note:
            for line in note:
                self.text(line, size=7.5, color=MID)
            self.y -= 4
        c.setFillColor(black)

    def text(self, s, size=8.5, bold=False, indent=0, color=black):
        self.need(size + 4)
        self.c.setFillColor(color)
        self.c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.c.drawString(LEFT + indent, self.y, s)
        self.c.setFillColor(black)
        self.y -= size + 4

    def field(self, x, y, label, value, label_w=96):
        self.c.setFont("Helvetica", 7.5)
        self.c.setFillColor(MID)
        self.c.drawString(x, y, label)
        self.c.setFont("Helvetica", 8.5)
        self.c.setFillColor(RED if value.startswith(">") else black)
        self.c.drawString(x + label_w, y, value)
        self.c.setFillColor(black)

    def account(self, i):
        a, b = TU[i], BASE[i]
        addr, phone = contact(i)
        rows = []

        def title(y):
            self.c.setFillColor(GRAY)
            self.c.rect(LEFT, y - 5, RIGHT - LEFT, 17, stroke=0, fill=1)
            self.c.setFillColor(black)
            self.c.setFont("Helvetica-Bold", 10)
            self.c.drawString(LEFT + 6, y, NAMES[i])
            self.c.setFont("Helvetica", 8.5)
            self.c.drawRightString(RIGHT - 6, y, a["number"])
        rows.append((22, title))

        left = [("Address", addr), ("Phone", phone)]
        if a.get("monthly"):
            left.append(("Monthly Payment", a["monthly"]))
        if a.get("opened"):
            left.append(("Date Opened", a["opened"]))
        if a.get("placed"):
            left.append(("Placed for Collection", a["placed"]))
        if a.get("original_creditor"):
            left.append(("Original Creditor", a["original_creditor"]))
        left += [("Responsibility", a["resp"]), ("Account Type", a["acct_type"]), ("Loan Type", a["loan_type"])]

        right = [("Balance", a["balance"]), ("Date Updated", a["updated"])]
        if a.get("original"):
            right.append(("Original Balance", a["original"]))
        if a.get("high"):
            right.append(("High Balance", a["high"]))
        if a.get("limit"):
            right.append(("Credit Limit", a["limit"]))
        if a.get("past_due"):
            right.append(("Past Due", a["past_due"]))
        if a.get("closed"):
            right.append(("Date Closed", a["closed"]))

        col2 = LEFT + (RIGHT - LEFT) / 2 + 66  # clears the longest creditor address
        for k in range(max(len(left), len(right))):
            l = left[k] if k < len(left) else None
            r = right[k] if k < len(right) else None

            def row(y, l=l, r=r):
                if l:
                    self.field(LEFT + 6, y, *l)
                if r:
                    self.field(col2, y, *r, label_w=72)
            rows.append((12, row))

        for label in ("pay_status", "terms", "remarks"):
            if a.get(label):
                name = {"pay_status": "Pay Status", "terms": "Terms", "remarks": "Remarks"}[label]
                rows.append((12, lambda y, n=name, v=a[label]: self.field(LEFT + 6, y, n, v)))

        # Payment history in blocks of six months, Rating row only.
        codes = [CODE_MAP.get(c, c) for c in b["history"]]
        if any(codes):
            rows.append((16, lambda y: self.field(LEFT + 6, y, "Payment History", "")))
            for blk in range(4):
                months = base.WINDOW[blk * 6:(blk + 1) * 6]
                vals = codes[blk * 6:(blk + 1) * 6]
                if not any(vals):  # months the account wasn't reported, like a real report
                    continue

                def hist(y, months=months, vals=vals):
                    x0, w = LEFT + 70, (RIGHT - LEFT - 76) / 6
                    self.c.setFont("Helvetica", 7)
                    self.c.setFillColor(MID)
                    self.c.drawString(LEFT + 6, y - 1, "Rating")
                    for j, ((yy, mm), v) in enumerate(zip(months, vals)):
                        x = x0 + j * w
                        self.c.setFont("Helvetica", 7)
                        self.c.setFillColor(MID)
                        self.c.drawString(x, y + 8, f"{MONTHS[mm - 1]} {yy}")
                        self.c.setFont("Helvetica-Bold", 8)
                        self.c.setFillColor(RED if v not in ("OK", "") else black)
                        self.c.drawString(x, y - 1, v)
                    self.c.setFillColor(black)
                rows.append((22, hist))

        if not self.room(sum(h for h, _ in rows[:4])):
            self.new_page()
        split = False
        for h, draw in rows:
            if not self.room(h):
                self.new_page()
                split = True
                self.text(f"{NAMES[i]}  (continued)", size=8, bold=True, color=MID)
            draw(self.y)
            self.y -= h
        if split:
            self.split.append(i)
        self.y -= 12

    def inquiries(self, title, items, note):
        self.h1(title, note)
        for name, loc, date, phone in items:
            self.need(30)
            self.text(name, bold=True, size=9)
            self.field(LEFT + 6, self.y, "Location", loc)
            self.y -= 12
            self.field(LEFT + 6, self.y, "Requested On", date)
            self.field(LEFT + 260, self.y, "Phone", phone, label_w=40)
            self.y -= 16

    def save(self):
        self.c.showPage()
        self.c.save()


def build_pdf(path):
    w = Writer(path)

    w.h1("Personal Information")
    for label, value in [("Credit Report Date", "10/28/2026"), ("Social Security Number", "XXX-XX-4417"),
                         ("Date of Birth", "XX/XX/1991"), ("Name", "DANA M WHITFIELD"),
                         ("Also Known As", "WHITFIELD, DANA;  DANA WHITFIELD")]:
        w.field(LEFT, w.y, label, value, label_w=110)
        w.y -= 13
    w.y -= 4
    w.text("Addresses", bold=True, size=9)
    for kind, addr, rep in [("Current Address", "610 HARMON AVE, FRESNO, CA 93721", "10/2026"),
                            ("Other Address", "PO BOX 2291, SACRAMENTO, CA 95812", "03/2025"),
                            ("Other Address", "1427 ALDER CRK RD, SACRAMENTO, CA 95819", "08/2023"),
                            ("Other Address", "1427 ALDER CREEK ROAD, SACRAMENTO, CA 95819", "04/2022"),
                            ("Other Address", "88 LINDEN ST APT 3, OAKLAND, CA 94607", "01/2019")]:
        w.field(LEFT + 6, w.y, kind, addr, label_w=104)
        w.field(LEFT + 360, w.y, "Date Reported", rep, label_w=62)
        w.y -= 13
    w.y -= 4
    w.text("Phone Numbers", bold=True, size=9)
    w.text("(559) 555-0148     (916) 555-0193", indent=6)
    w.y -= 2
    w.text("Employers", bold=True, size=9)
    w.field(LEFT + 6, w.y, "Name", "VALLEY HOME HEALTH SVCS", label_w=104)
    w.field(LEFT + 360, w.y, "Date Verified", "09/2025", label_w=62)
    w.y -= 20

    key = ["Payment/Remarks Key: OK = current or paid as agreed · 30 / 60 / 90 / 120 = days past due · "
           "COL = collection · C/O = charge-off",
           "VS = voluntary surrender · RPO = repossession · FC = foreclosure · X = unknown · N/R = not reported.  "
           "Adverse information is marked >like this<."]
    w.h1("Accounts with Adverse Information", key)
    for i in ORDER["adverse"]:
        w.account(i)
    w.h1("Satisfactory Accounts")
    for i in ORDER["satisfactory"]:
        w.account(i)
    w.h1("Collections", ["Accounts placed with a collection agency or sold to a debt buyer."])
    for i in ORDER["collections"]:
        w.account(i)

    w.inquiries("Regular Inquiries", REGULAR_INQ,
                ["Companies that requested your credit report when you applied for credit. Shown for two years."])
    w.inquiries("Promotional Inquiries", PROMO_INQ,
                ["Pre-approved offers. Not seen by lenders and do not affect your credit."])
    w.inquiries("Account Review Inquiries", REVIEW_INQ,
                ["Reviews by companies you already have accounts with. Not seen by lenders."])
    w.h1("Public Records and Consumer Statement")
    w.text("Public Records: none reported.     Consumer Statement: none.")
    w.y -= 6
    w.text("End of report.", color=MID)
    w.save()
    return w.split


def iso(mmddyyyy):
    m, d, y = mmddyyyy.split("/")
    return f"{y}-{m}-{d}"


EXPECTED = {  # what a good predictor should say on THIS layout, and the evidence that's actually here
    1: ("likely_hers", ["likely_hers"], ["Opened 09/2016, years before the relationship"]),
    2: ("likely_hers", ["likely_hers"], ["Opened 05/2018, before the relationship"]),
    3: ("likely_coerced", ["likely_coerced"], ["She names the TechMart card in her story"]),
    4: ("likely_coerced", ["likely_coerced", "needs_review"],
        ["Her story: collectors calling about 'a credit card ... I never opened'",
         "Charged off and sold; the matching collection is Summit Recovery Group",
         "Opened during the relationship"]),
    5: ("likely_coerced", ["likely_coerced", "needs_review"],
        ["Same debt as Pacific Crest Card (Original Creditor PACIFIC CREST CRD, Original Balance $6,400 = "
         "Pacific Crest High Balance)",
         "A collector on a credit card she says she never opened"]),
    6: ("likely_coerced", ["likely_coerced"], ["She names the car loan in her story"]),
    7: ("likely_coerced", ["likely_coerced"],
        ["Opened 03/04/2025, after she moved out (01/2025)",
         "Unknown PO BOX 2291, SACRAMENTO first reported 03/2025, the month this loan opened",
         "Regular inquiry 03/02/2025 from QuickFund",
         "Her story: a loan she never opened"]),
    8: ("likely_hers", ["likely_hers", "needs_review"],
        ["Opened 04/2025 in Fresno, the city she moved to in 02/2025", "Paid as agreed"]),
}


def build_ground_truth(split):
    gt = json.loads((DATA / "ground_truth.json").read_text())
    accounts = []
    for a in sorted(base.ACCOUNTS, key=lambda a: a["id"]):
        i, t = a["id"], TU[a["id"]]
        exp, ok, ev = EXPECTED[i]
        lab = base.LABELS[i]
        entry = {
            "id": i,
            "creditor": a["creditor"],
            "section": t["section"],
            "account_number_as_printed": t["number"],
            "account_last4": re.sub(r"\D", "", t["number"])[-4:],
            "loan_type": t["loan_type"],
            "secured": a["secured"],
            "secured_how_to_tell": "Loan Type AUTOMOBILE" if a["secured"] else None,
            "date_opened": iso(t["opened"]) if t.get("opened") else None,
            "date_placed_for_collection": t.get("placed"),
            "balance": int(t["balance"].strip("$").replace(",", "")),
            "label": lab["label"],
            "expected_prediction": exp,
            "acceptable_predictions": ok,
            "evidence_on_this_layout": ev,
            "split_across_page_break": i in split,
        }
        for k in ("mechanism", "eligible_for_notice", "exclusion_reason", "linked_account_id",
                  "current_holder_account_id", "notice_recipient", "notes"):
            if k in lab:
                entry[k] = lab[k]
        if t.get("original_creditor"):
            entry["original_creditor"] = t["original_creditor"]
        accounts.append(entry)
    return {
        "_note": ("Synthetic data. Same people and debts as ground_truth.json, rendered in a TU-style layout. "
                  "Match accounts by account_last4. Accounts here show the creditor's address/phone, not the "
                  "consumer's, so per-account phone/address checks don't apply."),
        "layout": "TransUnion-style structure, fictional bureau",
        "report_file": "credit_report_tu_style.pdf",
        "report_date": gt["report_date"],
        "law_cutoff_date": gt["law_cutoff_date"],
        "accounts": accounts,
        "expected_letters": gt["expected_letters"],
        "expected_exclusions": gt["expected_exclusions"],
        "expected_legit": gt["expected_legit"],
    }


def main():
    split = build_pdf(DATA / "credit_report_tu_style.pdf")
    (DATA / "ground_truth_tu_style.json").write_text(json.dumps(build_ground_truth(split), indent=2) + "\n")
    print(f"Wrote {DATA}/credit_report_tu_style.pdf and ground_truth_tu_style.json")
    print(f"Accounts split across a page break: {split or 'none'}")


if __name__ == "__main__":
    main()
