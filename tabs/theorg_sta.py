import datetime as dt
import hashlib
import io
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st


REQUIRED_COLUMNS = {"Umsatz", "Belegfeld 1", "Datum"}


def _find_header_row(raw: pd.DataFrame) -> int:
    for index, row in raw.head(30).iterrows():
        values = {str(value).strip() for value in row if not pd.isna(value)}
        if REQUIRED_COLUMNS.issubset(values):
            return index
    raise ValueError(
        "Die Kopfzeile wurde nicht gefunden. Benötigt werden mindestens die "
        "Spalten Umsatz, Belegfeld 1 und Datum."
    )


def _decimal(value) -> Decimal | None:
    if pd.isna(value):
        return None
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _text(value) -> str:
    if pd.isna(value):
        return ""
    value = str(value).strip()
    return value[:-2] if re.fullmatch(r"\d+\.0", value) else value


def read_bank_bookings(uploaded_file) -> pd.DataFrame:
    content = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    raw = pd.read_excel(io.BytesIO(content), header=None)
    header_row = _find_header_row(raw)
    positions = {
        str(value).strip(): position
        for position, value in enumerate(raw.iloc[header_row])
        if not pd.isna(value)
    }

    optional_columns = ["Nr.", "S/H", "Buchungstext"]
    result = pd.DataFrame()
    for column in [*REQUIRED_COLUMNS, *optional_columns]:
        if column in positions:
            result[column] = raw.iloc[header_row + 1 :, positions[column]].reset_index(drop=True)

    result["Datum"] = pd.to_datetime(result["Datum"], errors="coerce", dayfirst=True)
    result["Betrag"] = result["Umsatz"].map(_decimal)
    result["Rechnungsnummer"] = result["Belegfeld 1"].map(_text)
    result = result.dropna(subset=["Datum", "Betrag"])
    result = result[result["Rechnungsnummer"] != ""].copy()
    result = result[result["Betrag"] != Decimal("0.00")].copy()

    if "S/H" in result.columns:
        debit_credit = result["S/H"].map(_text).str.upper()
    else:
        debit_credit = pd.Series("", index=result.index)
    result["Richtung"] = "Gutschrift"
    result.loc[
        debit_credit.eq("H") | ((debit_credit == "") & (result["Betrag"] < 0)),
        "Richtung",
    ] = "Belastung"
    result["Betrag"] = result["Betrag"].map(abs)

    if result.empty:
        raise ValueError("Die Datei enthält keine verwendbaren Bankbuchungen.")
    return result.sort_values(["Datum", "Rechnungsnummer"]).reset_index(drop=True)


def _mt940_text(value, max_length: int) -> str:
    value = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode()
    value = re.sub(r"[^A-Za-z0-9 /\-?:().,'+]", " ", value.upper())
    return re.sub(r"\s+", " ", value).strip()[:max_length]


def _amount(value: Decimal) -> str:
    return f"{value.copy_abs():.2f}".replace(".", ",")


def _balance(value: Decimal, date: dt.date) -> str:
    direction = "C" if value >= 0 else "D"
    return f"{direction}{date:%y%m%d}EUR{_amount(value)}"


def _wrap_field(tag: str, content: str) -> list[str]:
    prefix = f":{tag}:"
    lines = [prefix + content[: 65 - len(prefix)]]
    remainder = content[65 - len(prefix) :]
    while remainder:
        lines.append(remainder[:65])
        remainder = remainder[65:]
    return lines


def automatic_statement_number(bookings: pd.DataFrame) -> int:
    parts = []
    for _, row in bookings.sort_values(["Datum", "Rechnungsnummer"]).iterrows():
        amount = _decimal(row["Betrag"])
        parts.append(
            "|".join(
                [
                    row["Datum"].strftime("%Y%m%d"),
                    _text(row["Rechnungsnummer"]),
                    _amount(amount or Decimal("0.00")),
                    _text(row["Richtung"]),
                ]
            )
        )
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).digest()
    return 10000 + int.from_bytes(digest[:8], "big") % 90000


