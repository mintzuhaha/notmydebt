"""NotMyDebt: Streamlit UI. Claude guesses, code applies the law, you decide."""

import hashlib
import html
import json
import pathlib

import streamlit as st

import core

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"
INTAKE = json.loads((DATA / "dana_intake.json").read_text())
SAMPLES = {
    "Northfield-style report (credit_report.pdf)": "credit_report.pdf",
    "TransUnion-style report (credit_report_tu_style.pdf)": "credit_report_tu_style.pdf",
}
SAMPLE_FIXTURES = {
    hashlib.sha256((DATA / pdf).read_bytes()).hexdigest(): FIXTURES / (pdf.removesuffix(".pdf") + ".json")
    for pdf in SAMPLES.values()
}
RANK = {"likely_coerced": 0, "needs_review": 1, "likely_hers": 2}
STATUS_RANK = {"covered": 0, "needs_info": 1, "not_covered_secured": 2, "not_covered_date": 3}
PILL = {"likely_coerced": ("Likely coerced", "red"),
        "needs_review": ("Needs review", "amber"),
        "likely_hers": ("Likely yours", "gray")}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

st.set_page_config(page_title="NotMyDebt", page_icon="🛡️", layout="wide")

CSS = """
<style>
header[data-testid="stHeader"] { display: none; }
.block-container { max-width: 1100px; padding-top: 2.2rem; padding-bottom: 3rem; }
[class*="st-key-card-"] { background: #fff; border-radius: 14px; }
.brand { font-size: 1.9rem; font-weight: 700; margin-right: 0.8rem; }
.tagline { color: #57606a; }
.sec { font-size: 0.9rem; font-weight: 700; letter-spacing: 0.03em; color: #424a53; text-transform: uppercase; }
.th { font-size: 0.85rem; font-weight: 600; color: #424a53; }
.muted { color: #6b7280; }
.cov-yes { color: #2e7d32; }
.cov-no { color: #b45309; }
.pill { display: inline-block; font-size: 0.82rem; padding: 0.05rem 0.55rem; border-radius: 6px; margin-bottom: 0.25rem; }
.pill.red { background: #fdecec; color: #c62828; }
.pill.amber { background: #fff1dc; color: #9a5b00; }
.pill.gray { background: #eeeeee; color: #57606a; }
.file-chip { border: 1.5px dashed #c8ccd2; border-radius: 10px; padding: 0.55rem 0.9rem; }
.plan { border: 1.5px solid; border-radius: 10px; padding: 0.75rem 1rem; margin: 0.15rem 0 0.6rem; background: #fff; }
.plan.ok { border-color: #8bc34a; }
.plan.no { border-color: #f0a830; }
.tag { font-size: 0.82rem; padding: 0.1rem 0.5rem; border-radius: 6px; margin-right: 0.45rem; }
.tag.ok { background: #e6f2d9; color: #33691e; }
.tag.no { background: #fdebd3; color: #9a5b00; }
.plan ol { margin: 0.4rem 0 0 1.2rem; padding: 0; }
.plan li { margin-bottom: 0.2rem; }
hr { margin: 0.3rem 0 !important; }
a.quick-exit {
  position: fixed; top: 3.3rem; right: max(1rem, calc((100vw - 1100px) / 2 + 1rem)); z-index: 1000000;
  background: #d93030; color: #fff !important; text-decoration: none !important;
  padding: 0.55rem 1.2rem; border-radius: 0.6rem; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}
a.quick-exit:hover { background: #a61f1f; }
</style>
"""


def h(text):
    """Escape for HTML, and keep $ from being read as LaTeX by Streamlit's markdown."""
    return html.escape(str(text)).replace("$", "&#36;")


def money(n):
    return f"&#36;{n:,}"


def mm_yyyy(date):
    return f"{date[5:7]}/{date[:4]}" if date and len(date) >= 7 else "—"


