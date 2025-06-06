import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
def show_tab_sport():
    # Datei-Upload
    uploaded_file2 = st.file_uploader("Lade deine CSV- oder Excel-Datei hoch", type=["csv", "xlsx"], key="file2")

    if uploaded_file2 is not None:
        try:
            # Datei einlesen
            if uploaded_file2.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file2)
            else:
                df = pd.read_excel(uploaded_file2)

            # Prüfen, ob notwendige Spalten existieren
            required_columns = [
                "Order Date", "Category", "Item Cost", "Item Cost (inc. tax)"
            ]
            missing = [col for col in required_columns if col not in df.columns]
            if missing:
                st.error(f"❌ Fehlende Spalten: {', '.join(missing)}")
            else:
                # --- 📆 Order Date verarbeiten ---
                df["Order Date"] = pd.to_datetime(df["Order Date"], errors="coerce")
                df["Monat"] = df["Order Date"].dt.to_period("M")

                # --- 📊 Gruppieren nach Monat und Kategorie ---

                # Konvertiere den Preis in numerische Werte, um sicherzustellen, dass keine Fehler auftreten
                df["Item Cost"] = pd.to_numeric(df["Item Cost"], errors="coerce")
                df["Item Cost (inc. tax)"] = pd.to_numeric(df["Item Cost (inc. tax)"], errors="coerce")

                # Gruppieren nach "Monat" und "Category", mit der Zählung der Buchungen und Summe des Summees
                summary = df.groupby(["Monat", "Category"]).agg(
                Erlös_Brutto=("Item Cost (inc. tax)", "sum"),
                Erlös_Netto=("Item Cost", "sum")
                ).reset_index()



                #Download
                def to_excel(df):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Daten')
                    return output.getvalue()
                excel_bytes = to_excel(summary)

                st.download_button(
                    label="📥 Ergebnis-Datei herunterladen",
                    data=excel_bytes,
                    file_name="Erlösaufteilung.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download2"
                )


                # Anzeige
                st.success("✅ Übersicht nach Monat und Kategorie")
                selected_month = st.selectbox("Wähle einen Monat", sorted(summary["Monat"].astype(str).unique()))
                st.dataframe(summary[summary["Monat"].astype(str) == selected_month])

                # Berechne die Summen für jede Kategorie über alle Monate hinweg
                category_sums = summary.groupby("Category")[["Erlös_Netto", "Erlös_Brutto"]].sum()
            
                # Zeige die Summen an
                st.write("Summen über alle Monate:")
                st.dataframe(category_sums)
        except Exception as e:
            st.error(f"❌ Unerwarteter Fehler: {e}")
    else:
        st.info("⬆️ Bitte lade eine Datei hoch.")