def build_mt940_bytes(
    bookings: pd.DataFrame,
    account_identification: str,
    opening_balance=Decimal("0.00"),
    statement_number: int | None = None,
) -> bytes:
    account = re.sub(r"\s+", "", _text(account_identification)).upper()
    if not account:
        raise ValueError("Bitte gib die IBAN oder die Kontoidentifikation an.")
    if len(account) > 35 or not re.fullmatch(r"[A-Z0-9/.-]+", account):
        raise ValueError("Die Kontoidentifikation ist für MT940 ungültig oder zu lang.")

    opening = _decimal(opening_balance)
    if opening is None:
        raise ValueError("Der Anfangssaldo ist ungültig.")
    first_date = bookings["Datum"].min().date()
    last_date = bookings["Datum"].max().date()
    if statement_number is None:
        statement_number = automatic_statement_number(bookings)
    if not 1 <= int(statement_number) <= 99999:
        raise ValueError("Die Auszugsnummer muss zwischen 1 und 99999 liegen.")
    reference = f"THEORG{last_date:%y%m%d}"[:16]
    lines = [
        f":20:{reference}",
        f":25:{account}",
        f":28C:{int(statement_number):05d}/001",
        f":60F:{_balance(opening, first_date)}",
    ]
    movement = Decimal("0.00")

    for sequence, (_, row) in enumerate(bookings.iterrows(), start=1):
        date = row["Datum"].date()
        amount = _decimal(row["Betrag"])
        if amount is None:
            continue
        is_credit = row["Richtung"] == "Gutschrift"
        direction = "C" if is_credit else "D"
        movement += amount if is_credit else -amount
        invoice = _mt940_text(row["Rechnungsnummer"], 36)
        customer_reference = _mt940_text(invoice, 16) or "NONREF"
        source_number = _text(row.get("Nr.", ""))
        bank_reference = _mt940_text(source_number, 16) or f"{sequence:08d}"
        lines.append(
            f":61:{date:%y%m%d}{date:%m%d}{direction}{_amount(amount)}"
            f"NTRF{customer_reference}//{bank_reference}"
        )
        gvc = "051" if is_credit else "020"
        booking_label = "UEBERWEISUNGSGUTSCHRIFT" if is_credit else "UEBERWEISUNGSAUFTRAG"
        purpose = f"{gvc}?00{booking_label}?20RECHNUNG {invoice}"
        booking_text = _mt940_text(row.get("Buchungstext", ""), 60)
        if booking_text:
            purpose += f"?21{booking_text}"
        lines.extend(_wrap_field("86", purpose))

    lines.extend([f":62F:{_balance(opening + movement, last_date)}", "-"])
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


def show_tab_theorg_sta():
    st.header("THEORG-STA-Export")
    st.info(
        "Erstellt aus einer DATEV-Bankbuchungsliste eine MT940-Datei mit der "
        "Endung .sta. THEORG kann daraus Zahlungseingänge anhand der "
        "Rechnungsnummer im Verwendungszweck zuordnen."
    )
    uploaded_file = st.file_uploader(
        "DATEV-Bankbuchungsliste als Excel-Datei", type=["xlsx"], key="theorg_bank_file"
    )
    if uploaded_file is None:
        st.info("⬆️ Bitte lade eine Excel-Datei hoch.")
        return

    try:
        bookings = read_bank_bookings(uploaded_file)
    except Exception as error:
        st.error(f"❌ Die Bankbuchungen konnten nicht gelesen werden: {error}")
        return

    st.subheader("Erkannte Bankbuchungen")
    preview = bookings[["Datum", "Rechnungsnummer", "Betrag", "Richtung"]].copy()
    preview["Betrag"] = preview["Betrag"].map(float)
    st.dataframe(preview, hide_index=True, width="stretch")
    credit_total = sum(
        bookings.loc[bookings["Richtung"] == "Gutschrift", "Betrag"], Decimal("0.00")
    )
    debit_total = sum(
        bookings.loc[bookings["Richtung"] == "Belastung", "Betrag"], Decimal("0.00")
    )
    st.write(
        f"Erkannt: **{len(bookings)} Buchungen**, "
        f"Gutschriften **{float(credit_total):,.2f} €**, "
        f"Belastungen **{float(debit_total):,.2f} €**."
    )

    st.subheader("Angabe für den MT940-Kontoauszug")
    account = st.text_input(
        "IBAN oder Kontoidentifikation",
        help="Pflichtfeld :25: des MT940-Formats. Die DATEV-Datei enthält diese Angabe nicht.",
    )
    statement_number = automatic_statement_number(bookings)
    st.caption(
        f"Auszugsnummer **{statement_number:05d}** und technischer "
        "Anfangssaldo **0,00 €** werden automatisch gesetzt. Der Endsaldo wird "
        "aus den Buchungen berechnet."
    )

    if not account:
        st.warning("Bitte ergänze die IBAN oder Kontoidentifikation für den Export.")
        return

    try:
        sta_bytes = build_mt940_bytes(bookings, account)
    except Exception as error:
        st.error(f"❌ Die STA-Datei konnte nicht erstellt werden: {error}")
        return

    date_from = bookings["Datum"].min().strftime("%Y%m%d")
    date_to = bookings["Datum"].max().strftime("%Y%m%d")
    st.download_button(
        "📥 THEORG-STA-Datei herunterladen",
        data=sta_bytes,
        file_name=f"THEORG_{date_from}_{date_to}.sta",
        mime="application/octet-stream",
        type="primary",
    )
