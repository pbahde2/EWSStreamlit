import numpy as np
import streamlit as st
import pandas as pd
from io import BytesIO
from tabs.sportgmbh import show_tab_sport
from tabs.verein import show_tab_verein
from tabs.provisionsabrechnung import show_tab_provisionsabrechnung
from tabs.rehasport import show_tab_rehasport
from tabs.zeitbox import show_tab_zeitbox
st.sidebar.title("Navigation")
page = st.sidebar.radio("Seite auswählen", ["Zeitbox", "Erlösaufteilung (Wordpress)", "Provisionsabrechnung", "Rehasport"])

if page == "Erlösaufteilung (Wordpress)":
    st.title("Erlösaufteilung")
    tab1, tab2 = st.tabs(["Verein", "Sport GmbH"])
    with tab1:
        show_tab_verein()
    with tab2:
        show_tab_sport()

elif page == "Zeitbox":
    show_tab_zeitbox()

elif page == "Provisionsabrechnung":
    show_tab_provisionsabrechnung()

elif page == "Rehasport":
    show_tab_rehasport()
