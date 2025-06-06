import pdfplumber
import pandas as pd
import re
import streamlit as st
import io
from io import BytesIO

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Daten')
    return output.getvalue()

def show_tab_provisionsabrechnung():
    # === 1. Provisionen aus PDF extrahieren ===
    st.title("Provisionsabrechnung")
    st.info("Hier kannst du eine Übersicht über die Provisionsabrechnung erstellen")
    uploaded_pdf = st.file_uploader("Lade die Provisionsabrechnung als PDF hoch", type=["pdf"], key="pdf_upload")
    if uploaded_pdf is not None:
        mitarbeiter_summen = {}

        with pdfplumber.open(io.BytesIO(uploaded_pdf.read())) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                # Mitarbeitername extrahieren
                mitarbeiter_match = re.search(r"Mitarbeiter:\s+(.+)", text)
                if mitarbeiter_match:
                    mitarbeiter = mitarbeiter_match.group(1).strip()
                    mitarbeiter = re.sub(r"Seite:\s*\d+", "", mitarbeiter).strip()

                    # Endsumme extrahieren
                    endsumme_match = re.search(r"Endsumme\s+\d+\s+([\d,]+)", text)
                    if endsumme_match:
                        betrag = float(endsumme_match.group(1).replace(",", "."))
                        mitarbeiter_summen[mitarbeiter] = mitarbeiter_summen.get(mitarbeiter, 0) + betrag

        # PDF-DataFrame vorbereiten
        df_pdf = pd.DataFrame(list(mitarbeiter_summen.items()), columns=["Name", "Provision (PDF)"])
        st.dataframe(df_pdf)
        #Download
        st.download_button(
            label="📥 Provisonsabrechnung herunterladen",
            data=to_excel(df_pdf),
            file_name="Provisionsabrechnung.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pdf"
        )
        df_pdf["Name_kurz"] = (
            df_pdf["Name"]
            .str.lower()
            .str.replace("ß", "ss")
            .str.replace(r"[^a-zäöü ]", "", regex=True)
            .str.replace("-", " ")
            .str.strip()
        )

       

        # === 2. Gesamtkosten-Tabelle aus CSV einlesen ===
        uploaded_files = st.file_uploader(
            "Lade eine oder mehrere Personalkostenübersichten hoch",
            type=["csv"],
            key="file3",
            accept_multiple_files=True
        )
        dfs = []
        if uploaded_files:
            for file in uploaded_files:
                df = pd.read_csv(file, sep=";", encoding="latin1", decimal=",", skiprows=1)
                df["Name_kurz"] = (
                    df["Nachname"] + " " + df["Vorname"]
                ).str.lower().str.replace("ß", "ss").str.replace(r"[^a-zäöü ]", "", regex=True).str.replace("-", " ").str.strip()

                df["Gesamtkosten"] = (
                    df["Gesamtkosten"].astype(str)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                    .astype(float)
                )
                dfs.append(df)
            df_gesamt = pd.concat(dfs)
            # Gesamtkosten summieren pro Person
            df_gesamt = df_gesamt.groupby("Name_kurz", as_index=False)["Gesamtkosten"].sum()

            # === 3. Zusammenführen ===
            df_merged = pd.merge(df_pdf, df_gesamt, on="Name_kurz", how="left")
            df_final = df_merged[["Name", "Provision (PDF)", "Gesamtkosten"]]
            df_final["Differenz"] = df_final["Provision (PDF)"] - df_final["Gesamtkosten"]
            df_final["Quote"] = df_final["Gesamtkosten"]/df_final["Provision (PDF)"]

            st.dataframe(df_final)

            # === 4. Excel exportieren ===
            st.download_button(
            label="📥 Provisonsabrechnung herunterladen",
            data=to_excel(df_final),
            file_name="Provisionsabrechnung-und-Kosten.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="gesamt"
            )
        else:
            st.info("⬆️ Bitte lade eine Datei hoch.")
    else:
        st.info("⬆️ Bitte lade eine Datei hoch.")
