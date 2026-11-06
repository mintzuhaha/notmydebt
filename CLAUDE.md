# NotMyDebt: MVP scope (working name, rename freely)

Hackathon build with about one hour left. Aim to finish code by 11:40. Demo video + GitHub link are due by 12:45.

**What it does:** An advocate uploads a survivor's credit report PDF. Claude reads it live and guesses which
accounts look coerced, quoting the evidence. Plain code checks whether California's coerced debt law
(Civ. Code §§ 1798.97.1–.6, SB 975) would cover each one. The survivor checks the debts she didn't agree to,
clicks Submit, and gets next steps for each.

**Three layers:** Claude guesses, with evidence → code applies the law → she decides.

## Non-negotiables

1. Synthetic data only (`data/`).
2. Claude never writes legal text and never decides coverage. All legal wording is in the constants below, copied verbatim.
3. Nothing stored: process uploads in memory. Don't write uploads or responses to disk. The one exception is
   `fixtures/`, which holds responses for the two synthetic sample PDFs only.
4. The Quick exit button is always visible. The disclaimer appears on the results.
5. Never commit `.env`.

## Stack

- Python, Streamlit (`app.py`), `anthropic` SDK, python-dotenv
- Model from env `CLAUDE_MODEL`, default `claude-sonnet-5-5`
- The PDF goes to Claude as a base64 document block, PDF first, then the text instruction:
  `{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}`
- Structured output: the `record_accounts` tool with `strict: true`, `tool_choice={"type": "auto"}`, and a prompt
  that names the tool. Forced `tool_choice` (`{"type": "tool"}`) returns a 400 on `claude-sonnet-5-5`. Raise if no
  tool call comes back. Use `max_tokens=8000`. If `stop_reason == "max_tokens"`, raise a clear error instead of parsing half a response.

## Files

```
app.py      Streamlit UI only
core.py     analyze() Claude call, is_secured(), coverage(), fixed text
eval.py     scores core.py against both answer keys
data/       ALREADY HERE, all synthetic:
            credit_report.pdf            (fictional "Northfield" layout; per-account consumer address/phone)
            credit_report_tu_style.pdf   (layout modeled on TransUnion's structure; fictional bureau)
            dana_intake.json             (her answers: addresses + dates, relationship dates, phone, story)
            ground_truth.json            (answer key for credit_report.pdf)
            ground_truth_tu_style.json   (answer key for credit_report_tu_style.pdf)
scripts/    ALREADY HERE: generators for data/
fixtures/   saved good responses for the two sample PDFs (fallback if the API fails)
```

## core.analyze(pdf_bytes, intake): the one Claude call

Input: the PDF plus `data/dana_intake.json`. Tool `record_accounts` returns `{"accounts": [...]}`, where each account has:

| Field | Notes |
|---|---|
| `creditor` | as printed |
| `account_number` | as printed |
| `last4` | last 4 digits only. Numbers can be spaced, e.g. `X X X X - 6 6 0 5` → `6605` |
| `section` | the report heading it sits under (e.g. "Collections", "Satisfactory Accounts") |
| `account_type`, `loan_type`, `collateral` | as printed, null if absent |
| `date_opened` | `YYYY-MM-DD`, or `YYYY-MM` if no day. Null for collections with no open date |
| `balance` | whole dollars |
| `status` | pay status as printed |
| `is_collection` | bool |
| `original_creditor` | for collections |
| `creditor_address`, `creditor_phone` | the creditor's or collector's own contact info |
| `consumer_address_on_account`, `consumer_phone_on_account` | only when the report ties HER address/phone to this account |
| `linked_last4` | the other account if this is the same debt (collection ↔ original), else null |
| `prediction` | `likely_coerced` / `needs_review` / `likely_hers` |
| `evidence` | 1–3 short plain sentences, each quoting a value from the report or her intake |

Instructions for Claude (put these in the prompt):
- Extract every account, including collections. If an account continues across a page break, merge it into one.
- Copy values exactly. Use null when absent. Never guess.
- **Careful:** on TransUnion-style reports, the address and phone under each account are the CREDITOR's contact
  info, not hers. Put them in `creditor_address` / `creditor_phone`. Fill the `consumer_*` fields only when the report
  ties her own address or phone to the account (e.g. a field labeled "Address reported").
- Link a collection to its original account when they're the same debt: the original creditor name matches,
  or the collection's original balance equals the original account's high balance. Set `linked_last4` on both.
- `likely_coerced`: at least one strong sign:
  - a phone or address tied to the account that isn't hers
  - an unknown address or phone in her personal info that first appears around when the account opened
  - opened after she moved out and not consistent with her new life
  - she names or describes it in her story ("a credit card I never opened" matches a credit card, or a collection on one)
- `likely_hers`: opened before the relationship, or consistent with her current life (her own address or phone,
  local to where she lives now, paid as agreed).
- `needs_review`: only weak or conflicting signs, e.g. opened during the relationship and nothing else.
- Do not judge legal coverage. Code does that.

Caching: in `app.py`, wrap the call in `@st.cache_data`. Streamlit reruns the whole script on every click, so
without the cache every click calls Claude again. Fallback: if the call fails and the PDF's sha256 matches a sample,
load `fixtures/<sample>.json`.

## Coverage rules: plain code in core.py

- Group linked accounts (collection + original) into one debt.
- `is_secured(account)`: True if collateral is listed, or `account_type`/`loan_type` contains AUTO, MORTGAGE,
  HOME EQUITY, or SECURED. **Check for UNSECURED first.** "UNSECURED" contains "SECURED", and QuickFund is unsecured.
- The debt's start date is the ORIGINAL account's `date_opened`. A collection's placement date doesn't count.
  If there's no original account date, return `needs_info`.
