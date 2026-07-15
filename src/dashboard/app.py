"""Entry point: `streamlit run src/dashboard/app.py` (or `make dashboard`)."""

from __future__ import annotations

import sys
from pathlib import Path

# allow running via `streamlit run` without an editable install
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from dashboard import theme
from dashboard.views import corpus, design, readout, sequential_view

st.set_page_config(
    page_title="Upworthy experiment readouts",
    page_icon="🧪",
    layout="wide",
)
theme.inject()

pages = st.navigation(
    [
        # NOTE: Streamlit serves the default page at "/" and ignores url_path on it
        st.Page(readout.render, title="Experiment readout", icon="🔎", default=True),
        st.Page(sequential_view.render, title="Sequential monitoring", icon="⏱️",
                url_path="sequential"),
        st.Page(design.render, title="Design a test", icon="📐", url_path="design"),
        st.Page(corpus.render, title="Corpus explorer", icon="🗺️", url_path="corpus"),
    ]
)

with st.sidebar:
    st.markdown(
        '<div style="font-family:Sora,sans-serif;font-weight:700;font-size:1.05rem;'
        'letter-spacing:-.01em;line-height:1.4;margin-bottom:.2rem">'
        '32,487 real A/B tests</div>'
        '<div style="height:2px;width:44px;border-radius:99px;margin-bottom:.7rem;'
        'background:linear-gradient(90deg,#2a78d6,#1baf7a)"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Decision-grade readouts for the Upworthy Research Archive. "
        "Methods were developed on the exploratory split only; every default "
        "(alpha, priors, gates) lives in `config/`.\n\n"
        "An uncorrected significant result is never presented as a win."
    )

pages.run()
