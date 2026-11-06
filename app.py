"""NotMyDebt: Streamlit UI. Claude guesses, code applies the law, you decide."""

import datetime
import hashlib
import html
import json
import pathlib

import pandas as pd
import streamlit as st

import core
import ui

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
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

st.set_page_config(page_title="NotMyDebt", page_icon=str(ROOT / "assets" / "notmydebt_icon.png"))

COLORS = ui.SCHEMES[ui.SCHEME]
APP_CSS = f"""
<style>
[class*="st-key-card-"] {{ background: #fff; border-radius: 16px; }}
.nmd-title {{ font-size: 1.25rem; font-weight: 700; margin: 0 0 0.4rem; }}
.th {{ font-size: 0.85rem; font-weight: 600; color: #4A4560; }}
.muted {{ color: #6B6880; }}
.plan {{ border: 1.5px solid; border-radius: 12px; padding: 0.75rem 1rem; margin: 0.6rem 0; background: #fff; }}
.plan.ok {{ border-color: {COLORS["covered_border"]}; }}
.plan.no {{ border-color: {COLORS["notcovered_border"]}; }}
.plan .nmd-chip {{ margin-right: 0.45rem; }}
.plan ol {{ margin: 0.4rem 0 0 1.2rem; padding: 0; }}
.plan li {{ margin-bottom: 0.2rem; }}
hr {{ margin: 0.3rem 0 !important; }}
/* Quick exit stays visible while scrolling (CLAUDE.md non-negotiable). */
a.nmd-exit {{ position: fixed; top: 1.4rem; right: max(1rem, calc((100vw - 940px) / 2 + 1rem));
             z-index: 1000000; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2); }}
</style>
"""


def h(text):
    """Escape for HTML, and keep $ from being read as LaTeX by Streamlit's markdown."""
    return html.escape(str(text)).replace("$", "&#36;")


def money(n):
    return f"&#36;{n:,}"


def mm_yyyy(date):
    return f"{date[5:7]}/{date[:4]}" if date and len(date) >= 7 else "—"


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


def covered_cell(debt, cov):
    if debt_prediction(debt) == "likely_hers":
        return '<span class="muted">—</span>'
    if cov["status"] == "covered":
        if debt["original"] and debt["collection"]:
            return ui.chip(f"Yes, send to {short(debt['collection'])}", "covered")
        return ui.chip("Yes", "covered")
    return {"not_covered_secured": ui.chip("No, secured debt", "notcovered"),
            "not_covered_date": ui.chip("No, before July 1, 2023", "notcovered"),
            "needs_info": ui.chip("Start date unknown", "unknown")}[cov["status"]]


def plan_card(debt, cov, full_steps):
    """One result card. All legal text comes verbatim from core's constants."""
    head = f"<b>{h(plan_title(debt))} · {money(core.debt_balance(debt))}</b>"
    send_to = ui.send_to(cov["recipient"].title(), cov["address"]).replace("$", "&#36;")
    if cov["status"] == "covered":
        origin = ""
        if debt["original"] and debt["collection"]:
            origin = (f'<div class="muted">Originally {h(short(debt["original"]))}, '
                      f'sold to {h(short(debt["collection"]))}</div>')
        if not full_steps:
            return (f'<div class="plan ok">{ui.chip("Covered", "covered")}{head}'
                    f'<span class="muted"> · same 4 steps</span>{origin}{send_to}</div>')
        steps = [html.escape(s).format(recipient=f"<b>{h(cov['recipient'].title())}</b>",
                                       address=f"<b>{h(cov['address'])}</b>") for s in core.COVERED_STEPS]
        items = "".join(f"<li>{s}</li>" for s in steps)
        return f'<div class="plan ok">{ui.chip("Covered", "covered")}{head}{origin}{send_to}<ol>{items}</ol></div>'
    tag = (ui.chip("Start date unknown", "unknown") if cov["status"] == "needs_info"
           else ui.chip("Not covered", "notcovered"))
    text = core.next_steps(cov)[0]
    return f'<div class="plan no">{tag}{head}<div>{h(text)}</div></div>'


