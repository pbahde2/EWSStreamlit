from functools import reduce
import pandas as pd
import streamlit as st
from tabs.controlling import physio
from tabs.controlling import tf

def show_tab_controlling():
    st.title("Controlling Gesamt")
    uploaded_file_controlling = st.file_uploader("Lade die Controlling-Datei hoch", type=["xlsx"], key="controlling",accept_multiple_files=False)
    if uploaded_file_controlling is not None:
        # Alle Sheets als Dict laden
        sheets = pd.read_excel(uploaded_file_controlling, sheet_name=None)
        
        # Nur Sheets behalten, die "Jahr" und "Quartal" enthalten
        valid_dfs = []
        for sheet_name, df in sheets.items():
            if "Jahr" in df.columns and "Quartal" in df.columns:
                df = df.copy()
                # Optional: Umbenennen der Spalten außer "Jahr" und "Quartal", damit sie eindeutig sind
                df = df.rename(columns={col: f"{sheet_name}_{col}" for col in df.columns if col not in ["Jahr", "Quartal"]})
                valid_dfs.append(df)
            else:
                st.warning(f"Blatt '{sheet_name}' enthält nicht die Spalten 'Jahr' und 'Quartal' und wird übersprungen.")

        if valid_dfs:
            # Schrittweises Mergen über Jahr & Quartal
            merged_df = reduce(lambda left, right: pd.merge(left, right, on=["Jahr", "Quartal"], how="outer"), valid_dfs)
            st.success("Sheets erfolgreich per 'Jahr' und 'Quartal' gejoined.")
            st.title("Erlösaufteilung")
            tab1, tab2 = st.tabs(["Physio", "Trainingsfläche"])
            with tab1:
                physio.show_tab_physio(merged_df)
            with tab2:
                tf.show_tab_trainigsflache(merged_df)

        else:
            st.error("Kein gültiges Sheet mit 'Jahr' und 'Quartal' gefunden.")
