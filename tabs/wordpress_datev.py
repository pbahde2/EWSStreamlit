import datetime as dt
import io
import re
import unicodedata

import pandas as pd
import streamlit as st


REQUIRED_COLUMNS = {
    "Order Date",
    "Category",
    "Item Cost (inc. tax)",
    "Payment Method",
    "Transaction ID",
}

# Feste DATEV-Stammdaten. Diese Werte werden nicht im UI konfiguriert.
DATEV_ADVISER_NUMBER = 446024
DATEV_CLIENT_NUMBER = 14118
DATEV_ACCOUNT_LENGTH = 4
DATEV_ACCOUNT_FRAMEWORK = "03"
DATEV_INITIALS = "WD"

# Feldnamen des DATEV-Buchungsstapels, Formatversion 13.
DATEV_COLUMNS = [
    "Umsatz (ohne Soll/Haben-Kz)",
    "Soll/Haben-Kennzeichen",
    "WKZ Umsatz",
    "Kurs",
    "Basis-Umsatz",
    "WKZ Basis-Umsatz",
    "Konto",
    "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel",
    "Belegdatum",
    "Belegfeld 1",
    "Belegfeld 2",
    "Skonto",
    "Buchungstext",
    "Postensperre",
    "Diverse Adressnummer",
    "Geschäftspartnerbank",
    "Sachverhalt",
    "Zinssperre",
    "Beleglink",
]
for number in range(1, 9):
    DATEV_COLUMNS.extend([f"Beleginfo - Art {number}", f"Beleginfo - Inhalt {number}"])
DATEV_COLUMNS.extend(
    [
        "KOST1 - Kostenstelle",
        "KOST2 - Kostenstelle",
        "KOST-Menge",
        "EU-Mitgliedstaat u. UStID (Bestimmung)",
        "EU-Steuersatz (Bestimmung)",
        "Abw. Versteuerungsart",
        "Sachverhalt L+L",
        "Funktionsergänzung L+L",
        "BU 49 Hauptfunktionstyp",
        "BU 49 Hauptfunktionsnummer",
        "BU 49 Funktionsergänzung",
    ]
)
for number in range(1, 21):
    DATEV_COLUMNS.extend(
        [f"Zusatzinformation - Art {number}", f"Zusatzinformation - Inhalt {number}"]
    )
DATEV_COLUMNS.extend(
    [
        "Stück",
        "Gewicht",
        "Zahlweise",
        "Forderungsart",
        "Veranlagungsjahr",
        "Zugeordnete Fälligkeit",
        "Skontotyp",
        "Auftragsnummer",
        "Buchungstyp",
        "USt-Schlüssel (Anzahlungen)",
        "EU-Mitgliedstaat (Anzahlungen)",
        "Sachverhalt L+L (Anzahlungen)",
        "EU-Steuersatz (Anzahlungen)",
        "Erlöskonto (Anzahlungen)",
        "Herkunft-Kz",
        "Leerfeld",
        "KOST-Datum",
        "SEPA-Mandatsreferenz",
        "Skontosperre",
        "Gesellschaftername",
        "Beteiligtennummer",
        "Identifikationsnummer",
        "Zeichnernummer",
        "Postensperre bis",
        "Bezeichnung SoBil-Sachverhalt",
        "Kennzeichen SoBil-Buchung",
        "Festschreibung",
        "Leistungsdatum",
        "Datum Zuord. Steuerperiode",
        "Fälligkeit",
        "Generalumkehr",
        "Steuersatz",
        "Land",
        "Abrechnungsreferenz",
        "BVV-Position (Betriebsvermögensvergleich)",
        "EU-Mitgliedstaat u. UStID (Ursprung)",
        "EU-Steuersatz (Ursprung)",
        "Abw. Skontokonto",
    ]
)


def _quote(value) -> str:
    return f'"{str(value).replace(chr(34), chr(34) * 2)}"'


def _serialize(fields, quoted_indexes=()) -> str:
    quoted_indexes = set(quoted_indexes)
    return ";".join(
        _quote(value) if index in quoted_indexes else str(value)
        for index, value in enumerate(fields)
    )


