import numpy as np
import streamlit as st
import pandas as pd
from io import BytesIO
from tabs.sportgmbh import show_tab_sport
from tabs.verein import show_tab_verein
from tabs.provisionsabrechnung import show_tab_provisionsabrechnung
from tabs.rehasport import show_tab_rehasport
from tabs.zeitbox import show_tab_zeitbox
from tabs.wordpress_datev import show_tab_wordpress_datev
from tabs.myyolo_datev import show_tab_myyolo_datev
from tabs.theorg_sta import show_tab_theorg_sta
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Seite auswählen",
    [
        "Zeitbox",
        "Erlösaufteilung (Wordpress)",
        "Wordpress-Datev",
        "MyYOLO-Datev",
        "THEORG-STA",
        "Provisionsabrechnung",
        "Rehasport",
    ],
)

if page == "Erlösaufteilung (Wordpress)":
    st.title("Erlösaufteilung")
    tab1, tab2 = st.tabs(["Verein", "Sport GmbH"])
    with tab1:
        show_tab_verein()
    with tab2:
        show_tab_sport()

elif page == "Zeitbox":
    show_tab_zeitbox()

elif page == "Wordpress-Datev":
    show_tab_wordpress_datev()

elif page == "MyYOLO-Datev":
    show_tab_myyolo_datev()

elif page == "THEORG-STA":
    show_tab_theorg_sta()

elif page == "Provisionsabrechnung":
    show_tab_provisionsabrechnung()

elif page == "Rehasport":
    show_tab_rehasport()
