import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import datetime

MANDANT_SPORT = 14118
MANDAT_GESUNDHEIT = 14168
MANDANT_SPORTSCHULE = 14203
MANDANT_VEREIN = 14117

LOHNART_PLUS = 8500
LOHNART_MINUS = 8501
LOHNART_URLAUB = 8560

BERATERNUMMER = 446024

def show_tab_zeitbox():
    st.header("Zeitbox-DATEV-Export 📄")
    st.subheader("Datenupload und Filter 📤 ❌")
    with st.expander("Monat auswählen 📅", expanded = True):

    # Liste der Monate
        monate = {
            "Januar": "01", "Februar": "02", "März": "03", "April": "04",
            "Mai": "05", "Juni": "06", "Juli": "07", "August": "08",
            "September": "09", "Oktober": "10", "November": "11", "Dezember": "12"
        }
        jahre = list(range(2000, 2101))  # Jahr-Auswahl

        # aktuellen Monat bestimmen
        heute = datetime.date.today()
        letzter_monat = (heute.replace(day=1) - datetime.timedelta(days=1))

        default_monat_name = list(monate.keys())[letzter_monat.month - 1]
        default_jahr = letzter_monat.year

        col1, col2 = st.columns(2)
        with col1:
            monat_name = st.selectbox(
                "Monat wählen",
                list(monate.keys()),
                index=list(monate.keys()).index(default_monat_name)
            )
        with col2:
            jahr = st.selectbox(
                "Jahr wählen",
                jahre,
                index=jahre.index(default_jahr)
            )
        # Ausgabe MM/JJJJ
        monat_string = f"{monate[monat_name]}/{jahr}"
        monat_string_speichern = f"{monat_name}{jahr}"
    expander = st.expander("Datenupload 📤", expanded = True)
    with expander:
        # Datei-Upload
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Upload Zeitbox")
            uploaded_file = st.file_uploader("Lade hier die Tabelle aus Zeitbox hoch", type=["csv", "xlsx"])
        with col2:
            st.subheader("Upload MA-Zuordnung")
            uploaded_file_ma = st.file_uploader("Lade hier die MA-Mandanten-Zuordnung", type=["csv", "xlsx"])

    if uploaded_file is not None and uploaded_file_ma is not None:
        with expander:
            df = check_correct_data(uploaded_file, uploaded_file_ma)
        with st.expander("Mitarbeiter aus Datei entfernen ❌", expanded = False):
            df = filter(df)
        st.header("Daten überprüfen 🔍")
        df_arbeitszeit = get_df_arbeitszeit(df)
        df_urlaub = get_df_urlaub(df)
        df_final = pd.concat([df_urlaub, df_arbeitszeit], ignore_index=True)
        st.header("Datein exportieren 📥")

        col1, col2 = st.columns(2)
        with col1:
            df_datev= get_datev_datei(df_final, MANDAT_GESUNDHEIT, monat_string)
            show_datev_download(df_datev, f"Arbeitszeit_Gesundheit_{monat_string_speichern}", "Gesundheit")
        with col2:
            df_datev= get_datev_datei(df_final, MANDANT_SPORT, monat_string)
            show_datev_download(df_datev, f"Arbeitszeit_Sport_{monat_string_speichern}", "Sport")
        col1, col2 = st.columns(2)
        with col1:
            df_datev= get_datev_datei(df_final, MANDANT_SPORTSCHULE, monat_string)
            show_datev_download(df_datev, f"Arbeitszeit_Sportschule_{monat_string_speichern}", "Sportschule")
        with col2:
            df_datev= get_datev_datei(df_final, MANDANT_VEREIN, monat_string)
            show_datev_download(df_datev, f"Arbeitszeit_Verein_{monat_string_speichern}", "Verein")



