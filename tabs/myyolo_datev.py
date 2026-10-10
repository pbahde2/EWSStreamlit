import datetime as dt

import pandas as pd
import streamlit as st

from tabs.wordpress_datev import DATEV_COLUMNS, _document_number, _serialize, dataframe_excel_bytes


DATEV_ADVISER_NUMBER = 446024
DATEV_CLIENT_NUMBER = 14117
DATEV_ACCOUNT_LENGTH = 4
DATEV_ACCOUNT_FRAMEWORK = "03"
DATEV_INITIALS = "WD"
DEBITOR_ACCOUNT = "10129"
REVENUE_ACCOUNT = "8106"

LOCATION_CONFIG = {
    "Borken": {"KOST1": "21", "Belegpräfix": "6861"},
    "Raesfeld": {"KOST1": "22", "Belegpräfix": "6862"},
    "Reken": {"KOST1": "23", "Belegpräfix": "6860"},
    "Vreden": {"KOST1": "26", "Belegpräfix": "7309"},
    "Epe": {"KOST1": "27", "Belegpräfix": "7632"},
}

SOURCE_COLUMNS = ["Nr", "Datum", "Beleg", "Nachname", "Vorname", "Betrag"]
INVOICE_TYPES = ["T-Rena", "RV-Fit"]


def read_myyolo_excel(uploaded_file) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(uploaded_file, header=None)
    if raw.shape[1] != len(SOURCE_COLUMNS):
        raise ValueError(
            f"Erwartet werden genau {len(SOURCE_COLUMNS)} Spalten, gefunden wurden {raw.shape[1]}."
        )

    data = raw.copy()
    data.columns = SOURCE_COLUMNS
    data["Datum"] = pd.to_datetime(data["Datum"], errors="coerce", dayfirst=True)
    data["Betrag"] = pd.to_numeric(data["Betrag"], errors="coerce")
    data["Beleg"] = data["Beleg"].astype("string").str.strip()
    data["Nachname"] = data["Nachname"].astype("string").str.strip()
    data["Vorname"] = data["Vorname"].astype("string").str.strip()

    invalid_mask = (
        data["Datum"].isna()
        | data["Betrag"].isna()
        | data["Beleg"].isna()
        | data["Beleg"].eq("")
    )
    invalid = data[invalid_mask].copy()
    valid = data[~invalid_mask & data["Betrag"].ne(0)].copy()
    return valid, invalid


def build_document_number(prefix: str, receipt, invoice_type: str = "T-Rena") -> str:
    receipt = _document_number(receipt)
    rv_prefix = "RV" if invoice_type == "RV-Fit" else ""
    return _document_number(f"{rv_prefix}{prefix}-{receipt}")


def build_booking_list(
    data: pd.DataFrame, location: str, invoice_type: str = "T-Rena"
) -> pd.DataFrame:
    config = LOCATION_CONFIG[location]
    result = data.copy()
    result["Standort"] = location
    result["Konto"] = DEBITOR_ACCOUNT
    result["Gegenkonto"] = REVENUE_ACCOUNT
    result["KOST1"] = config["KOST1"]
    result["Belegfeld 1"] = result["Beleg"].map(
        lambda value: build_document_number(
            config["Belegpräfix"], value, invoice_type
        )
    )
    return result[
        [
            "Nr",
            "Datum",
            "Beleg",
            "Belegfeld 1",
            "Nachname",
            "Vorname",
            "Betrag",
            "Standort",
            "Konto",
            "Gegenkonto",
            "KOST1",
        ]
    ].sort_values(["Datum", "Nr"])