# Cache key includes the prompt + schema, so editing them forces a fresh Claude call.
PROMPT_VERSION = hashlib.sha256((core.PROMPT + json.dumps(core.RECORD_ACCOUNTS, sort_keys=True)).encode()).hexdigest()

# --- "About you" form helpers ----------------------------------------------------

YEARS = list(range(datetime.date.today().year, 1969, -1))
STILL_TOGETHER = "Still together"
PLACE_COLUMNS = {
    "Address": st.column_config.TextColumn("Address", required=True, width="large"),
    "From": st.column_config.DateColumn("From", format="MMM YYYY", required=True),
    "To": st.column_config.DateColumn("To", format="MMM YYYY", help="Leave blank for where you live now."),
    "Lived with them?": st.column_config.CheckboxColumn(
        "Lived with them?", default=False, help="Did you live here with the person who caused this debt?"),
}


def ym_to_date(ym):
    return datetime.date(int(ym[:4]), int(ym[5:7]), 1) if ym else None


def to_ym(value):
    """Date-ish cell -> 'YYYY-MM', or None if blank."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return pd.Timestamp(value).strftime("%Y-%m")


def places_frame(rows):
    return pd.DataFrame({
        "Address": pd.Series([r["address"] for r in rows], dtype="string"),
        "From": pd.Series(pd.to_datetime([ym_to_date(r["from"]) for r in rows]), dtype="datetime64[ns]"),
        "To": pd.Series(pd.to_datetime([ym_to_date(r["to"]) for r in rows]), dtype="datetime64[ns]"),
        "Lived with them?": pd.Series([bool(r.get("note")) for r in rows], dtype="bool"),
    })


def build_intake(phone, places, rel_from, rel_to, story):
    """Same shape core.analyze already gets from data/dana_intake.json."""
    places = sorted(places, key=lambda p: p["from"])
    current = next((p["address"] for p in places if not p["to"]), None)
    return {
        "client": {"phone": phone.strip() or None, "mailing_address": current},
        "address_history": [{"address": p["address"], "from": p["from"], "to": p["to"],
                             **({"note": "lived with partner"} if p["lived_with"] else {})} for p in places],
        "relationship": {"from": rel_from, "to": rel_to},
        "story": story.strip(),
    }


SAMPLE_PLACES = [{"address": a["address"], "from": a["from"], "to": a["to"], "lived_with": bool(a.get("note"))}
                 for a in INTAKE["address_history"]]
SAMPLE_INTAKE = build_intake(INTAKE["client"]["phone"], SAMPLE_PLACES, INTAKE["relationship"]["from"],
                             INTAKE["relationship"]["to"], INTAKE["story"])


def fill_sample_answers():
    """Button callback: put Dana's synthetic answers into the form widgets."""
    rel = INTAKE["relationship"]
    st.session_state.update(
        f_phone=INTAKE["client"]["phone"], f_story=INTAKE["story"],
        f_rel_from_m=MONTHS[int(rel["from"][5:7]) - 1], f_rel_from_y=int(rel["from"][:4]),
        f_rel_to_m=MONTHS[int(rel["to"][5:7]) - 1] if rel["to"] else None,
        f_rel_to_y=int(rel["to"][:4]) if rel["to"] else STILL_TOGETHER,
        places_df=places_frame(list(reversed(INTAKE["address_history"]))),  # newest first
        form_version=st.session_state.get("form_version", 0) + 1,
    )