def month_year(ym):
    return f"{MONTHS[int(ym[5:7]) - 1]} {ym[:4]}"


def short(account):
    return account.get("short_name") or account["creditor"].title()


def debt_prediction(debt):
    return min((a["prediction"] for a in debt["accounts"]), key=lambda p: RANK[p])


def debt_summary(debt):
    return next((a.get("summary") for a in debt["accounts"] if a.get("summary")), "")


def debt_evidence(debt):
    lines = []
    for a in debt["accounts"]:
        for line in a.get("evidence") or []:
            if line not in lines:
                lines.append(line)
    return lines


def plan_title(debt):
    if debt["original"] and debt["collection"]:
        return debt["collection"]["creditor"].title()
    return short(core.holder(debt))


def dana_line():
    places = []
    for a in INTAKE["address_history"]:
        city = a["address"].split(",")[-2].strip()
        places.append(f"{city} {month_year(a['from'])}–{month_year(a['to']) if a['to'] else 'now'}")
    return "Your info: " + " · ".join(places) + f" · phone {INTAKE['client']['phone']}"


def covered_cell(debt, cov):
    if debt_prediction(debt) == "likely_hers":
        return '<span class="muted">—</span>'
    if cov["status"] == "covered":
        if debt["original"] and debt["collection"]:
            return f'<span class="cov-yes">✅ Yes, send to {h(short(debt["collection"]))}</span>'
        return '<span class="cov-yes">✅ Yes</span>'
    return {"not_covered_secured": '<span class="cov-no">❌ No, secured debt</span>',
            "not_covered_date": '<span class="cov-no">❌ No, before July 1, 2023</span>',
            "needs_info": '<span class="muted">? Start date unknown</span>'}[cov["status"]]


def plan_card(debt, cov, full_steps):
    """One result card. All legal text comes verbatim from core's constants."""
    head = f"<b>{h(plan_title(debt))} · {money(core.debt_balance(debt))}</b>"
    recipient = f"<b>{h(cov['recipient'].title())}, {h(cov['address'])}</b>"
    if cov["status"] == "covered":
        origin = ""
        if debt["original"] and debt["collection"]:
            origin = (f'<div class="muted">Originally {h(short(debt["original"]))}, '
                      f'sold to {h(short(debt["collection"]))}</div>')
        if not full_steps:
            return (f'<div class="plan ok"><span class="tag ok">Covered</span>{head}'
                    f'<span class="muted"> · same 4 steps · send to </span>{recipient}{origin}</div>')
        steps = [html.escape(s).format(recipient=f"<b>{h(cov['recipient'].title())}</b>",
                                       address=f"<b>{h(cov['address'])}</b>") for s in core.COVERED_STEPS]
        items = "".join(f"<li>{s}</li>" for s in steps)
        return (f'<div class="plan ok"><span class="tag ok">Covered</span>{head}{origin}'
                f'<div style="margin-top:0.35rem">Send to: {recipient}</div><ol>{items}</ol></div>')
    tag = "Start date unknown" if cov["status"] == "needs_info" else "Not covered"
    text = core.next_steps(cov)[0]
    return f'<div class="plan no"><span class="tag no">{tag}</span>{head}<div>{h(text)}</div></div>'


# Cache key includes the prompt + schema, so editing them forces a fresh Claude call.
PROMPT_VERSION = hashlib.sha256((core.PROMPT + json.dumps(core.RECORD_ACCOUNTS, sort_keys=True)).encode()).hexdigest()


@st.cache_data(show_spinner=False)
def run_analysis(pdf_bytes, prompt_version):
    """One Claude call per distinct PDF (cached in memory). Falls back to a saved result for the samples."""
    try:
        return core.analyze(pdf_bytes, INTAKE), None
    except Exception:
        fixture = SAMPLE_FIXTURES.get(hashlib.sha256(pdf_bytes).hexdigest())
        if fixture is None:
            raise
        return json.loads(fixture.read_text()), "Couldn't reach Claude, so this shows a saved result for this sample report."


