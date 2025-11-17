from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Committee:
    key: str
    name: str
    summary: str
    aliases: tuple[str, ...]


COMMITTEES: tuple[Committee, ...] = (
    Committee(
        key="sports",
        name="Sports Committee",
        summary="Leads athletics, intramurals, and campus spirit events.",
        aliases=("athletics", "sports committee"),
    ),
    Committee(
        key="social",
        name="Social Committee",
        summary="Plans mixers, welcome events, and cohort traditions.",
        aliases=("social committee",),
    ),
    Committee(
        key="cultural",
        name="Cultural Committee",
        summary="Celebrates heritage nights, arts showcases, and shared identities.",
        aliases=("culture", "cultral", "cultural committee"),
    ),
    Committee(
        key="science",
        name="Science Committee",
        summary="Hosts innovation labs, research spotlights, and STEM outreach.",
        aliases=("stem", "science committee"),
    ),
    Committee(
        key="art",
        name="Art Committee",
        summary="Curates galleries, performances, and creative workshops.",
        aliases=("arts", "art committee"),
    ),
)


def normalize_committee_key(raw: str) -> str:
    if raw is None:
        raw = ""
    token = raw.strip().lower()
    if token.startswith("/"):
        token = token.lstrip("/")
    if token.endswith("/"):
        token = token.rstrip("/")
    if token.endswith(".html"):
        token = token[: -len(".html")]
    token = token.replace("_", " ").replace("-", " ")
    token = " ".join(token.split())
    if token.endswith("committee") and not token.endswith(" committee"):
        token = token.replace("committee", " committee")

    candidates = {token}
    candidates.add(token.replace(" committee", ""))

    for committee in COMMITTEES:
        if committee.key == token:
            return committee.key
        if committee.name.lower() == token:
            return committee.key
        if committee.key in candidates:
            return committee.key
        if committee.name.lower() in candidates:
            return committee.key
        for alias in committee.aliases:
            alias_token = " ".join(alias.lower().replace("_", " ").replace("-", " ").split())
            if alias_token in candidates:
                return committee.key
    return ""


def committee_by_key(key: str) -> Committee | None:
    normalized = normalize_committee_key(key)
    for committee in COMMITTEES:
        if committee.key == normalized:
            return committee
    return None


def iter_committees() -> Iterable[Committee]:
    return COMMITTEES
