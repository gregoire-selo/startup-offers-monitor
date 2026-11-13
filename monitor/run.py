"""Point d'entrée : python -m monitor.run [--sources wttj,linkedin,ats,rss] [--fixtures DIR]"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

import requests
import yaml

from . import scoring, sources
from .dashboard import render

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "offers.json"
DOCS = ROOT / "docs" / "index.html"
log = logging.getLogger("run")


def load_state() -> dict:
    if DATA.exists():
        return json.loads(DATA.read_text(encoding="utf-8"))
    return {"offers": {}, "runs": []}


def dedupe_key(j: dict) -> str:
    return scoring.norm(j["title"])[:80] + "|" + scoring.norm(j["company"])[:40]


def collect(cfg: dict, wanted: list[str], fixtures: Path | None) -> tuple[list[dict], dict]:
    jobs, stats = [], {}
    if fixtures:   # mode test hors-ligne
        for h in json.loads((fixtures / "wttj_hits.json").read_text())["hits"]:
            if (j := sources.parse_wttj_hit(h)):
                jobs.append(j)
        jobs += sources.parse_linkedin_html((fixtures / "linkedin.html").read_text(), "Stage")
        return jobs, {"fixtures": len(jobs)}
    for name in wanted:
        try:
            got = sources.ALL_SOURCES[name](cfg)
        except Exception as e:  # noqa: BLE001
            log.exception("Source %s en échec : %s", name, e)
            got = []
        stats[name] = len(got)
        jobs += got
    return jobs, stats


def notify_telegram(new: list[dict]):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat and new):
        return
    lines = [f"🚀 {len(new)} nouvelle(s) offre(s) startup"]
    for j in new[:15]:
        lines.append(f"\n<b>{j['score']}</b> · {j['title']} — {j['company']}\n{j['url']}")
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                      data={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "HTML",
                            "disable_web_page_preview": "true"})
    except requests.RequestException as e:
        log.warning("Telegram : %s", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="wttj,linkedin,ats,rss")
    ap.add_argument("--fixtures", type=Path)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    state = load_state()
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    raw, stats = collect(cfg, args.sources.split(","), args.fixtures)
    seen_keys, kept, new = {}, 0, []
    for j in raw:
        if not scoring.location_ok(j, cfg):
            continue
        s, why, formats = scoring.score(j, cfg)
        if s < cfg["min_score"]:
            continue
        k = dedupe_key(j)
        if k in seen_keys and seen_keys[k] != j["id"]:
            # même offre vue sur une autre source : on garde la 1re, on ajoute le lien
            other = state["offers"].get(seen_keys[k])
            if other and j["url"] not in other.get("alt_urls", []) and j["url"] != other["url"]:
                other.setdefault("alt_urls", []).append(j["url"])
            continue
        seen_keys[k] = j["id"]
        kept += 1
        prev = state["offers"].get(j["id"])
        rec = {k2: v for k2, v in j.items() if k2 != "text"}
        rec.update(score=s, why=why, formats=formats, last_seen=today,
                   first_seen=prev["first_seen"] if prev else today,
                   alt_urls=prev.get("alt_urls", []) if prev else [])
        state["offers"][j["id"]] = rec
        if not prev:
            new.append(rec)

    state["runs"] = (state.get("runs", []) + [{"at": now, "raw": len(raw), "kept": kept,
                                               "new": len(new), "sources": stats}])[-60:]
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    DOCS.parent.mkdir(exist_ok=True)
    DOCS.write_text(render(state, cfg, now), encoding="utf-8")

    new.sort(key=lambda r: -r["score"])
    notify_telegram([n for n in new if n["score"] >= cfg["notify_score"]])

    summary = [f"### Veille startup — {now}", f"Brut : {len(raw)} · retenues : {kept} · **nouvelles : {len(new)}**",
               f"Par source : {stats}", ""]
    summary += [f"- **{n['score']}** [{n['title']} — {n['company']}]({n['url']})" for n in new[:30]]
    print("\n".join(summary))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")


if __name__ == "__main__":
    main()