def read_form(phone, places_df, from_m, from_y, to_m, to_y, story, pdf_bytes):
    """Validate the form. Returns (intake, errors)."""
    errors, places = [], []
    for _, row in places_df.iterrows():
        address = str(row["Address"]).strip() if isinstance(row["Address"], str) else ""
        start, end = to_ym(row["From"]), to_ym(row["To"])
        if not address and not start and not end:
            continue
        if not address:
            errors.append("Every place needs an address.")
        if not start:
            errors.append(f"Add a From date for {address or 'each place'}.")
        if start and end and start > end:
            errors.append(f"{address}: From is after To.")
        places.append({"address": address, "from": start or "", "to": end, "lived_with": bool(row["Lived with them?"])})
    if not places:
        errors.append("Add at least one place you've lived.")
    rel_from = f"{from_y}-{MONTHS.index(from_m) + 1:02d}" if from_m and from_y else None
    if not rel_from:
        errors.append("Add the month and year the relationship started.")
    if to_y == STILL_TOGETHER:
        rel_to = None
    elif to_m and to_y:
        rel_to = f"{to_y}-{MONTHS.index(to_m) + 1:02d}"
    else:
        rel_to = None
        errors.append("Add the month and year the relationship ended, or choose \"Still together\".")
    if rel_from and rel_to and rel_from > rel_to:
        errors.append("The relationship start is after its end.")
    if not pdf_bytes:
        errors.append("Upload your credit report or choose a sample report.")
    if errors:
        return None, list(dict.fromkeys(errors))
    return build_intake(phone, places, rel_from, rel_to, story), []


@st.cache_data(show_spinner=False)
def run_analysis(pdf_bytes, intake_json, prompt_version):
    """One Claude call per distinct PDF + answers (cached in memory only).
    Falls back to a saved result only for a sample report with the sample answers."""
    intake = json.loads(intake_json)
    try:
        return core.analyze(pdf_bytes, intake), None
    except Exception:
        fixture = SAMPLE_FIXTURES.get(hashlib.sha256(pdf_bytes).hexdigest())
        if fixture is None or intake != SAMPLE_INTAKE:
            raise
        return json.loads(fixture.read_text()), "Couldn't reach Claude, so this shows a saved result for this sample report."


# --- Wizard state -----------------------------------------------------------------

# Streamlit drops a widget's value when the widget isn't rendered. Re-saving the "About you" answers at the top
# of every run keeps them when she moves to step 2 or 3 and comes back.
FORM_KEYS = ("f_phone", "f_story", "f_rel_from_m", "f_rel_from_y", "f_rel_to_m", "f_rel_to_y", "f_sample")
for _k in FORM_KEYS:
    if _k in st.session_state:
        st.session_state[_k] = st.session_state[_k]

st.session_state.setdefault("step", 1)
st.session_state.setdefault("confirmed", set())   # last4 of every account she checked
accounts = st.session_state.get("accounts")
if st.session_state.step >= 2 and not accounts:
    st.session_state.step = 1
if st.session_state.step == 3 and not (st.session_state.get("plan_ready") and st.session_state.confirmed):
    st.session_state.step = 2
step_now = st.session_state.step


def go(step):
    st.session_state.step = step
    st.rerun()


def is_confirmed(debt):
    return any(a["last4"] in st.session_state.confirmed for a in debt["accounts"])


if accounts:
    all_debts = core.group_debts(accounts)
    covs = {d["key"]: core.coverage(d) for d in all_debts}
    start = {d["key"]: (covs[d["key"]]["start_date"] or "") for d in all_debts}
    debts = sorted(all_debts, key=lambda d: (RANK[debt_prediction(d)], STATUS_RANK[covs[d["key"]]["status"]],
                                             "".join(chr(255 - ord(ch)) for ch in start[d["key"]])))

# --- Header + Quick exit (fixed, always visible) + progress ------------------------

ui.inject_css()
st.markdown(APP_CSS, unsafe_allow_html=True)
ui.header(logo=str(ROOT / "assets" / "notmydebt_logo.png"))
st.progress(step_now / 3)
st.markdown(ui.steps_nav(step_now), unsafe_allow_html=True)

# --- Step 1 · About you + upload -----------------------------------------------------

