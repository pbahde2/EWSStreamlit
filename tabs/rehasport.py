import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
def show_tab_rehasport():
    st.title("Rehasport")
    # Datei-Upload
    uploaded_file_reha = st.file_uploader("Lade die Teilnehmer-Übersicht hoch (aus my-yolo)", type=["csv", "xlsx"], key="reha",accept_multiple_files=False)
    uploaded_file_Kurstrainer = st.file_uploader("Lade die Kursleiter-Übersicht hoch (selbsterstellt)", type=["csv", "xlsx"], key="kursleiter",accept_multiple_files=False)

    if uploaded_file_reha is not None:
        try:
            # Datei einlesen
            if uploaded_file_reha.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file_reha, header=None)
            else:
                df = pd.read_excel(uploaded_file_reha, header=None)

            df.columns = ['', 'Kurs', 'Standort', 'Teilnehmer', "Datum", "Uhrzeit", ""]  # Beispiel
            print("testNEU")
            # --- 📆 Order Date verarbeiten ---
            df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")
            df["Monat"] = df["Datum"].dt.to_period("M")
            df["Jahr"] = df["Datum"].dt.to_period("Y")
            df["Einnahmen"] = df["Teilnehmer"] * 6.32
            zeit_granularitaet = st.selectbox(
                "Wähle die Zeitgranularität:",
                options=["Monat", "Jahr"]
            )
            print("test")

            # --- 📊 Neue Spalte je nach Auswahl erstellen ---
            summary = df.groupby([zeit_granularitaet, "Kurs","Standort"]).agg(
                Anzahl_Kurse=("Kurs", "count"),
                Anzahl_Teilnehmer=("Teilnehmer", "sum"),
                Einnahmen=("Einnahmen","sum")
            ).reset_index()
            summary["Durschnitt-TN"] = summary["Anzahl_Teilnehmer"] / summary["Anzahl_Kurse"]
            print("test")

            #Standorte
            summary_standorte = summary.groupby(["Standort", zeit_granularitaet]).agg(
                Anzahl_Kurse=("Anzahl_Kurse", "sum"),
                Anzahl_Teilnehmer=("Anzahl_Teilnehmer", "sum"),
                Einnahmen=("Einnahmen","sum")).reset_index()
            summary_standorte["Durschnitt-TN"] = summary_standorte["Anzahl_Teilnehmer"] / summary_standorte["Anzahl_Kurse"]
            summary_kursleiter = None
            print("test")
            if uploaded_file_Kurstrainer is not None:
                # Datei einlesen
                if uploaded_file_Kurstrainer.name.endswith(".csv"):
                    df_kurstrainer = pd.read_csv(uploaded_file_Kurstrainer, header=None)
                else:
                    df_kurstrainer = pd.read_excel(uploaded_file_Kurstrainer, header=None)
                df_kurstrainer.columns = ['Kurs', 'Kursleiter',"Kursleiter-Stundenkosten"]
                summary = pd.merge(summary,df_kurstrainer,on="Kurs",how="left")
                summary["Kursleiter-Kosten"] = summary["Kursleiter-Stundenkosten"] * summary["Anzahl_Kurse"]
                summary["Gewinn"] = summary["Einnahmen"] - summary["Kursleiter-Kosten"]
                #Standorte
                print("test")
                summary_standorte = summary.groupby(["Standort", zeit_granularitaet]).agg(
                    Anzahl_Kurse=("Anzahl_Kurse", "sum"),
                    Anzahl_Teilnehmer=("Anzahl_Teilnehmer", "sum"),
                    Einnahmen=("Einnahmen","sum"),
                    Kursleiter_Kosten=("Kursleiter-Kosten","sum"),
                    Gewinn=("Gewinn","sum")).reset_index()
                summary_standorte["Durschnitt-TN"] = summary_standorte["Anzahl_Teilnehmer"] / summary_standorte["Anzahl_Kurse"]
                print("test")
                #Kursleiter
                summary_kursleiter = summary.groupby(["Kursleiter", zeit_granularitaet]).agg(
                    Anzahl_Kurse=("Anzahl_Kurse", "sum"),
                    Anzahl_Teilnehmer=("Anzahl_Teilnehmer", "sum"),
                    Einnahmen=("Einnahmen","sum"),
                    Kursleiter_Kosten=("Kursleiter-Kosten","sum"),
                    Gewinn=("Gewinn","sum")).reset_index()
                summary_kursleiter["Durschnitt-TN"] = summary_kursleiter["Anzahl_Teilnehmer"] / summary_kursleiter["Anzahl_Kurse"]
            print("test")
            # Anzeige
            st.success("✅ Übersicht über alle Standorte")
            st.dataframe(summary_standorte)

            if uploaded_file_Kurstrainer is not None:
                st.success("✅ Übersicht über alle Kursleiter")
                st.dataframe(summary_kursleiter)

            st.success("✅ Übersicht über alle Kurse")
            selected_standorth = st.selectbox("Wähle einen Standort", sorted(summary["Standort"].astype(str).unique()))
            st.dataframe(summary[summary["Standort"].astype(str) == selected_standorth])

            #Download
            def to_excel(summary_standort, summary_kursleiter, summary):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    summary_standort.to_excel(writer, index=False, sheet_name='Übersicht')
                    if summary_kursleiter is not None:
                        summary_kursleiter.to_excel(writer, index=False, sheet_name='Kursleiter')
                    for standort, group_df in summary.groupby("Standort"):
                        # Sheet-Namen bereinigen (max. 31 Zeichen, keine ungültigen Zeichen)
                        sheet_name = str(standort)[:31].replace("/", "-").replace("\\", "-")
                        group_df.to_excel(writer, index=False, sheet_name=sheet_name)
                return output.getvalue()

            excel_bytes = to_excel(summary_standorte, summary_kursleiter, summary)
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