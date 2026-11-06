"""NotMyDebt: Streamlit UI. Claude guesses, code applies the law, she decides."""

import hashlib
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
CHIP = {"likely_coerced": ("Likely coerced", "red"),
        "needs_review": ("Needs review", "orange"),
        "likely_hers": ("Looks like hers", "green")}

st.set_page_config(page_title="NotMyDebt", page_icon="🛡️", layout="wide")


def md(text):
    """Escape $ so Streamlit markdown doesn't treat dollar amounts as LaTeX."""
    return str(text).replace("$", "\\$")


def money(n):
    return f"\\${n:,}"


def name(account):
    return account["creditor"].title()


def debt_title(debt):
    orig, coll = debt["original"], debt["collection"]
    if orig and coll:
        return f"{name(orig)} → now held by {name(coll)}"
    return name(core.holder(debt))


def debt_numbers(debt):
    return " / ".join(f"…{a['last4']}" for a in ([debt["original"], debt["collection"]]) if a)


def debt_prediction(debt):
    return min((a["prediction"] for a in debt["accounts"]), key=lambda p: RANK[p])


def debt_evidence(debt):
    lines = []
    for a in debt["accounts"]:
        for line in a.get("evidence") or []:
            if line not in lines:
                lines.append(line)
    return lines[:3]


def coverage_label(cov):
    return {"covered": f"✅ Yes, send to {name({'creditor': cov['recipient']})}",
            "not_covered_secured": "❌ Secured debt",
            "not_covered_date": "❌ Before July 1, 2023",
            "needs_info": "? Start date unknown"}[cov["status"]]


@st.cache_data(show_spinner=False)
def run_analysis(pdf_bytes):
    """One Claude call per distinct PDF (cached in memory). Falls back to a saved result for the samples."""
    try:
        return core.analyze(pdf_bytes, INTAKE), None
    except Exception as e:
        fixture = SAMPLE_FIXTURES.get(hashlib.sha256(pdf_bytes).hexdigest())
        if fixture is None:
            raise
        return json.loads(fixture.read_text()), f"Couldn't reach Claude ({e}). Showing a saved result for this sample."


# --- Header + Quick exit ------------------------------------------------------

st.markdown("""
<style>
a.quick-exit {
  position: fixed; top: 4rem; right: 2rem; z-index: 1000000;
  background: #c62828; color: #fff !important; text-decoration: none !important;
  padding: 0.5rem 1.1rem; border-radius: 0.5rem; font-weight: 700;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
}
a.quick-exit:hover { background: #8e0000; }
</style>
<a class="quick-exit" href="https://www.google.com/search?q=weather" target="_self">Quick exit</a>
""", unsafe_allow_html=True)

st.title("NotMyDebt")
st.caption("Synthetic data · Draft for advocate review")

# --- Dana's info --------------------------------------------------------------

with st.expander("Dana's info"):
    client = INTAKE["client"]
    st.markdown(f"**Phone:** {client['phone']}  \n**Mailing address:** {client['mailing_address']}  \n"
                f"**Contact preference:** {client['contact_preference']}")
    st.markdown("**Addresses**")
    st.table([{"Address": a["address"], "From": a["from"], "To": a["to"] or "now", "Note": a.get("note", "")}
              for a in INTAKE["address_history"]])
    rel = INTAKE["relationship"]
    st.markdown(f"**Relationship:** {rel['from']} to {rel['to']}. {rel['note']}")
    st.markdown(f"**Her story:**\n> {md(INTAKE['story'])}")

# --- Upload ------------------------------------------------------------------

left, right = st.columns(2)
uploaded = left.file_uploader("Upload a credit report (PDF)", type=["pdf"])
sample = right.selectbox("Use a sample report", list(SAMPLES), index=None, placeholder="Choose a sample")

if st.button("Read report", type="primary"):
    if uploaded is not None:
        pdf_bytes = uploaded.getvalue()
    elif sample:
        pdf_bytes = (DATA / SAMPLES[sample]).read_bytes()
    else:
        pdf_bytes = None
        st.warning("Upload a PDF or choose a sample report first.")
    if pdf_bytes:
        with st.spinner("Reading the report…"):
            try:
                accounts, notice = run_analysis(pdf_bytes)
                st.session_state.update(accounts=accounts, notice=notice,
                                        report_id=hashlib.sha256(pdf_bytes).hexdigest()[:12], checked=None)
            except Exception as e:
                st.error(f"Couldn't read the report: {e}")