if step_now == 1:
    with st.container(border=True, key="card-about"):
        title_col, fill_col = st.columns([4, 1.5], vertical_alignment="center")
        title_col.markdown(ui.step("Step 1") + '<div class="nmd-title">About you</div>', unsafe_allow_html=True)
        fill_col.button("Fill with sample answers", on_click=fill_sample_answers, width="stretch",
                        help="Fills in Dana's synthetic answers. The sample reports belong to her.")

        with st.form("about-you", border=False):
            phone = st.text_input("Your phone number", key="f_phone", placeholder="(555) 555-0100")

            st.markdown('**Places you\'ve lived** <span class="muted">· leave "To" blank for where you live now · '
                        'click the empty row to add a place</span>',
                        unsafe_allow_html=True)
            places_df = st.data_editor(
                st.session_state.get("places_df", places_frame([])),
                key=f"f_places_{st.session_state.get('form_version', 0)}",
                num_rows="dynamic", hide_index=True, width="stretch", column_config=PLACE_COLUMNS, placeholder="—")

            st.markdown("**The relationship**")
            m1, y1, m2, y2 = st.columns(4)
            from_m = m1.selectbox("Started: month", MONTHS, index=None, placeholder="Month", key="f_rel_from_m")
            from_y = y1.selectbox("Started: year", YEARS, index=None, placeholder="Year", key="f_rel_from_y")
            to_m = m2.selectbox("Ended: month", MONTHS, index=None, placeholder="Month", key="f_rel_to_m")
            to_y = y2.selectbox("Ended: year", [STILL_TOGETHER] + YEARS, index=None, placeholder="Year",
                                key="f_rel_to_y")

            story = st.text_area(
                "In your own words", key="f_story", height=110,
                placeholder="What happened with money? Mention any accounts you know were opened in your name "
                            "or that you were pushed to sign.")

            st.markdown("**Your credit report**")
            up_col, sample_col, btn_col = st.columns([3, 2, 1.2], vertical_alignment="bottom")
            uploaded = up_col.file_uploader("Upload your credit report (PDF)", type=["pdf"])
            sample = sample_col.selectbox("Or use a sample report", list(SAMPLES), index=None,
                                          placeholder="Choose a sample", key="f_sample")
            submitted = btn_col.form_submit_button("Read report", type="primary", width="stretch")
            st.caption("Nothing you type is saved. It's only sent to Claude to read your report.")

        if submitted:
            if uploaded is not None:
                pdf_bytes = uploaded.getvalue()
            elif sample:
                pdf_bytes = (DATA / SAMPLES[sample]).read_bytes()
            else:
                pdf_bytes = None
            intake, errors = read_form(phone, places_df, from_m, from_y, to_m, to_y, story, pdf_bytes)
            result = None
            if errors:
                st.error("Please check:\n" + "\n".join(f"- {e}" for e in errors))
            else:
                with st.spinner("Reading the report…"):
                    try:
                        result = run_analysis(pdf_bytes, json.dumps(intake, sort_keys=True), PROMPT_VERSION)
                    except Exception as e:
                        st.error(f"Couldn't read the report: {e}")
            if result:
                new_accounts, notice = result
                if new_accounts != accounts:   # a different report or answers: start selections fresh
                    st.session_state.update(confirmed=set(), plan_ready=False)
                st.session_state.update(
                    accounts=new_accounts, notice=notice, report_id=hashlib.sha256(pdf_bytes).hexdigest()[:12],
                    # keep the table's edits for when she comes back (new key so edits aren't applied twice)
                    places_df=places_df, form_version=st.session_state.get("form_version", 0) + 1)
                go(2)

# --- Step 2 · Which of these didn't you agree to? ---------------------------------------

