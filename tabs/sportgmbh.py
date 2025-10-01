import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
def show_tab_sport():
    # Datei-Upload
    st.subheader("Upload - Wordpress")
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
                "Order Date", "Category", "Item Cost", "Item Cost (inc. tax)", "Payment Method"
            ]
            missing = [col for col in required_columns if col not in df.columns]
            if missing:
                st.error(f"❌ Fehlende Spalten: {', '.join(missing)}")
            else:
                stripe = st.checkbox("Filtern: Nur Stripe-Erlöse", value=True)
                if stripe:
                    df = df[df["Payment Method"].isin(["stripe", "stripe_sepa_debit"])]
                    
                    # Datei-Upload
                    st.subheader("Upload - Stripe - Datei")
                    uploaded_file3 = st.file_uploader("Lade deine CSV-Datei hoch", type=["csv", "xlsx"], key="file23")
                    if uploaded_file3 is not None:
                        df_stripe = pd.read_csv(uploaded_file3, sep=",", decimal=",")
                        for col in ["Amount", "Fee", "Net"]:
                            df_stripe[col] = pd.to_numeric(df_stripe[col], errors="coerce")
                        df_stripe = df_stripe[df_stripe["Type"]!="payout"]
                        df_stripe["Created (UTC)"] = pd.to_datetime(df_stripe["Created (UTC)"])
                        # Alles zusammenfassen in gewünschtem Format
                        df_stripe["Created"] = df_stripe["Created (UTC)"].dt.strftime("%d %m %Y %H:%M:%S")

                        df = df.drop_duplicates(keep="first", subset="Order ID")
                        df_join = pd.merge(df, df_stripe, left_on="Order ID", right_on="order_id (metadata)", how="right")
                        
                        df_join["diff"] = df_join["Amount"] - df_join["Item Cost (inc. tax)"]
                        df_missing = df_join[df_join["Order ID"].isna()]

                        if len(df_missing) > 0:
                            st.warning("Für Folgende Stripe-Transaktionen konnte keine Bestellung gefunden werden:")
                            st.dataframe(df_missing[["id", "Type", "Amount", "Created", "order_id (metadata)"]])
                        df = df_join[df_join["Order ID"].notna()]
                        df["Item Cost (inc. tax)"] = df["Amount"]
                        show_rest(df, stripe)
                else:
                    show_rest(df, stripe)
        except Exception as e:
            st.error(f"❌ Unerwarteter Fehler: {e}")
    else:
        st.info("⬆️ Bitte lade eine Datei hoch.")


def show_rest(df, stripe):
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
    ).reset_index()

    

    # Summen pro Kategorie
    category_sums = summary.groupby("Category")[["Erlös_Brutto"]].sum()

    # Gesamtsumme berechnen
    total_sum = category_sums.sum().to_frame().T  # Summe über alle Kategorien
    total_sum.index = ["Gesamt"]  # Index für die Gesamtsumme setzen

    # Gesamtsumme an die Kategorie-Summen anhängen
    category_sums = pd.concat([category_sums, total_sum])

    # Zeige die Summen an
    st.write("Summen über alle Monate:")
    st.dataframe(category_sums)
    if not stripe:
        # Anzeige
        st.success("✅ Übersicht nach Monat und Kategorie")
        selected_month = st.selectbox("Wähle einen Monat", sorted(summary["Monat"].astype(str).unique()))
        st.dataframe(summary[summary["Monat"].astype(str) == selected_month])

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