# --- Header + Quick exit (fixed, always visible) -------------------------------

st.markdown(CSS + '<a class="quick-exit" href="https://www.google.com/search?q=weather" target="_self">Quick exit</a>'
            '<div><span class="brand">NotMyDebt</span>'
            '<span class="tagline">Synthetic data · Draft for advocate review</span></div>',
            unsafe_allow_html=True)

# --- 1 · Upload -----------------------------------------------------------------

with st.container(border=True, key="card-upload"):
    st.markdown('<div class="sec">1 · Upload</div>', unsafe_allow_html=True)
    with st.expander(dana_line()):
        client = INTAKE["client"]
        st.markdown(f"**Phone:** {client['phone']}  \n**Mailing address:** {client['mailing_address']}  \n"
                    f"**Contact preference:** {client['contact_preference']}")
        st.table([{"Address": a["address"], "From": a["from"], "To": a["to"] or "now", "Note": a.get("note", "")}
                  for a in INTAKE["address_history"]])
        rel = INTAKE["relationship"]
        st.markdown(f"**Relationship:** {rel['from']} to {rel['to']}. {rel['note']}")
        st.markdown(f"**Your story:**\n> {INTAKE['story'].replace('$', chr(92) + '$')}")

    up_col, sample_col = st.columns([3, 2])
    uploaded = up_col.file_uploader("Upload your credit report (PDF)", type=["pdf"])
    sample = sample_col.selectbox("Or use a sample report", list(SAMPLES), index=None, placeholder="Choose a sample")
    if uploaded is not None:
        chosen_name, pdf_bytes = uploaded.name, uploaded.getvalue()
    elif sample:
        chosen_name = SAMPLES[sample]
        pdf_bytes = (DATA / chosen_name).read_bytes()
    else:
        chosen_name, pdf_bytes = None, None

    chip_col, btn_col = st.columns([5, 1.2], vertical_alignment="center")
    if chosen_name:
        chip_col.markdown(f'<div class="file-chip">📄 {h(chosen_name)} '
                          f'<span class="muted">· {max(1, len(pdf_bytes) // 1024)} KB</span></div>',
                          unsafe_allow_html=True)
    else:
        chip_col.markdown('<div class="file-chip muted">No report chosen yet. Upload one or choose a sample.</div>',
                          unsafe_allow_html=True)
    if btn_col.button("Read report", width="stretch"):
        if not pdf_bytes:
            st.warning("Upload a PDF or choose a sample report first.")
        else:
            with st.spinner("Reading the report…"):
                try:
                    accounts, notice = run_analysis(pdf_bytes, PROMPT_VERSION)
                    st.session_state.update(accounts=accounts, notice=notice,
                                            report_id=hashlib.sha256(pdf_bytes).hexdigest()[:12], checked=None)
                except Exception as e:
                    st.error(f"Couldn't read the report: {e}")

# --- 2 · Which of these didn't you agree to? ------------------------------------