- Per debt, in this order:
  1. any account in the group is secured → `not_covered_secured`
  2. start date before 2023-07-01 → `not_covered_date` (treat `YYYY-MM` as the 1st of that month)
  3. otherwise `covered`. Send to the collection account if there is one (it holds the debt now), else the original creditor.
- The "Covered if coerced?" column runs this same function before she confirms anything.

## Fixed text: copy verbatim into core.py

```python
DISCLAIMER = ("Information to review with a domestic violence advocate or legal aid attorney. "
              "Not legal advice.")

ASSUMPTION = ("Assumes each debt was for personal, family, or household use, and that she is a survivor "
              "of domestic violence (Civ. Code § 1798.97.1(d)).")

COVERED_STEPS = [
    "Get proof (one of these): a police report, an FTC report, a court order, or a signed letter from a "
    "qualified professional, like a domestic violence counselor, on their organization's letterhead.",
    "Write a sworn statement. It needs: a copy of your state ID (and any other ID that supports your claim); "
    "a statement that you didn't willingly authorize this debt, with the facts; the account number; copies of "
    "any letters you've sent disputing it; the name and contact information of the person who did this, or a "
    "sworn statement that naming them is likely to lead to abuse; how to contact you (a phone number, or "
    "writing only to a mailing address); and this line: \"I declare under penalty of perjury that the "
    "representations made herein are true, correct, and contain no material omissions of fact.\"",
    "Send both to {recipient}, {address}. Certified mail is recommended so you have proof it arrived.",
    "What happens next: once they have both, they must stop collecting until their review is done "
    "(§ 1798.97.2(b)). Within 10 business days, if they reported this debt to the credit bureaus, they must "
    "tell the bureaus the account is disputed (§ 1798.97.2(d)(1)). Within 10 business days of finishing their "
    "review, they must send you a written decision (§ 1798.97.2(d)(3)).",
]

NOT_COVERED_SECURED = ("Not covered: this law doesn't apply to secured debts (Civ. Code § 1798.97.4(a)). "
                       "What you can do: talk to a legal aid attorney about other options.")

NOT_COVERED_DATE = ("Not covered: this law only applies to debts incurred on or after July 1, 2023 "
                    "(Civ. Code § 1798.97.5(a)). What you can do: if a creditor or collector sues you over "
                    "this debt, you can file a cross-complaint in that lawsuit saying it's coerced debt, as "
                    "long as there's no final judgment yet (§ 1798.97.5(b)). Talk to a legal aid attorney.")

LAW_URL = ("https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml"
           "?lawCode=CIV&division=3.&title=1.81.35.&part=4.&chapter=&article=")

NEEDS_INFO = ("We couldn't find when this debt started. The law covers debts incurred on or after "
              "July 1, 2023. Check the original account's open date with your advocate.")
```

## UI (app.py)

1. **Header:** "NotMyDebt", caption "Synthetic data · Draft for advocate review", and Quick exit top right.
   Quick exit must open in the SAME tab, because `st.link_button` opens a new tab and leaves the app showing. Use
   `st.markdown('<a href="https://www.google.com/search?q=weather" target="_self">Quick exit</a>', unsafe_allow_html=True)`
   styled as a red button.
2. **"Dana's info" expander,** read-only: addresses with dates, relationship dates, phone, story.
3. **Upload:** `st.file_uploader` (PDF), plus a "Use a sample report" selectbox. A "Read report" button runs the
   analysis under a spinner that says "Reading the report…". Store results in `st.session_state`.
4. **Accounts,** inside `st.form` so checking boxes doesn't rerun the app. One row per debt, with linked pairs together:
   "Pacific Crest Card → now held by Summit Recovery Group". Columns:
   - ☐ She didn't agree to this (nothing pre-checked)
   - Account
   - Opened
   - Balance
   - Likely coerced? (a chip, with the evidence lines underneath)
   - Covered if coerced? (✅ Yes, send to X / ❌ Secured debt / ❌ Before July 1, 2023 / ? Start date unknown)

   Then a Submit button.
5. **Results:**
   - a summary box: "2 debts you can stop collection on · $10,412 · 2 debts this law doesn't cover"
   - one bordered card per checked debt, with its fixed text and the recipient's name and address in bold
   - a collapsed "Accounts that look like yours" list
   - `ASSUMPTION` and `DISCLAIMER`

## eval.py

Run it for each sample (`credit_report.pdf` with `ground_truth.json`, `credit_report_tu_style.pdf` with
`ground_truth_tu_style.json`). Match accounts by last 4 digits and print PASS/FAIL for each check:
- 8/8 accounts found; balance and date_opened match (compare to the month)
- `is_secured()` is true only for Valley Auto (7142)
- Prediction:
  - TU-style key: the prediction is in `acceptable_predictions`
  - original key: label coerced ⇒ `likely_coerced`, legit ⇒ `likely_hers`
  - Fresno CU (4471) is never `likely_coerced`
- Link: 3391 ↔ 8820
- Coverage, after confirming the truly coerced accounts:
  - covered: 8820 (via 3391) and 6605
  - not covered: 0573 (date) and 7142 (secured)

Print a total. When everything passes, save the response to `fixtures/`.

## Build order

Stop and test after each step. Commit and push after each step that works.

1. `core.analyze` + eval extraction/prediction checks, run on both samples
2. `is_secured` + `coverage` + eval coverage checks
3. `app.py`
4. Save fixtures, do a full click-through, finish the README, push, and make the repo public

Do not build: login, a database, letter or statement drafting, other states, multiple bureaus, PDF export.

## README

Fill in the eval scoreboard. Keep the existing sections.