def build_myyolo_datev_bytes(
    data: pd.DataFrame,
    location: str,
    created_at: dt.datetime | None = None,
    invoice_type: str = "T-Rena",
) -> bytes:
    if data.empty:
        raise ValueError("Keine gültigen Buchungen für den Export vorhanden.")
    years = sorted(data["Datum"].dt.year.unique())
    if len(years) != 1:
        raise ValueError(
            "Eine DATEV-Datei kann nur Buchungen aus einem Kalenderjahr enthalten. "
            "Bitte teile die Excel-Datei nach Jahren auf."
        )

    created_at = created_at or dt.datetime.now()
    date_from = data["Datum"].min().date()
    date_to = data["Datum"].max().date()
    fiscal_year_start = dt.date(years[0], 1, 1)
    location_config = LOCATION_CONFIG[location]
    header = [
        "EXTF",
        700,
        21,
        "Buchungsstapel",
        13,
        created_at.strftime("%Y%m%d%H%M%S") + f"{created_at.microsecond // 1000:03d}",
        "",
        "RE",
        "MyYOLO",
        "",
        DATEV_ADVISER_NUMBER,
        DATEV_CLIENT_NUMBER,
        fiscal_year_start.strftime("%Y%m%d"),
        DATEV_ACCOUNT_LENGTH,
        date_from.strftime("%Y%m%d"),
        date_to.strftime("%Y%m%d"),
        f"MyYOLO {location}"[:30],
        DATEV_INITIALS,
        1,
        0,
        0,
        "EUR",
        "",
        "",
        "",
        "",
        DATEV_ACCOUNT_FRAMEWORK,
        "",
        "",
        "",
        "MyYOLO-Datev",
    ]
    lines = [
        _serialize(header, {0, 3, 7, 8, 9, 16, 17, 21, 23, 26, 29, 30}),
        _serialize(DATEV_COLUMNS, range(len(DATEV_COLUMNS))),
    ]

    for _, row in data.sort_values(["Datum", "Nr"]).iterrows():
        amount = float(row["Betrag"])
        fields = [""] * len(DATEV_COLUMNS)
        fields[0] = f"{abs(amount):.2f}".replace(".", ",")
        fields[1] = "S" if amount > 0 else "H"
        fields[6] = DEBITOR_ACCOUNT
        fields[7] = REVENUE_ACCOUNT
        fields[9] = row["Datum"].strftime("%d%m")
        fields[10] = build_document_number(
            location_config["Belegpräfix"], row["Beleg"], invoice_type
        )
        booking_text = f'{row["Nachname"]} {row["Vorname"]}'.strip()
        fields[13] = booking_text[:60]
        fields[36] = location_config["KOST1"]
        lines.append(_serialize(fields, {1, 10, 13, 36}))

    return ("\r\n".join(lines) + "\r\n").encode("cp1252", errors="replace")


def show_tab_myyolo_datev():
    st.header("MyYOLO-DATEV-Export")
    st.info(
        "Die Anwendung verarbeitet immer alle Buchungen der hochgeladenen Excel-Datei – "
        "unabhängig vom Monat. Die dritte Spalte wird zusammen mit dem Standortpräfix "
        "als DATEV-Belegfeld 1 verwendet."
    )

    invoice_type = st.selectbox(
        "Rechnungsart", INVOICE_TYPES, key="myyolo_invoice_type"
    )
    location = st.selectbox("Standort", list(LOCATION_CONFIG), key="myyolo_location")
    location_config = LOCATION_CONFIG[location]
    st.success(
        f"Automatische Zuordnung für **{location}**: Konto {DEBITOR_ACCOUNT}, "
        f"Gegenkonto {REVENUE_ACCOUNT}, KOST1 {location_config['KOST1']}, "
        f"Belegpräfix {location_config['Belegpräfix']}."
    )

    uploaded_file = st.file_uploader(
        "MyYOLO-Datei hochladen", type=["xlsx"], key="myyolo_datev_file"
    )
    if uploaded_file is None:
        st.info("⬆️ Bitte lade eine Excel-Datei hoch.")
        return

    try:
        bookings, invalid = read_myyolo_excel(uploaded_file)
    except Exception as error:
        st.error(f"❌ Die Excel-Datei konnte nicht verarbeitet werden: {error}")
        return

    if bookings.empty:
        st.error("❌ Die Datei enthält keine gültigen Buchungen.")
        return

    booking_list = build_booking_list(bookings, location, invoice_type)
    st.subheader("Alle Buchungen")
    st.write(
        f"**{len(booking_list)} Buchungen** vom {bookings['Datum'].min():%d.%m.%Y} "
        f"bis {bookings['Datum'].max():%d.%m.%Y}, Gesamtsumme: "
        f"**{bookings['Betrag'].sum():,.2f} €**"
    )
    st.dataframe(booking_list, hide_index=True, width="stretch")
    st.download_button(
        "📥 Buchungsliste als Excel herunterladen",
        data=dataframe_excel_bytes(booking_list, "Buchungen"),
        file_name=f"MyYOLO_Buchungen_{location}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    try:
        datev_bytes = build_myyolo_datev_bytes(
            bookings, location, invoice_type=invoice_type
        )
    except Exception as error:
        st.error(f"❌ DATEV-Datei konnte nicht erstellt werden: {error}")
    else:
        st.download_button(
            "📥 DATEV-Buchungsstapel herunterladen",
            data=datev_bytes,
            file_name=f"EXTF_Buchungsstapel_MyYOLO_{location}.csv",
            mime="text/csv",
            type="primary",
        )

    st.subheader("Nicht verarbeitete Zeilen")
    if invalid.empty:
        st.success("Alle Zeilen der Excel-Datei konnten verarbeitet werden.")
    else:
        st.warning(
            f"{len(invalid)} Zeile(n) wurden wegen eines fehlenden Datums, Betrags oder Belegs ignoriert."
        )
        st.dataframe(invalid, hide_index=True, width="stretch")