def check_correct_data(uploaded_file, uploaded_file_ma):
    # Datei einlesen
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, sep=";", encoding="utf-8")
    else:
        df = pd.read_excel(uploaded_file)

    if uploaded_file_ma.name.endswith(".csv"):
        df_ma = pd.read_csv(uploaded_file_ma, sep=";", encoding="utf-8")
    else:
        df_ma = pd.read_excel(uploaded_file_ma)

    # -----------------------------
    # Personalnummer als int einlesen
    # -----------------------------
    # Personalnummern korrekt einlesen (verhindert angehängte 0!)
    for data in (df, df_ma):
        if "Pers.-Nr." in data.columns:
            data["Pers.-Nr."] = (
                pd.to_numeric(data["Pers.-Nr."], errors="coerce")  # 12345.0 → 12345
                .astype("Int64")                                   # echter Integer
        )


    # Prüfen, ob notwendige Spalten existieren
    required_columns = [
        "Vorname","Nachname","Pers.-Nr.","Gesamtzeit Std:Min","Gesamtzeit Dezimal",
        "Soll-Zeit Std:Min","Soll-Zeit Dezimal","Überstunden Std:Min","Überstunden Dezimal",
        "Abwesenheiten Datum","Abwesenheiten Typ","Abwesenheiten Dauer (Tage)"
    ]

    required_columns_ma = ["Vorname", "Nachname", "Pers.-Nr.", "Mandant"]

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        st.error(f"❌ Fehlende Spalten in der Zeitbox-Datei: {', '.join(missing)}")
        st.info("Überprüfe ob du die Option 'Abwesenheits-Sollstunden anzeigen' aktiviert hast.")

    missing = [col for col in required_columns_ma if col not in df_ma.columns]
    if missing:
        st.error(f"❌ Fehlende Spalten in der MA-Zuordnung: {', '.join(missing)}")

    # Vergleichslogik
    join_keys = ["Vorname", "Nachname", "Pers.-Nr."]

    only_in_df = df.merge(df_ma[join_keys], on=join_keys, how="left", indicator=True)
    only_in_df = only_in_df[only_in_df["_merge"] == "left_only"].drop(columns="_merge")

    only_in_df_ma = df_ma.merge(df[join_keys], on=join_keys, how="left", indicator=True)
    only_in_df_ma = only_in_df_ma[only_in_df_ma["_merge"] == "left_only"].drop(columns="_merge")

    if not only_in_df.empty:
        st.subheader("🔹 Zeilen nur in Zeitbox-Datei")
        st.warning("Achtung!! Diese MA tauchen in Zeitbox auf, aber nicht in der Zuordnung!! Sie tauchen in der Finalen Datei daher nicht auf!")
        st.write(only_in_df)

    if not only_in_df_ma.empty:
        st.subheader("🔹 Zeilen nur in MA-Zuordnung")
        st.warning("Achtung!! Diese MA tauchen in Zuordnung auf, aber nicht in Zeitbox!! Sie tauchen in der Finalen Datei daher nicht auf!")
        st.write(only_in_df_ma)

    st.success("Daten konnten korrekt eingelesen werden")

    # -----------------------------
    # Am Ende: Personalnummer als 5-stelliger String formatieren
    # -----------------------------
    merged = df.merge(df_ma, on=join_keys, how="inner")
    # Am Ende: Zeilen ohne Personalnummer löschen
    merged = merged.dropna(subset=["Pers.-Nr."])

    # Personalnummer als 5-stelligen String formatieren
    merged["Pers.-Nr."] = (
        merged["Pers.-Nr."]
        .astype(int)
        .astype(str)
        .str.zfill(5)
    )
    return merged


def filter(merged):
    if merged is not None and not merged.empty:

        # 1️⃣ Eindeutige Personenliste bauen (für das Multiselect)
        personen_df = (
            merged[["Pers.-Nr.", "Vorname", "Nachname"]]
            .drop_duplicates()
            .copy()
        )

        # Schöne Anzeige im Multiselect, z.B.: "01234 – Max Mustermann"
        personen_df["Label"] = personen_df.apply(
            lambda r: f"{r['Pers.-Nr.']} – {r['Vorname']} {r['Nachname']}", axis=1
        )

        # 2️⃣ Multiselect in Streamlit
        auszuschliessen = st.multiselect(
            "Mitarbeitende, die NICHT in der finalen Datei sein sollen:",
            options=personen_df["Label"].tolist(),
        )

        # 3️⃣ Daraus die Personalnummern der auszuschließenden Personen ermitteln
        excl_persnr = personen_df.loc[
            personen_df["Label"].isin(auszuschliessen), "Pers.-Nr."
        ]

        # 4️⃣ Gefiltertes DataFrame (ohne die ausgewählten Personen)
        return merged[~merged["Pers.-Nr."].isin(excl_persnr)]

      



def get_df_urlaub(df):

    with st.expander("Erkannten Urlaubstage 🏖️", expanded = False):
        convert_to_numeric("Überstunden Dezimal", df)
        df_arbeitszeit= df[["Pers.-Nr.", "Vorname", "Nachname", "Abwesenheiten Typ", "Abwesenheiten Dauer (Tage)", "Mandant"]]
        df = df_arbeitszeit[df_arbeitszeit["Abwesenheiten Typ"] == "Urlaub (bezahlt)"]

        # sicherstellen, dass die Tage numerisch sind
        convert_to_numeric("Abwesenheiten Dauer (Tage)", df)
        # Summieren pro Mitarbeiter
        df = (
            df
            .groupby(["Pers.-Nr.", "Vorname", "Nachname", "Mandant"], as_index=False)
            ["Abwesenheiten Dauer (Tage)"]
            .sum()
        )

        df = df.sort_values(by="Abwesenheiten Dauer (Tage)", ascending=False)
        st.dataframe(df)
        # 3️⃣ Lohnart zuweisen
        df["Lohnart"] = LOHNART_URLAUB
        df["Wert"] = df["Abwesenheiten Dauer (Tage)"]

        return df[["Mandant", "Pers.-Nr.", "Lohnart", "Wert"]]


