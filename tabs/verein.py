import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
def show_tab_verein():
    # Datei-Upload
    uploaded_file = st.file_uploader("Lade deine CSV- oder Excel-Datei hoch", type=["csv", "xlsx"])

    if uploaded_file is not None:
        try:
            # Datei einlesen
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            # Prüfen, ob notwendige Spalten existieren
            required_columns = [
                "Order Date", "Category", "Product Current Price",
                "Order Refund Amount", "Item Cost"
            ]
            missing = [col for col in required_columns if col not in df.columns]
            if missing:
                st.error(f"❌ Fehlende Spalten: {', '.join(missing)}")
            else:
                # --- 📆 Order Date verarbeiten ---
                df["Order Date"] = pd.to_datetime(df["Order Date"], errors="coerce")
                df["Monat"] = df["Order Date"].dt.to_period("M")

                # --- 📊 Gruppieren nach Monat und Kategorie ---
                # Kategorien, die wir filtern möchten
                kategorien = [
                    "Sommerferien", "Osterferien", "Feiertage",
                    "Herbstferien", "Winterferien", "Prävention", "Rücktrittsschutz"
                ]

            # Splitte die 'Category' Spalte in Listen von Kategorien
                vorher = (len(df))
                print("TEST NEU")
                print(df["Item Cost"].sum())
                df["Category"] = df["Category"].apply(lambda x: x.split(','))

                # Filtern nach den gewünschten Kategorien
                df = df[df["Category"].apply(lambda x: any(cat in kategorien for cat in x))]

                # Ersetze die Kategorie-Spalte durch die erste gefundene Kategorie, die in der Liste 'kategorien' ist
                df["Category"] = df["Category"].apply(lambda x: next((cat for cat in x if cat in kategorien), None))
                # Welche Einträge sind rausgefallen?

                # Optional anzeigen
                if len(df)-vorher > 0:
                    st.write("❌ Es wurden "+ str(len(df)-vorher)+" Einträge entfernt, da sie keiner Kategorie zugeordnet werden konnten:")

                # Konvertiere den Preis in numerische Werte, um sicherzustellen, dass keine Fehler auftreten
                df["Product Current Price"] = pd.to_numeric(df["Product Current Price"], errors="coerce")
                df["Price Difference"] =  df["Item Cost"] - df["Product Current Price"]

                # Gruppieren nach "Monat" und "Category", mit der Zählung der Buchungen und Summe des Summees
                summary = df.groupby(["Monat", "Category"]).agg(
                Erlös=("Product Current Price", "sum"),
                Preisunterschied=("Price Difference", "sum")
                ).reset_index()

                #Rücktrittschutz berechnen (erhöhen um zusammenhängend gebucht)
                monthly_price_diff = df.groupby("Monat")["Price Difference"].sum().reset_index()
                # Schritt 1: Erstelle ein Dictionary, das den Preisunterschied für jeden Monat enthält
                price_diff_dict = dict(zip(monthly_price_diff["Monat"], monthly_price_diff["Price Difference"]))
                # Schritt 1: Alle Monate im Preis-Diff-Dict prüfen
                for monat, price_diff in price_diff_dict.items():
                    # Prüfe, ob es in summary keine Zeile mit diesem Monat und Kategorie "Rücktrittsschutz" gibt
                    if not ((summary["Monat"] == monat) & (summary["Category"] == "Rücktrittsschutz")).any():
                        # Neue Zeile definieren
                        neue_zeile = {
                            "Monat": monat,
                            "Category": "Rücktrittsschutz",
                            "Erlös": 0,
                            "Preisunterschied":0
                        }
                        # Zeile zum DataFrame hinzufügen
                        print("Angefügt" +str(monat))
                        summary = pd.concat([summary, pd.DataFrame([neue_zeile])], ignore_index=True)

                # Schritt 2: Aktualisiere bestehenden Erlös (wie du es schon machst)
                def update_erlös(row):
                    if row["Category"] == "Rücktrittsschutz":
                        price_diff = price_diff_dict.get(row["Monat"], 0)
                        return row["Erlös"] + price_diff
                    else:
                        return row["Erlös"]

                # Schritt 3: Wende die Funktion auf den DataFrame an
                summary["Erlös"] = summary.apply(update_erlös, axis=1)
                #summary = summary.drop(columns=["Preisunterschied"])

                # Rückerstattungen berechnen
                df_unique = df.sort_values("Date of first refund").drop_duplicates(subset="Order Number", keep="first")
                df_unique["Date of first refund"] = pd.to_datetime(df_unique["Date of first refund"], errors="coerce")
                df_unique["Monat"] = df_unique["Date of first refund"].dt.to_period("M")
                df_unique["Erstattungen_Ruecktrittsschutz"] = np.where(
                    df_unique["Order Refund Amount"].isin([100,80,60, 40, 20]),
                    df_unique["Order Refund Amount"],
                    0
                )

                df_unique["Erstattungen_Andere"] = np.where(
                    ~df_unique["Order Refund Amount"].isin([100,80,60, 40, 20]),
                    df_unique["Order Refund Amount"],
                    0
                )
                #Alle Erstattungen
                erstattungen = df_unique.groupby(["Monat", "Category"]).agg(
                Erstattungen_Ruecktrittsschutz=("Erstattungen_Ruecktrittsschutz", "sum"),
                Erstattungen=("Erstattungen_Andere", "sum"), 

                ).reset_index()
                #Erlös mindern um erstattungen
                df_join = pd.merge(summary, erstattungen, how="left", on=["Category","Monat"])

                ##Erstattungen für rücktrittsschutz
                df_erstattungen_monatlich = erstattungen.groupby(["Monat"]).agg(
                Erstattungen=("Erstattungen_Ruecktrittsschutz", "sum"),

                ).reset_index()
                df_erstattungen_monatlich["Category"] = "Erstattungen Rücktrittsschutz"
                #Anfügen des Rücktrittsschutzes
                df_union = pd.concat([df_erstattungen_monatlich, df_join])
                df_union["Summe"] = df_union["Erlös"].fillna(0) - df_union["Erstattungen"].fillna(0)
                df_union = df_union[["Monat", "Category", "Erlös", "Erstattungen", "Summe",]]
                df_union = df_union.sort_values("Monat")

                #Download

                def to_excel(df):
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_union.to_excel(writer, index=False, sheet_name='Daten')
                    return output.getvalue()
                excel_bytes = to_excel(df)

                st.download_button(
                    label="📥 Ergebnis-Datei herunterladen",
                    data=excel_bytes,
                    file_name="Erlösaufteilung.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )


                # Anzeige
                st.success("✅ Übersicht nach Monat und Kategorie")
                selected_month = st.selectbox("Wähle einen Monat", sorted(df_union["Monat"].astype(str).unique()))
                st.dataframe(df_union[df_union["Monat"].astype(str) == selected_month])

                # Berechne die Summen für jede Kategorie über alle Monate hinweg
                category_sums = df_union.groupby("Category")[["Erlös", "Erstattungen", "Summe"]].sum()
            
                # Zeige die Summen an
                st.write("Summen über alle Monate:")
                st.dataframe(category_sums)
        except Exception as e:
            st.error(f"❌ Unerwarteter Fehler: {e}")
    else:
        st.info("⬆️ Bitte lade eine Datei hoch.")