def _number(value) -> float:
    if pd.isna(value):
        return float("nan")
    if isinstance(value, str):
        value = value.strip().replace("\u00a0", "").replace(" ", "")
        if "," in value:
            value = value.replace(".", "").replace(",", ".")
    return pd.to_numeric(value, errors="coerce")


def _account(value) -> str:
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if re.fullmatch(r"\d+\.0", value):
        value = value[:-2]
    return value


def _bu_key(value) -> str:
    value = _account(value)
    return value.zfill(4) if value else ""


def _document_number(value) -> str:
    value = "" if pd.isna(value) else str(value).strip()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_$&%*+\-/]", "", value)[:36]


def _booking_text(row) -> str:
    product_value = row.get("Product Name", "")
    category_value = row.get("Category", "")
    product = "" if pd.isna(product_value) else str(product_value).strip()
    category = "" if pd.isna(category_value) else str(category_value).strip()
    return (product or category or "Wordpress-Bestellung")[:60]


def build_config(categories, payment_methods) -> pd.DataFrame:
    rows = [
        {
            "Typ": "Kategorie",
            "Wert": value,
            "Konto": "",
            "BU-Schlüssel": "",
            "KOST1": "",
        }
        for value in sorted(set(categories))
    ]
    rows.extend(
        {
            "Typ": "Zahlungsart",
            "Wert": value,
            "Konto": "",
            "BU-Schlüssel": "",
            "KOST1": "",
        }
        for value in sorted(set(payment_methods))
    )
    return pd.DataFrame(
        rows, columns=["Typ", "Wert", "Konto", "BU-Schlüssel", "KOST1"]
    )


def merge_config(base: pd.DataFrame, imported: pd.DataFrame) -> pd.DataFrame:
    required = {"Typ", "Wert", "Konto", "BU-Schlüssel"}
    if not required.issubset(imported.columns):
        raise ValueError("Die Konfiguration benötigt die Spalten: " + ", ".join(sorted(required)))
    if "KOST1" not in imported.columns:
        imported["KOST1"] = ""
    imported = imported[["Typ", "Wert", "Konto", "BU-Schlüssel", "KOST1"]].copy()
    imported["Typ"] = imported["Typ"].astype(str).str.strip()
    imported["Wert"] = imported["Wert"].astype(str).str.strip()
    imported = imported.drop_duplicates(["Typ", "Wert"], keep="last")
    result = base.drop(columns=["Konto", "BU-Schlüssel", "KOST1"]).merge(
        imported, on=["Typ", "Wert"], how="left"
    )
    return result[["Typ", "Wert", "Konto", "BU-Schlüssel", "KOST1"]].fillna("")


def config_csv_bytes(config: pd.DataFrame) -> bytes:
    return config.to_csv(index=False, sep=";", lineterminator="\r\n").encode("utf-8-sig")


