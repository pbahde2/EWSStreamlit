import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
def show_tab_rehasport():
    st.title("Rehasport")
    # Datei-Upload
    uploaded_file_reha = st.file_uploader("Lade deine CSV- oder Excel-Datei hoch", type=["csv", "xlsx"], key="reha")

    if uploaded_file_reha is not None:
        try:
            # Datei einlesen
            if uploaded_file_reha.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file_reha, header=None)
            else:
                df = pd.read_excel(uploaded_file_reha, header=None)

            df.columns = ['', 'Kurs', 'Standort', 'Teilnehmer', "Datum", "Uhrzeit", ""]  # Beispiel
            # --- 📆 Order Date verarbeiten ---
            df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
            df["Monat"] = df["Datum"].dt.to_period("M")
            df["Jahr"] = df["Datum"].dt.to_period("Y")

            zeit_granularitaet = st.selectbox(
                "Wähle die Zeitgranularität:",
                options=["Monat", "Jahr"]
            )
            # --- 📊 Neue Spalte je nach Auswahl erstellen ---
            summary = df.groupby([zeit_granularitaet, "Kurs","Standort"]).agg(
                Anzahl_Kurse=("Kurs", "count"),
                Anzahl_Teilnehmer=("Teilnehmer", "sum")
            ).reset_index()
            summary["Durschnitt"] = summary["Anzahl_Teilnehmer"] / summary["Anzahl_Kurse"]
            
            summary_standorte = summary.groupby(["Standort", zeit_granularitaet]).agg(
                Anzahl_Kurse=("Anzahl_Kurse", "sum"),
                Anzahl_Teilnehmer=("Anzahl_Teilnehmer", "sum")).reset_index()
            summary_standorte["Durschnitt"] = summary_standorte["Anzahl_Teilnehmer"] / summary_standorte["Anzahl_Kurse"]

            # Anzeige
            st.success("✅ Übersicht über alle Standorte")
            st.dataframe(summary_standorte)

            st.success("✅ Übersicht über alle Kurse")
            selected_standorth = st.selectbox("Wähle einen Standort", sorted(summary["Standort"].astype(str).unique()))
            st.dataframe(summary[summary["Standort"].astype(str) == selected_standorth])

            

            #Download
            def to_excel(summary_standort, summary):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    summary_standort.to_excel(writer, index=False, sheet_name='Übersicht')
                    for standort, group_df in summary.groupby("Standort"):
                        # Sheet-Namen bereinigen (max. 31 Zeichen, keine ungültigen Zeichen)
                        sheet_name = str(standort)[:31].replace("/", "-").replace("\\", "-")
                        group_df.to_excel(writer, index=False, sheet_name=sheet_name)
                return output.getvalue()

            excel_bytes = to_excel(summary_standorte, summary)
            st.download_button(
                label="📥 Ergebnis-Datei herunterladen",
                data=excel_bytes,
                file_name="Rehasport.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="downloadreha"
            )
        except Exception as e:
            st.error(f"❌ Unerwarteter Fehler: {e}")
    else:
        st.info("⬆️ Bitte lade eine Datei hoch.")