# --- Accounts ----------------------------------------------------------------

accounts = st.session_state.get("accounts")
if accounts:
    if st.session_state.get("notice"):
        st.info(st.session_state["notice"])
    debts = sorted(core.group_debts(accounts), key=lambda d: RANK[debt_prediction(d)])

    st.subheader("Accounts on the report")
    st.caption("Check each debt she didn't agree to. Nothing is pre-checked. She decides.")
    widths = [1.1, 2.4, 1, 1, 3, 2]
    with st.form(f"accounts-{st.session_state['report_id']}"):
        header = st.columns(widths)
        for col, label in zip(header, ["She didn't agree to this", "Account", "Opened", "Balance",
                                       "Likely coerced?", "Covered if coerced?"]):
            col.markdown(f"**{label}**")
        checks = {}
        for d in debts:
            st.divider()
            c = st.columns(widths, vertical_alignment="top")
            checks[d["key"]] = c[0].checkbox(f"She didn't agree to {debt_title(d)}", key=f"chk-{d['key']}",
                                             label_visibility="collapsed")
            c[1].markdown(f"**{md(debt_title(d))}**  \n{debt_numbers(d)}")
            c[2].markdown((d["original"] or {}).get("date_opened") or "—")
            c[3].markdown(money(core.debt_balance(d)))
            label, color = CHIP[debt_prediction(d)]
            c[4].badge(label, color=color)
            for line in debt_evidence(d):
                c[4].caption(md(line))
            c[5].markdown(coverage_label(core.coverage(d)))
        if st.form_submit_button("Submit", type="primary"):
            st.session_state["checked"] = [k for k, v in checks.items() if v]

    # --- Results -------------------------------------------------------------

    checked = st.session_state.get("checked")
    if checked is not None:
        st.subheader("Next steps")
        mine = [d for d in debts if d["key"] in checked]
        covs = {d["key"]: core.coverage(d) for d in mine}
        covered = [d for d in mine if covs[d["key"]]["status"] == "covered"]
        not_covered = [d for d in mine if covs[d["key"]]["status"] in ("not_covered_secured", "not_covered_date")]
        unknown = [d for d in mine if covs[d["key"]]["status"] == "needs_info"]

        def n_debts(n):
            return f"{n} debt{'s' if n != 1 else ''}"

        if not mine:
            st.info("No debts checked. Check the debts she didn't agree to, then Submit.")
        else:
            parts = [f"**{n_debts(len(covered))} you can stop collection on · "
                     f"{money(sum(core.debt_balance(d) for d in covered))}**",
                     f"{n_debts(len(not_covered))} this law doesn't cover"]
            if unknown:
                parts.append(f"{n_debts(len(unknown))} with an unknown start date")
            st.success(" · ".join(parts))

        for d in sorted(mine, key=lambda d: ["covered", "needs_info", "not_covered_date",
                                             "not_covered_secured"].index(covs[d["key"]]["status"])):
            cov = covs[d["key"]]
            with st.container(border=True):
                st.markdown(f"#### {md(debt_title(d))} · {money(core.debt_balance(d))}")
                st.markdown(f"{debt_numbers(d)} · {coverage_label(cov)}")
                steps = core.next_steps(cov, bold=True)
                if cov["status"] == "covered":
                    st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
                else:
                    st.markdown(steps[0])

        with st.expander("Accounts that look like yours"):
            rest = [d for d in debts if d["key"] not in checked]
            if not rest:
                st.write("None. Every account is checked above.")
            for d in rest:
                st.markdown(f"- **{md(debt_title(d))}** {debt_numbers(d)} · opened "
                            f"{(d['original'] or {}).get('date_opened') or '—'} · {money(core.debt_balance(d))}")

        st.caption(core.ASSUMPTION)
        st.caption(core.DISCLAIMER)
        st.markdown(f"[Read the law: California Civil Code §§ 1798.97.1–.6]({core.LAW_URL})")
