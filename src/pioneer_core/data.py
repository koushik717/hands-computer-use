"""Synthetic teller data. Nothing here is real PII."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    member_id: str
    display_name: str
    status: str
    savings: str  # already formatted, e.g. "4250.17"
    checking: str
    member_since: str
    restricted: bool = False
    fraud_hold: bool = False
    slow: bool = False


MEMBERS: dict[str, Member] = {
    "12345": Member(
        member_id="12345",
        display_name="A. Patel",
        status="Active",
        savings="4250.17",
        checking="890.00",
        member_since="2014-03-12",
    ),
    "12346": Member(
        member_id="12346",
        display_name="R. Okonkwo",
        status="Active",
        savings="12000.00",
        checking="210.44",
        member_since="2018-11-02",
    ),
    "00001": Member(
        member_id="00001",
        display_name="[restricted]",
        status="Restricted",
        savings="0.00",
        checking="0.00",
        member_since="2009-01-01",
        restricted=True,
    ),
    "77777": Member(
        member_id="77777",
        display_name="M. Chen",
        status="Active",
        savings="640.02",
        checking="15.00",
        member_since="2021-07-19",
        fraud_hold=True,
    ),
    "88888": Member(
        member_id="88888",
        display_name="S. Alvarez",
        status="Active",
        savings="99.00",
        checking="12.00",
        member_since="2020-02-08",
        slow=True,
    ),
}


def format_usd(amount: str) -> str:
    whole, _, frac = amount.partition(".")
    frac = (frac + "00")[:2]
    grouped = f"{int(whole):,}"
    return f"${grouped}.{frac}"