def get_df_arbeitszeit(df):
        convert_to_numeric("Überstunden Dezimal", df)
        df_arbeitszeit= df[["Pers.-Nr.", "Vorname", "Nachname", "Überstunden Dezimal", "Mandant"]]
        with st.expander("Erkannte Überstunden ⬆️", expanded=True):
            filtered_df = df_arbeitszeit[df_arbeitszeit["Überstunden Dezimal"] > 0]
            sorted_df = filtered_df.sort_values(by="Überstunden Dezimal", ascending=False)
            st.dataframe(sorted_df)
        with st.expander("Erkannte Minusstunden ⬇️", expanded=True):
            filtered_df = df_arbeitszeit[df_arbeitszeit["Überstunden Dezimal"] < 0]
            sorted_df = filtered_df.sort_values(by="Überstunden Dezimal", ascending=True)
            st.dataframe(sorted_df)
        df_arbeitszeit["Überstunden Dezimal"] = df_arbeitszeit["Überstunden Dezimal"] * -1

        # 1️⃣ Zuerst NaN in Zahlen konvertieren (falls nötig)
        df_arbeitszeit["Überstunden Dezimal"] = pd.to_numeric(
            df_arbeitszeit["Überstunden Dezimal"], errors="coerce"
        )

        # 2️⃣ Nur Zeilen behalten, die != 0 und nicht NaN sind
        df_arbeitszeit = df_arbeitszeit[
            df_arbeitszeit["Überstunden Dezimal"].notna() &
            (df_arbeitszeit["Überstunden Dezimal"] != 0)
        ]

        # 3️⃣ Lohnart zuweisen
        df_arbeitszeit["Lohnart"] = np.where(
            df_arbeitszeit["Überstunden Dezimal"] < 0,
            8500,   # Überstunden
            8501    # Minusstunden
        )
        df_arbeitszeit["Wert"] = df_arbeitszeit["Überstunden Dezimal"]

        return df_arbeitszeit[["Mandant", "Pers.-Nr.", "Lohnart", "Wert"]]

def convert_to_numeric(col, df):
    assert col in df.columns, f"Spalte '{col}' nicht gefunden. Verfügbare Spalten: {list(df.columns)}"

    # --- Rohwerte in String konvertieren und säubern ---
    s = df[col].astype(str)

    # Unicode-Minus (−) -> normales Minus (-)
    s = s.str.replace("−", "-", regex=False)

    # Tausendertrennzeichen entfernen (Punkt / Leerzeichen / schmale Leerzeichen)
    s = s.str.replace(r"[.\s\u202F\u00A0]", "", regex=True)

    # deutsches Komma in Punkt wandeln
    s = s.str.replace(",", ".", regex=False)

    # Nur erlaubte Zeichen behalten (Ziffern, +, -, .)
    s = s.str.replace(r"[^0-9+\-\.]", "", regex=True)

    # --- In Zahl umwandeln ---
    df[col] = pd.to_numeric(s, errors="coerce").astype("Float64")


def get_datev_datei(df, mandantennummer, abrechnungsmonat):
    data = [
        [BERATERNUMMER, mandantennummer, abrechnungsmonat],
    ]
    df_header = pd.DataFrame(data, columns=["Pers.-Nr.", "Lohnart", "Wert"])

    # --- df_arbeitszeit muss die gleichen Spalten haben ---
    # Falls Spalten anders heißen, hier anpassen!
    df = df[df["Mandant"] == mandantennummer]

    df = df[["Pers.-Nr.", "Lohnart", "Wert"]]
    df["Wert"] = (
    pd.to_numeric(df["Wert"], errors="coerce")
        .map(lambda x: f"{x:.2f}".replace(".", ","))
    )
    # --- Zusammenführen ---
    df_final = pd.concat([df_header, df], ignore_index=True)
    return df_final


def show_datev_download(df_datev, name, firma):
    csv_bytes = build_datev_csv_bytes(df_datev)

    st.download_button(
        label=f"📥 Datei für {firma} herunterladen",
        data=csv_bytes,
        file_name=name,
        mime="text/csv",
        width="stretch"
    )

def build_datev_csv_bytes(df_datev: pd.DataFrame) -> bytes:
    """
    Erwartet DataFrame mit Spalten:
    - 'Personalnummer'
    - 'Lohnartennummer'
    - 'Wert'
    Gibt cp1252-kodierte CSV-Bytes zurück (Semikolon, kein Header, CRLF).
    """
    csv_str = df_datev.to_csv(
        sep=";",
        index=False,
        header=False,
        lineterminator="\r\n",

    )
    return csv_str.encode("cp1252", errors="replace")