elif step_now == 2:
    with st.container(border=True, key="card-accounts"):
        st.markdown(ui.step("Step 2") + '<div class="nmd-title">Which of these didn\'t you agree to?</div>',
                    unsafe_allow_html=True)
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
                # Default comes from session_state["confirmed"], since the checkbox's own value is dropped
                # whenever step 2 isn't on screen.
                checks[d["key"]] = c[0].checkbox("I didn't agree to this", key=f"chk-{d['key']}",
                                                 value=is_confirmed(d), label_visibility="collapsed")
                account_html = f"<div>{h(short(main))}</div>"
                if d["original"] and d["collection"]:
                    account_html += f'<div class="muted">→ now held by {h(short(d["collection"]))}</div>'
                c[1].markdown(account_html, unsafe_allow_html=True)
                c[2].markdown(mm_yyyy((d["original"] or {}).get("date_opened")))
                c[3].markdown(f"<div>{money(core.debt_balance(d))}</div>", unsafe_allow_html=True)
                c[4].markdown(("<div>" + ui.prediction_chip(debt_prediction(d)) + "</div>"
                               + ui.evidence([debt_summary(d)])).replace("$", "&#36;"), unsafe_allow_html=True,
                              help="\n\n".join(debt_evidence(d)).replace("$", "\\$") or None)
                c[5].markdown(covered_cell(d, covs[d["key"]]), unsafe_allow_html=True)
            st.write("")
            back_col, next_col, _ = st.columns([1, 1.4, 4])
            back = back_col.form_submit_button("Back", width="stretch")
            see_plan = next_col.form_submit_button("See my plan", type="primary", width="stretch")

        if back or see_plan:
            st.session_state.confirmed = {a["last4"] for d in debts if checks[d["key"]] for a in d["accounts"]}
        if back:
            st.session_state.plan_ready = False
            go(1)
        if see_plan:
            if not st.session_state.confirmed:
                st.warning("Check at least one account first.")
            else:
                st.session_state.plan_ready = True
                go(3)

# --- Step 3 · Your action plan ----------------------------------------------------------

else:
    mine = [d for d in debts if is_confirmed(d)]
    covered = [d for d in mine if covs[d["key"]]["status"] == "covered"]
    not_covered = [d for d in mine if covs[d["key"]]["status"] in ("not_covered_secured", "not_covered_date")]
    rest = [d for d in debts if not is_confirmed(d)]

    with st.container(border=True, key="card-plan"):
        st.markdown(ui.step("Step 3") + '<div class="nmd-title">Your action plan</div>', unsafe_allow_html=True)
        # Debts with an unknown start date stay out of the graphic; their cards still show below.
        st.markdown(ui.plan_graphic(sum(core.debt_balance(d) for d in covered), len(covered),
                                    sum(core.debt_balance(d) for d in not_covered), len(not_covered), len(rest)),
                    unsafe_allow_html=True)
        cards, shown_steps = [], False
        for d in sorted(mine, key=lambda d: (STATUS_RANK[covs[d["key"]]["status"]], -core.debt_balance(d))):
            cov = covs[d["key"]]
            full = cov["status"] == "covered" and not shown_steps
            shown_steps |= full
            cards.append(plan_card(d, cov, full_steps=full))
        st.markdown("".join(cards), unsafe_allow_html=True)

        with st.expander(f"Accounts that look like yours ({len(rest)}): nothing to do"):
            for d in rest:
                main = d["original"] or d["collection"]
                st.markdown(f"- {h(short(main))} · opened {mm_yyyy(main.get('date_opened'))} · "
                            f"{money(core.debt_balance(d))}", unsafe_allow_html=True)

        st.markdown(ui.disclaimer(f"{core.ASSUMPTION} {core.DISCLAIMER} Nothing is stored.")
                    + f'<p class="nmd-disclaimer"><a href="{h(core.LAW_URL)}" target="_blank">'
                      'Read the law: California Civil Code §§ 1798.97.1–.6</a></p>', unsafe_allow_html=True)

        back_col, over_col, _ = st.columns([1, 1.4, 4])
        if back_col.button("Back", width="stretch"):
            go(2)
        if over_col.button("Start over", width="stretch"):
            st.session_state.update(confirmed=set(), plan_ready=False)
            go(1)
