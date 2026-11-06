"""NotMyDebt core: one Claude call to read the report, plain code to apply the law, fixed legal text.

Claude guesses (with evidence). Code decides coverage. Claude never writes legal text.
"""

import base64
import json
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# ---------------------------------------------------------------------------
# Fixed text. Verbatim from CLAUDE.md (checked against Civ. Code §§ 1798.97.1–.6).
# ---------------------------------------------------------------------------

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

NEEDS_INFO = ("We couldn't find when this debt started. The law covers debts incurred on or after "
              "July 1, 2023. Check the original account's open date with your advocate.")

LAW_URL = ("https://leginfo.legislature.ca.gov/faces/codes_displayText.xhtml"
           "?lawCode=CIV&division=3.&title=1.81.35.&part=4.&chapter=&article=")

# ---------------------------------------------------------------------------
# The one Claude call
# ---------------------------------------------------------------------------

_S = {"type": ["string", "null"]}

RECORD_ACCOUNTS = {
    "name": "record_accounts",
    "description": "Record every account found on the credit report, with a prediction and evidence for each.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["accounts"],
        "properties": {
            "accounts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "creditor": {"type": "string", "description": "As printed."},
                        "account_number": {"type": "string", "description": "As printed."},
                        "last4": {"type": "string", "description": "Last 4 digits only. 'X X X X - 6 6 0 5' -> '6605'."},
                        "section": {"type": "string", "description": "The report heading the account sits under."},
                        "account_type": _S,
                        "loan_type": _S,
                        "collateral": _S,
                        "date_opened": {"type": ["string", "null"],
                                        "description": "YYYY-MM-DD, or YYYY-MM if no day. Null for collections with no open date."},
                        "balance": {"type": ["integer", "null"], "description": "Current balance, whole dollars."},
                        "status": _S,
                        "is_collection": {"type": "boolean"},
                        "original_creditor": _S,
                        "creditor_address": _S,
                        "creditor_phone": _S,
                        "consumer_address_on_account": _S,
                        "consumer_phone_on_account": _S,
                        "linked_last4": _S,
                        "prediction": {"type": "string", "enum": ["likely_coerced", "needs_review", "likely_hers"]},
                        "evidence": {"type": "array", "items": {"type": "string"},
                                     "description": "1-3 short plain sentences, each quoting a value from the report or her intake."},
                    },
                    "required": [
                        "creditor", "account_number", "last4", "section", "account_type", "loan_type",
                        "collateral", "date_opened", "balance", "status", "is_collection", "original_creditor",
                        "creditor_address", "creditor_phone", "consumer_address_on_account",
                        "consumer_phone_on_account", "linked_last4", "prediction", "evidence",
                    ],
                },
            }
        },
    },
}

PROMPT = """The PDF above is a credit report for a survivor of domestic violence. Her advocate is helping her find \
debts she didn't agree to. Her intake answers are at the end.

Call the record_accounts tool exactly once, with every account on the report.

Extraction:
- Extract every account, including collections. If an account continues across a page break, merge it into one.
- Copy values exactly as printed. Use null when a value is absent. Never guess.
- last4: the last 4 digits of the account number only. Numbers can be spaced, e.g. "X X X X - 6 6 0 5" -> "6605".
- section: the report heading the account sits under (e.g. "Collections", "Satisfactory Accounts").
- date_opened: YYYY-MM-DD, or YYYY-MM if the report gives no day. Null for collections with no open date \
(a date placed for collection is not an open date).
- balance: the current balance in whole dollars.
- Careful: on TransUnion-style reports, the address and phone printed under each account are the CREDITOR's \
contact info, not hers. Put them in creditor_address / creditor_phone. Fill consumer_address_on_account / \
consumer_phone_on_account only when the report ties HER own address or phone to the account (e.g. a field \
labeled "Address reported").
- Link a collection to its original account when they're the same debt: the original creditor name matches \
(it may be abbreviated), or the collection's original balance equals the original account's high balance. \
Set linked_last4 on both accounts. Otherwise linked_last4 is null.

Prediction (compare each account with her intake and with the report's personal information: addresses, \
phones, and when each was first reported):
- likely_coerced: at least one strong sign:
  - a phone or address tied to the account that isn't hers
  - an unknown address or phone in her personal info that first appears around when the account opened
  - opened after she moved out and not consistent with her new life
  - she names or describes it in her story ("a credit card I never opened" matches a credit card, or a \
collection on one)
- likely_hers: opened before the relationship, or consistent with her current life (her own address or phone, \
local to where she lives now, paid as agreed).
- needs_review: only weak or conflicting signs, e.g. opened during the relationship and nothing else.
- A collection and the original account it's linked to are the same debt, so give them the same prediction.
- evidence: 1-3 short plain sentences, each quoting a value from the report or her intake.
- Do not judge legal coverage. Code does that.

Her intake (JSON):
"""


def _digits4(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[-4:] if len(digits) >= 4 else None


def analyze(pdf_bytes, intake):
    """Send the PDF + intake to Claude. Returns the list of account dicts."""
    client = anthropic.Anthropic()
    b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=8000,
        # Forced tool_choice returns a 400 on this model, so: auto + strict schema + a prompt that names the tool.
        tools=[RECORD_ACCOUNTS],
        tool_choice={"type": "auto", "disable_parallel_tool_use": True},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                {"type": "text", "text": PROMPT + json.dumps(intake, indent=2)},
            ],
        }],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (hit max_tokens). Try again.")
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to read this report.")
    tool_use = next((b for b in response.content
                     if b.type == "tool_use" and b.name == "record_accounts"), None)
    if tool_use is None:
        raise RuntimeError("Claude didn't return the account list. Try again.")
    accounts = tool_use.input["accounts"]
    for a in accounts:  # normalize digits so matching never depends on spacing
        a["last4"] = _digits4(a.get("last4")) or _digits4(a.get("account_number"))
        a["linked_last4"] = _digits4(a.get("linked_last4"))
    return accounts