accounts = st.session_state.get("accounts")
if accounts:
    all_debts = core.group_debts(accounts)
    covs = {d["key"]: core.coverage(d) for d in all_debts}
    start = {d["key"]: (covs[d["key"]]["start_date"] or "") for d in all_debts}
    debts = sorted(all_debts, key=lambda d: (RANK[debt_prediction(d)], STATUS_RANK[covs[d["key"]]["status"]],
                                             "".join(chr(255 - ord(ch)) for ch in start[d["key"]])))

    with st.container(border=True, key="card-accounts"):
        st.markdown('<div class="sec">2 · Which of these didn\'t you agree to?</div>', unsafe_allow_html=True)
        if st.session_state.get("notice"):
            st.info(st.session_state["notice"])
        widths = [0.9, 2.4, 0.9, 0.9, 2.8, 2.0]
        with st.form(f"accounts-{st.session_state['report_id']}", border=False):
            header = st.columns(widths, vertical_alignment="bottom")
            for col, label in zip(header, ["I didn't agree to this", "Account", "Opened", "Balance",
                                           "Likely coerced? (Claude)", "Covered if coerced? (code)"]):
                col.markdown(f'<div class="th">{label}</div>', unsafe_allow_html=True)
            checks = {}
            for d in debts:
                st.divider()
                c = st.columns(widths)
                main = d["original"] or d["collection"]
                checks[d["key"]] = c[0].checkbox("I didn't agree to this", key=f"chk-{d['key']}",
                                                 label_visibility="collapsed")
                account_html = f"<div>{h(short(main))}</div>"
                if d["original"] and d["collection"]:
                    account_html += f'<div class="muted">→ now held by {h(short(d["collection"]))}</div>'
                c[1].markdown(account_html, unsafe_allow_html=True)
                c[2].markdown(mm_yyyy((d["original"] or {}).get("date_opened")))
                c[3].markdown(f"<div>{money(core.debt_balance(d))}</div>", unsafe_allow_html=True)
                label, color = PILL[debt_prediction(d)]
                c[4].markdown(f'<div><span class="pill {color}">{label}</span></div>'
                              f'<div class="muted">{h(debt_summary(d))}</div>', unsafe_allow_html=True,
                              help="\n\n".join(debt_evidence(d)).replace("$", "\\$") or None)
                c[5].markdown(covered_cell(d, covs[d["key"]]), unsafe_allow_html=True)
            st.write("")
            if st.form_submit_button("Submit"):
                st.session_state["checked"] = [k for k, v in checks.items() if v]

    # --- 3 · Your action plan ------------------------------------------------------

    checked = st.session_state.get("checked")
    if checked is not None:
        mine = [d for d in debts if d["key"] in checked]
        covered = [d for d in mine if covs[d["key"]]["status"] == "covered"]
        not_covered = [d for d in mine if covs[d["key"]]["status"] in ("not_covered_secured", "not_covered_date")]
        unknown = [d for d in mine if covs[d["key"]]["status"] == "needs_info"]

        def n_debts(n):
            return f"{n} debt{'s' if n != 1 else ''}"

        with st.container(border=True, key="card-plan"):
            st.markdown('<div class="sec">3 · Your action plan</div>', unsafe_allow_html=True)
            if not mine:
                st.info("No debts checked. Check the debts you didn't agree to, then Submit.")
            else:
                parts = [f"**{n_debts(len(covered))} you can stop collection on · "
                         f"\\${sum(core.debt_balance(d) for d in covered):,}**",
                         f"{n_debts(len(not_covered))} this law doesn't cover"]
                if unknown:
                    parts.append(f"{n_debts(len(unknown))} with an unknown start date")
                st.success(" · ".join(parts))
                cards, shown_steps = [], False
                for d in sorted(mine, key=lambda d: (STATUS_RANK[covs[d["key"]]["status"]], -core.debt_balance(d))):
                    cov = covs[d["key"]]
                    full = cov["status"] == "covered" and not shown_steps
                    shown_steps |= full
                    cards.append(plan_card(d, cov, full_steps=full))
                st.markdown("".join(cards), unsafe_allow_html=True)

            rest = [d for d in debts if d["key"] not in checked]
            with st.expander(f"Accounts that look like yours ({len(rest)}): nothing to do"):
                for d in rest:
                    main = d["original"] or d["collection"]
                    st.markdown(f"- {h(short(main))} · opened {mm_yyyy(main.get('date_opened'))} · "
                                f"{money(core.debt_balance(d))}", unsafe_allow_html=True)

            st.caption(f"{core.ASSUMPTION} {core.DISCLAIMER} Nothing is stored. "
                       f"[Read the law: California Civil Code §§ 1798.97.1–.6]({core.LAW_URL})")
