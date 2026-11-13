"""Score de pertinence d'une offre par rapport au profil de Grégoire (0–100 environ)."""
from __future__ import annotations

import re
import unicodedata


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s.replace("’", "'"))


def _has(text: str, term: str) -> bool:
    t = norm(term)
    # bornes de mot pour les termes courts (évite "sdr" dans "sdrive", "vp" dans "vpn"…)
    if len(t) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text) is not None
    return t in text


PATTERNS = {
    "internship": r"\b(stage|stagiaire|intern|internship|stage alterne|stage altern)\b",
    "freelance": r"\b(freelance|free-lance|independant|portage|mission de \d|contractor|consultant externe)\b",
    "part_time": r"(temps partiel|part[- ]time|mi-temps|\b[234],?5? ?(jours|j|days) ?(/|par|per|a|une) ?(semaine|sem|week)|\b(3|4) jours\b)",
    "alternance": r"\b(alternance|apprentissage|apprenti|work[- ]study|apprenticeship)\b",
    "cdi": r"\b(cdi|full[- ]time|temps plein|permanent)\b",
}
YOUNG = r"\b(intern|internship|stage|stagiaire|junior|alternan|apprenti|graduate)\b"


def location_ok(job: dict, cfg: dict) -> bool:
    loc = norm(job.get("location", ""))
    remote = norm(job.get("remote", ""))
    countries = job.get("countries") or []
    if countries and "FR" not in countries:
        return False
    if any(c in loc for c in (norm(x) for x in cfg["locations"]["keep_cities"])):
        return True
    if cfg["locations"].get("keep_remote") and (remote in ("fulltime", "full_time", "remote", "fully_remote")
                                                or "remote" in loc or "teletravail" in loc or "a distance" in loc):
        return True
    if job["source"] in ("RSS",) or job["source"].startswith(("Lever", "Greenhouse", "Ashby")):
        # pages carrières : on garde si Paris/France/remote apparaît quelque part
        return bool(re.search(r"paris|france|remote|ile-de-france", norm(job.get("text", ""))[:3000]))
    return False


def score(job: dict, cfg: dict) -> tuple[int, list[str], list[str]]:
    sc = cfg["scoring"]
    title = norm(job["title"])
    text = norm(" ".join([job["title"], job.get("contract", ""), job.get("text", "")]))
    pts, why, formats = 0, [], []

    strong = [t for t in sc["title_strong"] if _has(title, t)]
    medium = [t for t in sc["title_medium"] if _has(title, t)]
    if strong:
        pts += 40; why.append(f"poste cible ({strong[0]})")
    elif medium:
        pts += 20; why.append(f"poste proche ({medium[0]})")

    for key in ("internship", "freelance", "part_time", "alternance"):
        if re.search(PATTERNS[key], text):
            formats.append(key)
    for key in formats:
        pts += sc["contract"][key]
    if formats:
        why.append("format : " + ", ".join({"internship": "stage", "freelance": "freelance",
                                            "part_time": "temps partiel", "alternance": "alternance"}[f] for f in formats))
    elif re.search(PATTERNS["cdi"], text):
        pts += sc["cdi_only_penalty"]; why.append("CDI/temps plein seulement")

    if any(_has(text, t) for t in sc["timing_terms"]):
        pts += sc["timing_bonus"]; why.append("démarrage début 2027 / ASAP")
    if any(_has(text, t) for t in sc["timing_bad_terms"]) and not any(_has(text, t) for t in sc["timing_terms"]):
        pts += sc["timing_penalty"]; why.append("démarrage été/automne 2027")

    prof = [t for t in sc["profile_terms"] if _has(text, t)]
    if prof:
        pts += min(sc["profile_bonus_cap"], sc["profile_bonus_each"] * len(prof))
        why.append("profil : " + ", ".join(prof[:4]))
    if any(_has(text, t) for t in sc["startup_terms"]):
        pts += sc["startup_bonus"]

    neg = [t for t in sc["title_negative"] if _has(title, t)]
    if neg:
        pts -= 60; why.append(f"hors cible ({neg[0]})")
    if not re.search(YOUNG, title) and any(_has(title, t) for t in sc["title_seniority"]) and not strong:
        pts -= 40; why.append("poste senior")
    elif not re.search(YOUNG, title) and any(_has(title, t) for t in sc["title_seniority"]):
        pts -= 15; why.append("intitulé plutôt senior")

    return max(0, min(100, pts)), why, formats