def config_excel_bytes(config: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        config.to_excel(writer, index=False, sheet_name="Kontenzuordnung")
    return output.getvalue()


def dataframe_excel_bytes(data: pd.DataFrame, sheet_name: str) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        data.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()


def _read_wordpress_orders(uploaded_file) -> pd.DataFrame:
    # Transaction IDs can consist only of digits. Without an explicit text dtype,
    # pandas interprets the complete column as numbers and drops leading zeroes.
    return pd.read_excel(uploaded_file, dtype={"Transaction ID": "string"})


def build_complete_booking_list(
    orders: pd.DataFrame, config: pd.DataFrame
) -> pd.DataFrame:
    category_config = (
        config[config["Typ"] == "Kategorie"]
        .set_index("Wert")[["Konto", "BU-Schlüssel", "KOST1"]]
        .rename(columns={"Konto": "Erlöskonto"})
    )
    payment_config = (
        config[config["Typ"] == "Zahlungsart"]
        .set_index("Wert")[["Konto"]]
        .rename(columns={"Konto": "Geld-/Verrechnungskonto"})
    )
    result = orders.copy()
    result = result.join(category_config, on="Category")
    result = result.join(payment_config, on="Payment Method")
    preferred_columns = [
        "Order Date",
        "Order Number",
        "Order ID",
        "Transaction ID",
        "Product Name",
        "Category",
        "Payment Method",
        "Item Cost (inc. tax)",
        "Erlöskonto",
        "BU-Schlüssel",
        "KOST1",
        "Geld-/Verrechnungskonto",
    ]
    available_columns = [column for column in preferred_columns if column in result.columns]
    return result[available_columns].sort_values("Order Date").reset_index(drop=True)


def build_incomplete_category_list(
    excluded_orders: pd.DataFrame, config: pd.DataFrame
) -> pd.DataFrame:
    columns = [
        "Category",
        "Betroffene Buchungen",
        "Betrag",
        "Fehlende Informationen",
        "Erlöskonto",
        "BU-Schlüssel",
        "KOST1",
    ]
    if excluded_orders.empty:
        return pd.DataFrame(columns=columns)

    result = (
        excluded_orders.groupby("Category", as_index=False)
        .agg(
            **{
                "Betroffene Buchungen": ("_amount", "size"),
                "Betrag": ("_amount", "sum"),
                "Fehlende Informationen": (
                    "Grund",
                    lambda values: "; ".join(sorted(set(values))),
                ),
            }
        )
        .sort_values("Category")
    )
    category_config = (
        config[config["Typ"] == "Kategorie"]
        .set_index("Wert")[["Konto", "BU-Schlüssel", "KOST1"]]
        .rename(columns={"Konto": "Erlöskonto"})
    )
    result = result.join(category_config, on="Category")
    return result[columns]


def validate_config(config: pd.DataFrame, account_length: int) -> list[str]:
    errors = []
    for _, row in config.iterrows():
        account = _account(row["Konto"])
        bu_key = _bu_key(row["BU-Schlüssel"])
        label = f'{row["Typ"]} „{row["Wert"]}“'
        if not re.fullmatch(r"[1-9]\d{0,8}", account):
            errors.append(f"{label}: Konto fehlt oder ist ungültig.")
        elif len(account) not in (account_length, account_length + 1):
            errors.append(
                f"{label}: Konto muss {account_length} Stellen haben "
                f"({account_length + 1} nur für Personenkonten)."
            )
        if bu_key and not re.fullmatch(r"\d{4}", bu_key):
            errors.append(f"{label}: BU-Schlüssel muss numerisch und maximal vierstellig sein.")
        if row["Typ"] == "Kategorie":
            kost1 = "" if pd.isna(row["KOST1"]) else str(row["KOST1"]).strip()
            if not kost1:
                errors.append(f"{label}: KOST1 fehlt.")
            elif not re.fullmatch(r"[\w ]{1,36}", kost1):
                errors.append(
                    f"{label}: KOST1 darf maximal 36 Zeichen sowie nur Buchstaben, "
                    "Ziffern, Leerzeichen und Unterstriche enthalten."
                )
    return errors


def split_exportable_orders(
    orders: pd.DataFrame, config: pd.DataFrame, account_length: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trennt Buchungen anhand der vollständigen Kontenzuordnung."""
    category_config = config[config["Typ"] == "Kategorie"].set_index("Wert")
    payment_config = config[config["Typ"] == "Zahlungsart"].set_index("Wert")
    included_indexes = []
    excluded_indexes = []
    reasons = []

    def mapping_error(mapping: pd.DataFrame, key: str, with_bu_key: bool) -> str | None:
        if key not in mapping.index:
            return "keine Zuordnung vorhanden"
        mapped = mapping.loc[key]
        account = _account(mapped["Konto"])
        if not re.fullmatch(r"[1-9]\d{0,8}", account):
            return "Konto fehlt oder ist ungültig"
        if len(account) not in (account_length, account_length + 1):
            return f"Konto hat nicht {account_length} Stellen"
        if with_bu_key:
            bu_key = _bu_key(mapped["BU-Schlüssel"])
            if bu_key and not re.fullmatch(r"\d{4}", bu_key):
                return "BU-Schlüssel ist ungültig"
            kost1 = "" if pd.isna(mapped["KOST1"]) else str(mapped["KOST1"]).strip()
            if not kost1:
                return "KOST1 fehlt"
            if not re.fullmatch(r"[\w ]{1,36}", kost1):
                return "KOST1 enthält ungültige Zeichen oder ist zu lang"
        return None

    for index, row in orders.iterrows():
        category = str(row["Category"]).strip()
        payment_method = str(row["Payment Method"]).strip()
        row_reasons = []
        category_error = mapping_error(category_config, category, True)
        payment_error = mapping_error(payment_config, payment_method, False)
        if category_error:
            row_reasons.append(f"Kategorie „{category}“: {category_error}")
        if payment_error:
            row_reasons.append(f"Zahlungsart „{payment_method}“: {payment_error}")

        if row_reasons:
            excluded_indexes.append(index)
            reasons.append("; ".join(row_reasons))
        else:
            included_indexes.append(index)

    included = orders.loc[included_indexes].copy()
    excluded = orders.loc[excluded_indexes].copy()
    excluded["Grund"] = reasons
    return included, excluded


def build_datev_bytes(
    orders: pd.DataFrame,
    config: pd.DataFrame,
    adviser_number: int,
    client_number: int,
    fiscal_year_start: dt.date,
    account_length: int,
    account_framework: str,
    initials: str,
    created_at: dt.datetime | None = None,
) -> bytes:
    if orders.empty:
        raise ValueError("Keine Buchungen für den Export vorhanden.")

    created_at = created_at or dt.datetime.now()
    category_config = config[config["Typ"] == "Kategorie"].set_index("Wert")
    payment_config = config[config["Typ"] == "Zahlungsart"].set_index("Wert")
    date_from = orders["Order Date"].min().date()
    date_to = orders["Order Date"].max().date()

    header = [
        "EXTF",
        700,
        21,
        "Buchungsstapel",
        13,
        created_at.strftime("%Y%m%d%H%M%S") + f"{created_at.microsecond // 1000:03d}",
        "",
        "RE",
        "Wordpress",
        "",
        adviser_number,
        client_number,
        fiscal_year_start.strftime("%Y%m%d"),
        account_length,
        date_from.strftime("%Y%m%d"),
        date_to.strftime("%Y%m%d"),
        f"Wordpress {date_from:%m/%Y}",
        initials.upper(),
        1,
        0,
        0,
        "EUR",
        "",
        "",
        "",
        "",
        account_framework,
        "",
        "",
        "",
        "Wordpress-Datev",
    ]
    lines = [
        _serialize(header, {0, 3, 7, 8, 9, 16, 17, 21, 23, 26, 29, 30}),
        _serialize(DATEV_COLUMNS, range(len(DATEV_COLUMNS))),
    ]

    for _, row in orders.iterrows():
        amount = float(row["_amount"])
        category = str(row["Category"]).strip()
        payment_method = str(row["Payment Method"]).strip()
        fields = [""] * len(DATEV_COLUMNS)
        fields[0] = f"{abs(amount):.2f}".replace(".", ",")
        fields[1] = "S" if amount > 0 else "H"
        fields[6] = _account(payment_config.loc[payment_method, "Konto"])
        fields[7] = _account(category_config.loc[category, "Konto"])
        fields[8] = _bu_key(category_config.loc[category, "BU-Schlüssel"])
        fields[9] = row["Order Date"].strftime("%d%m")
        fields[10] = _document_number(row["Transaction ID"])
        fields[13] = _booking_text(row)
        fields[36] = str(category_config.loc[category, "KOST1"]).strip()
        lines.append(_serialize(fields, {1, 8, 10, 13, 36, 94}))

    return ("\r\n".join(lines) + "\r\n").encode("cp1252", errors="replace")


def _read_imported_config(uploaded_file) -> pd.DataFrame:
    content = uploaded_file.getvalue()
    if uploaded_file.name.lower().endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
    try:
        return pd.read_csv(io.BytesIO(content), sep=";", dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        return pd.read_csv(
            io.BytesIO(content), sep=";", dtype=str, keep_default_na=False, encoding="cp1252"
        )


def show_tab_wordpress_datev():
    st.header("Wordpress-DATEV-Export")
    st.info(
        "Lade den Wordpress-/WooCommerce-Excel-Export hoch. Danach ordnest du "
        "Kategorien den Erlöskonten und Zahlungsarten den Geld-/Verrechnungskonten zu."
    )
    uploaded_file = st.file_uploader(
        "Wordpress-Bestellungen als Excel-Datei", type=["xlsx"], key="wordpress_datev_orders"
    )
    if uploaded_file is None:
        st.info("⬆️ Bitte lade eine Excel-Datei hoch.")
        return

    try:
        orders = _read_wordpress_orders(uploaded_file)
    except Exception as error:
        st.error(f"❌ Die Excel-Datei konnte nicht gelesen werden: {error}")
        return

    missing = sorted(REQUIRED_COLUMNS - set(orders.columns))
    if missing:
        st.error("❌ Fehlende Spalten: " + ", ".join(missing))
        return

    orders = orders.copy()
    orders["Order Date"] = pd.to_datetime(orders["Order Date"], errors="coerce", dayfirst=True)
    orders["_amount"] = orders["Item Cost (inc. tax)"].map(_number)
    invalid_count = int((orders["Order Date"].isna() | orders["_amount"].isna()).sum())
    orders = orders.dropna(subset=["Order Date", "_amount", "Category", "Payment Method"])
    orders["Category"] = orders["Category"].astype(str).str.strip()
    orders["Payment Method"] = orders["Payment Method"].astype(str).str.strip()
    orders = orders[(orders["_amount"] != 0) & (orders["Category"] != "") & (orders["Payment Method"] != "")]
    if invalid_count:
        st.warning(f"{invalid_count} Zeile(n) ohne gültiges Datum oder Betrag wurden ignoriert.")
    if orders.empty:
        st.error("❌ Die Datei enthält keine exportierbaren Buchungen.")
        return

    orders["_period"] = orders["Order Date"].dt.to_period("M").astype(str)
    periods = sorted(orders["_period"].unique(), reverse=True)
    selected_period = st.selectbox("Buchungsmonat", periods, key="wordpress_datev_period")
    period_orders = orders[orders["_period"] == selected_period].copy()
    st.info(
        f"**Buchungsmonat {selected_period}:** Es werden nur Bestellungen mit einem "
        "Bestelldatum in diesem Monat berücksichtigt. DATEV erhält damit einen "
        "separaten Buchungsstapel für diese Abrechnungsperiode."
    )

    period_year = int(selected_period[:4])
    fiscal_year_start = dt.date(period_year, 1, 1)

    st.subheader("Kontenzuordnung")
    st.caption(
        "Kategorie: Erlöskonto (Gegenkonto), KOST1 und optionaler BU-Schlüssel. "
        "Zahlungsart: Geld-, Bank- oder Verrechnungskonto (Konto)."
    )
    base_config = build_config(period_orders["Category"], period_orders["Payment Method"])
    config_file = st.file_uploader(
        "Vorhandene Konfiguration laden (optional)",
        type=["csv", "xlsx"],
        key="wordpress_datev_config",
    )
    if config_file is not None:
        try:
            base_config = merge_config(base_config, _read_imported_config(config_file))
        except Exception as error:
            st.error(f"❌ Konfiguration konnte nicht gelesen werden: {error}")

    category_config = st.data_editor(
        base_config[base_config["Typ"] == "Kategorie"],
        hide_index=True,
        disabled=["Typ", "Wert"],
        width="stretch",
        key=f"wordpress_category_config_v2_{selected_period}",
        column_config={
            "Wert": st.column_config.TextColumn("Kategorie"),
            "Konto": st.column_config.TextColumn("Erlöskonto", required=True),
            "BU-Schlüssel": st.column_config.TextColumn("BU-Schlüssel (optional)"),
            "KOST1": st.column_config.TextColumn("KOST1 (Kostenstelle)", required=True),
        },
    )
    payment_config = st.data_editor(
        base_config[base_config["Typ"] == "Zahlungsart"],
        hide_index=True,
        disabled=["Typ", "Wert", "BU-Schlüssel", "KOST1"],
        width="stretch",
        key=f"wordpress_payment_config_v2_{selected_period}",
        column_config={
            "Wert": st.column_config.TextColumn("Zahlungsart"),
            "Konto": st.column_config.TextColumn("Geld-/Verrechnungskonto", required=True),
            "BU-Schlüssel": None,
            "KOST1": None,
        },
    )
    config = pd.concat([category_config, payment_config], ignore_index=True)

    config_col1, config_col2 = st.columns(2)
    with config_col1:
        st.download_button(
            "📥 Konfiguration als Excel speichern",
            data=config_excel_bytes(config),
            file_name="Wordpress_DATEV_Konfiguration.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with config_col2:
        st.download_button(
            "📥 Konfiguration als CSV speichern",
            data=config_csv_bytes(config),
            file_name="Wordpress_DATEV_Konfiguration.csv",
            mime="text/csv",
        )

    export_orders, excluded_orders = split_exportable_orders(
        period_orders, config, DATEV_ACCOUNT_LENGTH
    )
    complete_booking_list = build_complete_booking_list(export_orders, config)
    incomplete_category_list = build_incomplete_category_list(excluded_orders, config)

    preview = (
        period_orders.groupby(["Category", "Payment Method"], as_index=False)
        .agg(Buchungen=("_amount", "size"), Betrag=("_amount", "sum"))
        .sort_values(["Category", "Payment Method"])
    )
    st.subheader("Vorschau")
    st.dataframe(preview, hide_index=True, width="stretch")
    st.write(
        f"Im Monat gefunden: **{len(period_orders)} Buchungen**. Davon werden "
        f"**{len(export_orders)} Buchungen** mit insgesamt "
        f"**{export_orders['_amount'].sum():,.2f} €** exportiert."
    )
    st.download_button(
        "📥 Vollständige Buchungen als Excel herunterladen",
        data=dataframe_excel_bytes(complete_booking_list, "Vollständige Buchungen"),
        file_name=f"Vollstaendige_Buchungen_{selected_period}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if not export_orders.empty:
        try:
            datev_bytes = build_datev_bytes(
                export_orders,
                config,
                DATEV_ADVISER_NUMBER,
                DATEV_CLIENT_NUMBER,
                fiscal_year_start,
                DATEV_ACCOUNT_LENGTH,
                DATEV_ACCOUNT_FRAMEWORK,
                DATEV_INITIALS,
            )
        except Exception as error:
            st.error(f"❌ DATEV-Datei konnte nicht erstellt werden: {error}")
        else:
            st.success("✅ Die DATEV-Datei ist bereit.")
            st.download_button(
                "📥 DATEV-Buchungsstapel herunterladen",
                data=datev_bytes,
                file_name=f"EXTF_Buchungsstapel_Wordpress_{selected_period}.csv",
                mime="text/csv",
                type="primary",
            )
    else:
        st.warning(
            "Noch keine Buchung kann exportiert werden. Ergänze mindestens die "
            "benötigten Kategorie- und Zahlungsartkonten."
        )

    st.subheader("Kategorien mit fehlenden Informationen")
    if incomplete_category_list.empty:
        st.success("Alle Kategorien dieses Monats sind vollständig konfiguriert.")
    else:
        st.warning(
            f"Bei {len(incomplete_category_list)} Kategorie(n) fehlen Informationen. "
            f"Dadurch werden {len(excluded_orders)} Buchung(en) nicht exportiert."
        )
        st.dataframe(
            incomplete_category_list,
            hide_index=True,
            width="stretch",
        )
