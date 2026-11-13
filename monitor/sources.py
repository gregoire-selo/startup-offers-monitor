"""Collecte des offres : Welcome to the Jungle, LinkedIn (guest), ATS (Lever/Greenhouse/Ashby), RSS.

Chaque source renvoie une liste de dicts normalisés :
  {id, source, title, company, location, url, published, contract, remote, text}
`text` = tout le texte disponible, utilisé pour le scoring.
Une source qui plante n'arrête jamais les autres : l'erreur est loggée.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("sources")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})


def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(p.strip().lower() for p in parts).encode()).hexdigest()[:16]


def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", BeautifulSoup(s, "html.parser").get_text(" ")).strip()


def _get(url, **kw):
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=25, **kw)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return r
        except requests.RequestException as e:
            log.warning("GET %s failed (%s)", url, e)
            time.sleep(2)
    return None


# ───────────────────────── Welcome to the Jungle ─────────────────────────
WTTJ_APP = "CSEKHVMS53"
WTTJ_KEY = "4bd8f6215d0cc52b26430765769e65a0"   # clé publique search-only du front WTTJ
WTTJ_URL = f"https://{WTTJ_APP.lower()}-dsn.algolia.net/1/indexes/*/queries"
WTTJ_INDEXES = [  # essayés dans l'ordre (WTTJ a déjà renommé ses index)
    ("wttj_jobs_production_fr", ""),
    ("wk_cms_jobs_production", "website.reference:wttj_fr"),
]
WTTJ_HEADERS = {
    "x-algolia-application-id": WTTJ_APP,
    "x-algolia-api-key": WTTJ_KEY,
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://www.welcometothejungle.com",
    "referer": "https://www.welcometothejungle.com/",
}


def _wttj_query(index: str, filters: str, query: str, since_ts: int, page: int = 0):
    params = {"query": query, "hitsPerPage": 100, "page": page,
              "numericFilters": f"published_at_timestamp>{since_ts}"}
    if filters:
        params["filters"] = filters
    body = {"requests": [{"indexName": index, "params": urlencode(params)}]}
    r = SESSION.post(WTTJ_URL, headers=WTTJ_HEADERS, data=json.dumps(body), timeout=25)
    r.raise_for_status()
    return r.json()["results"][0]


def parse_wttj_hit(h: dict) -> dict | None:
    org = h.get("organization") or {}
    org_slug, slug = org.get("slug") or "", h.get("slug") or ""
    if not (org_slug and slug):
        return None
    offices = h.get("offices") or ([h["office"]] if h.get("office") else [])
    cities = ", ".join(filter(None, {(o or {}).get("city", "") for o in offices}))
    countries = {((o or {}).get("country_code") or "").upper() for o in offices}
    contract = (h.get("contract_type_names") or {}).get("fr") or h.get("contract_type") or ""
    return {
        "id": "wttj-" + str(h.get("reference") or h.get("objectID") or _id(org_slug, slug)),
        "source": "WTTJ",
        "title": h.get("name") or "",
        "company": org.get("name") or org_slug,
        "location": cities,
        "countries": sorted(c for c in countries if c),
        "url": f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}",
        "published": (h.get("published_at") or "")[:10],
        "contract": str(contract),
        "remote": str(h.get("remote") or ""),
        "company_size": str(org.get("nb_employees") or ""),
        # tout le hit sérialisé = maximum de texte pour le scoring (missions, profil, etc.)
        "text": _strip_html(json.dumps(h, ensure_ascii=False)),
    }


def fetch_wttj(cfg: dict) -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=cfg["max_age_days"])).timestamp())
    out, index = [], None
    for idx, flt in WTTJ_INDEXES:   # détecte l'index qui marche
        try:
            _wttj_query(idx, flt, "chief of staff", since)
            index = (idx, flt)
            break
        except Exception as e:  # noqa: BLE001
            log.info("WTTJ index %s indisponible (%s)", idx, e)
    if not index:
        log.error("WTTJ : aucun index Algolia ne répond — vérifier la clé dans sources.py")
        return out
    for q in cfg["queries"]:
        for page in range(3):
            try:
                res = _wttj_query(index[0], index[1], q, since, page)
            except Exception as e:  # noqa: BLE001
                log.warning("WTTJ '%s' p%d : %s", q, page, e)
                break
            for h in res.get("hits", []):
                j = parse_wttj_hit(h)
                if j:
                    out.append(j)
            if page + 1 >= res.get("nbPages", 0):
                break
            time.sleep(0.3)
    log.info("WTTJ : %d offres brutes", len(out))
    return out


# ───────────────────────── LinkedIn (API guest publique) ─────────────────────────
LI_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


def parse_linkedin_html(page_html: str, contract_hint: str = "") -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    out = []
    for card in soup.select("li"):
        a = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        t = card.select_one(".base-search-card__title, h3")
        if not (a and t):
            continue
        url = a["href"].split("?")[0]
        m = re.search(r"(\d{8,})", url)
        comp = card.select_one(".base-search-card__subtitle, h4")
        loc = card.select_one(".job-search-card__location")
        tm = card.select_one("time")
        title = t.get_text(strip=True)
        company = comp.get_text(strip=True) if comp else ""
        out.append({
            "id": "li-" + (m.group(1) if m else _id(title, company)),
            "source": "LinkedIn",
            "title": title,
            "company": company,
            "location": loc.get_text(strip=True) if loc else "",
            "countries": [],
            "url": url,
            "published": tm.get("datetime", "") if tm else "",
            "contract": contract_hint,
            "remote": "",
            "company_size": "",
            "text": f"{title} {company} {contract_hint}",
        })
    return out


def fetch_linkedin(cfg: dict) -> list[dict]:
    secs = cfg["max_age_days"] * 86400
    # f_JT : I=stage, P=temps partiel, C=contrat/freelance, T=temporaire
    combos = [("I", "Stage"), ("P", "Temps partiel"), ("C", "Freelance / contrat"), ("T", "Temporaire")]
    out = []
    for q in cfg["queries"]:
        for loc in cfg["locations"]["linkedin"]:
            for jt, label in combos:
                params = {"keywords": q, "location": loc, "f_TPR": f"r{secs}", "f_JT": jt, "start": 0}
                if loc == "France":
                    params["f_WT"] = "2"   # remote uniquement hors Paris
                r = _get(LI_URL + "?" + urlencode(params, quote_via=quote))
                if r is None or r.status_code != 200:
                    log.warning("LinkedIn '%s' %s %s : %s", q, loc, jt, getattr(r, "status_code", "err"))
                    continue
                jobs = parse_linkedin_html(r.text, label)
                for j in jobs:
                    if loc == "France":
                        j["remote"] = "fulltime"
                out += jobs
                time.sleep(1.2)
    log.info("LinkedIn : %d offres brutes", len(out))
    return out


# ───────────────────────── ATS : Lever / Greenhouse / Ashby ─────────────────────────
def fetch_ats(cfg: dict) -> list[dict]:
    out, ats = [], cfg.get("ats") or {}
    for slug in ats.get("lever") or []:
        r = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if r is None or r.status_code != 200:
            log.warning("Lever '%s' introuvable (%s)", slug, getattr(r, "status_code", "err"))
            continue
        for p in r.json():
            cat = p.get("categories") or {}
            out.append({
                "id": "lever-" + p["id"], "source": f"Lever · {slug}", "title": p.get("text", ""),
                "company": slug.capitalize(), "location": cat.get("location", ""), "countries": [],
                "url": p.get("hostedUrl", ""),
                "published": datetime.fromtimestamp(p.get("createdAt", 0) / 1000, timezone.utc).strftime("%Y-%m-%d"),
                "contract": cat.get("commitment", ""), "remote": p.get("workplaceType", ""), "company_size": "",
                "text": " ".join([p.get("text", ""), cat.get("commitment", ""), cat.get("location", ""),
                                  p.get("descriptionPlain", "") or "", p.get("additionalPlain", "") or ""]),
            })
    for slug in ats.get("greenhouse") or []:
        r = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
        if r is None or r.status_code != 200:
            log.warning("Greenhouse '%s' introuvable (%s)", slug, getattr(r, "status_code", "err"))
            continue
        for p in r.json().get("jobs", []):
            loc = (p.get("location") or {}).get("name", "")
            out.append({
                "id": f"gh-{p['id']}", "source": f"Greenhouse · {slug}", "title": p.get("title", ""),
                "company": slug.capitalize(), "location": loc, "countries": [], "url": p.get("absolute_url", ""),
                "published": (p.get("updated_at") or "")[:10], "contract": "", "remote": "", "company_size": "",
                "text": p.get("title", "") + " " + loc + " " + _strip_html(html.unescape(p.get("content", ""))),
            })
    for slug in ats.get("ashby") or []:
        r = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        if r is None or r.status_code != 200:
            log.warning("Ashby '%s' introuvable (%s)", slug, getattr(r, "status_code", "err"))
            continue
        for p in r.json().get("jobs", []):
            out.append({
                "id": f"ashby-{p.get('id')}", "source": f"Ashby · {slug}", "title": p.get("title", ""),
                "company": slug.capitalize(), "location": p.get("location", ""), "countries": [],
                "url": p.get("jobUrl", ""), "published": (p.get("publishedAt") or "")[:10],
                "contract": p.get("employmentType", ""), "remote": "fulltime" if p.get("isRemote") else "",
                "company_size": "",
                "text": " ".join([p.get("title", ""), p.get("employmentType", ""), p.get("location", ""),
                                  p.get("descriptionPlain", "") or ""]),
            })
    log.info("ATS : %d offres brutes", len(out))
    return out


# ───────────────────────── RSS (Google Alerts, etc.) ─────────────────────────
def fetch_rss(cfg: dict) -> list[dict]:
    out = []
    for feed in cfg.get("rss") or []:
        r = _get(feed)
        if r is None or r.status_code != 200:
            log.warning("RSS %s : %s", feed, getattr(r, "status_code", "err"))
            continue
        soup = BeautifulSoup(r.content, "xml")
        for it in soup.find_all(["item", "entry"]):
            title = _strip_html(it.title.get_text() if it.title else "")
            link_tag = it.find("link")
            link = (link_tag.get("href") or link_tag.get_text()) if link_tag else ""
            m = re.search(r"[?&]url=([^&]+)", link)   # Google Alerts enveloppe l'URL
            if m:
                from urllib.parse import unquote
                link = unquote(m.group(1))
            summ = _strip_html((it.find("description") or it.find("content") or it.find("summary") or "").__str__())
            date = (it.find("pubDate") or it.find("published") or it.find("updated"))
            out.append({
                "id": "rss-" + _id(link or title), "source": "RSS", "title": title, "company": "",
                "location": "", "countries": [], "url": link, "published": (date.get_text() if date else "")[:16],
                "contract": "", "remote": "", "company_size": "", "text": f"{title} {summ}",
            })
    log.info("RSS : %d offres brutes", len(out))
    return out


ALL_SOURCES = {"wttj": fetch_wttj, "linkedin": fetch_linkedin, "ats": fetch_ats, "rss": fetch_rss}
