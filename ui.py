"""Drop-in styling for NotMyDebt.

In app.py (set_page_config must be the first Streamlit call):

    import streamlit as st
    from ui import inject_css, header, chip, evidence, summary, send_to, disclaimer

    st.set_page_config(page_title="NotMyDebt", page_icon="assets/notmydebt_icon.png", layout="centered")
    inject_css()
    header()

Then render HTML pieces with st.markdown(..., unsafe_allow_html=True), e.g.
    st.markdown(chip("Likely coerced", "coerced") + evidence(lines), unsafe_allow_html=True)

Chip kinds: coerced, review, yours, covered, notcovered, unknown.
All model text is HTML-escaped before it's inserted.
"""
from html import escape

import streamlit as st

CSS = """
<style>
[data-testid="stHeader"] {background: transparent;}
#MainMenu, footer {visibility: hidden;}
.block-container, [data-testid="stMainBlockContainer"] {max-width: 940px; padding-top: 1.25rem;}
h1, h2, h3 {letter-spacing: -0.01em;}
[data-testid="stVerticalBlockBorderWrapper"] {background: #FFFFFF; border-radius: 16px; border-color: #E6E1D8 !important;}
.stButton button, [data-testid="stFormSubmitButton"] button {border-radius: 10px; font-weight: 600; padding: 0.45rem 1.2rem;}
[data-testid="stFileUploaderDropzone"] {border-radius: 12px;}
.nmd-step {font-size: 12px; font-weight: 700; letter-spacing: 0.06em; color: ACCENT; margin: 0 0 2px;}
.nmd-chip {display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px; white-space: nowrap;}
STATUS_CSS
.nmd-evidence {font-size: 13px; color: #5F6B6D; margin: 4px 0 0; line-height: 1.45;}
.nmd-exit {background: #C8372D; color: #FFFFFF !important; text-decoration: none !important; font-weight: 600;
           font-size: 14px; padding: 8px 16px; border-radius: 10px; display: inline-block;}
.nmd-exit:hover {background: #A82C23;}
.nmd-summary {background: SUMMARY_BG; color: SUMMARY_FG; border-radius: 12px; padding: 14px 16px; font-size: 17px; font-weight: 700;}
.nmd-summary span {font-weight: 500;}
.nmd-sendto {background: #F0ECE5; border-radius: 10px; padding: 10px 12px; font-weight: 600; margin: 8px 0;}
.nmd-disclaimer {font-size: 12px; color: #7A8583; margin-top: 12px;}
</style>
"""

# Status colors: "1" classic signals, "2" brand only, "3" red only means leave.
SCHEME = "2"
SCHEMES = {'1': {'coerced': ('#FBE9E4', '#9A3B22'), 'review': ('#FDF0DA', '#8A5A0B'), 'yours': ('#ECEBEF', '#55536A'), 'covered': ('#E3F1EC', '#1F5A4E'), 'notcovered': ('#FDF0DA', '#8A5A0B'), 'unknown': ('#ECEBEF', '#55536A'), 'summary': ('#E3F1EC', '#1F5A4E'), 'covered_border': '#9CCBB9', 'notcovered_border': '#F2C77E'}, '2': {'coerced': ('#EFE8F8', '#5B3B8C'), 'review': ('#FDF0DA', '#8A5A0B'), 'yours': ('#ECEBEF', '#55536A'), 'covered': ('#5B3B8C', '#FFFFFF'), 'notcovered': ('#FDF0DA', '#8A5A0B'), 'unknown': ('#ECEBEF', '#55536A'), 'summary': ('#EFE8F8', '#3E2766'), 'covered_border': '#B9A3DA', 'notcovered_border': '#F2C77E'}, '3': {'coerced': ('#FDF0DA', '#8A5A0B'), 'review': ('#EFE8F8', '#5B3B8C'), 'yours': ('#ECEBEF', '#55536A'), 'covered': ('#E3F1EC', '#1F5A4E'), 'notcovered': ('#ECEBEF', '#55536A'), 'unknown': ('#ECEBEF', '#55536A'), 'summary': ('#E3F1EC', '#1F5A4E'), 'covered_border': '#9CCBB9', 'notcovered_border': '#CFCCD8'}}

QUICK_EXIT_URL = "https://www.google.com/search?q=weather"


def inject_css():
    accent = st.get_option("theme.primaryColor") or "#2F6F62"  # follows .streamlit/config.toml
    s = SCHEMES[SCHEME]
    status = "\n".join(f".nmd-{k} {{background: {s[k][0]}; color: {s[k][1]};}}"
                       for k in ("coerced", "review", "yours", "covered", "notcovered", "unknown"))
    css = (CSS.replace("ACCENT", accent).replace("STATUS_CSS", status)
           .replace("SUMMARY_BG", s["summary"][0]).replace("SUMMARY_FG", s["summary"][1]))
    st.markdown(css, unsafe_allow_html=True)


def header(logo="assets/notmydebt_logo.png"):
    left, right = st.columns([4, 1])
    with left:
        st.image(logo, width=260)
        st.caption("Debt that was never yours  ·  Synthetic data  ·  Review results with an advocate")
    with right:
        # target="_self" keeps Quick exit in the same tab (st.link_button opens a new one).
        st.markdown(f'<div style="text-align:right"><a class="nmd-exit" href="{QUICK_EXIT_URL}" '
                    f'target="_self">Quick exit</a></div>', unsafe_allow_html=True)


def step(label):
    """Small teal step label above a section title, e.g. step('Step 2')."""
    return f'<p class="nmd-step">{escape(label).upper()}</p>'


def chip(text, kind):
    return f'<span class="nmd-chip nmd-{kind}">{escape(text)}</span>'


PREDICTION_CHIP = {
    "likely_coerced": ("Likely coerced", "coerced"),
    "needs_review": ("Needs review", "review"),
    "likely_hers": ("Likely yours", "yours"),
}


def prediction_chip(prediction):
    text, kind = PREDICTION_CHIP.get(prediction, ("Needs review", "review"))
    return chip(text, kind)


def evidence(lines):
    return '<p class="nmd-evidence">' + "<br>".join(escape(l) for l in lines) + "</p>"


def summary(main, rest=""):
    return f'<div class="nmd-summary">{escape(main)} <span>{escape(rest)}</span></div>'


def send_to(recipient, address):
    return f'<div class="nmd-sendto">Send to: {escape(recipient)}, {escape(address or "")}</div>'


def disclaimer(text):
    return f'<p class="nmd-disclaimer">{escape(text)}</p>'
