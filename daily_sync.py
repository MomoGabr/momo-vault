"""
Momo Vault — Daily Autonomous Production Sync (GitHub Actions & Local Cron)
Controlla i nuovi video pubblicati dai 5 canali YouTube, sincronizza Trakt (visti + voti)
e rigenera index.html + cine_dashboard.html in ~15 secondi.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import re
import requests

import cine_dashboard as cd
import multi_creator_scanner as mcs

ALL_CHANNELS = [
    ("Federico Frusciante", "UCeiW1AdgyfDyW5wPLjZqH2Q"),
    ("Francesco Alò", "UC3i9322156_vA8N1E3R-k9w"),
    ("I Criticoni", "UCwce2-aT-1g39hB3L4nB0aw"),
    ("Mr. Marra", "UCf9_D6s-7h423l1l6_s6k7w"),
    ("Victorlaszlo88", "UC-9_p7h2L2N9C8-3W6-5z8g"),
]


def fetch_latest_channel_videos(creator, channel_id, max_vids=15):
    """
    Recupera gli ultimi video pubblicati sul canale tramite RSS ufficiale YouTube
    (zero blocchi IP su GitHub Actions) con fallback su InnerTube browse.
    """
    vids = []
    try:
        r = requests.get(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code == 200:
            vids = list(
                dict.fromkeys(re.findall(r"<yt:videoId>([^<]+)</yt:videoId>", r.text))
            )
    except Exception:
        pass

    if not vids:
        try:
            r = requests.post(
                "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false",
                json={"browseId": channel_id, "context": mcs.CTX},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=12,
            )
            if r.status_code == 200:
                vids = list(
                    dict.fromkeys(re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text))
                )
        except Exception:
            pass

    return [{"video_id": v, "creator": creator} for v in vids[:max_vids]]


EBERT_POS_WORDS = (
    "masterpiece",
    "triumph",
    "brilliant",
    "extraordinary",
    "gem",
    "thrilling",
    "magnificent",
    "wonderful",
    "compelling",
    "stunning",
    "superb",
    "essential",
    "tour de force",
    "riveting",
    "exquisite",
    "unforgettable",
    "crowd-pleasing",
    "more heart",
    "exalting",
    "entertainingly",
    "emotional center",
    "terrific",
    "gripping",
    "captivating",
    "impressive",
)
EBERT_NEG_WORDS = (
    "forgets to",
    "fun enough if",
    "incorporeal",
    "watered-down",
    "suffers from",
    "disappointing",
    "tedious",
    "dull",
    "mess",
    "mediocre",
    "fails",
    "forgettable",
    "uninspired",
    "clunky",
    "lifeless",
    "boring",
    "disaster",
    "shallow",
    "hollow",
    "squanders",
    "tiresome",
    "misfire",
)


def sync_latest_rogerebert_feed(db_data, headers, ch_map, daily_log=None):
    """
    Scarica le ultime recensioni da https://www.rogerebert.com/reviews/feed
    e https://www.rogerebert.com/category/great-movies/feed e aggiunge quelle positive!
    """
    if daily_log is None:
        daily_log = []
    processed_set = set(db_data.get("processed_videos", []))
    new_ebert = []
    for feed_url, is_great in (
        ("https://www.rogerebert.com/reviews/feed", False),
        ("https://www.rogerebert.com/category/great-movies/feed", True),
    ):
        try:
            r = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            if r.status_code != 200:
                continue
            for item_xml in re.findall(r"<item>(.*?)</item>", r.text, re.S):
                m_t = re.search(r"<title>(.*?)</title>", item_xml)
                m_l = re.search(r"<link>(.*?)</link>", item_xml)
                if not m_t or not m_l:
                    continue
                title = m_t.group(1).strip()
                link = m_l.group(1).strip()
                slug = link.rstrip("/").split("/")[-1]
                vid = f"ebert_{slug}"
                if vid in processed_set:
                    continue
                m_d = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item_xml, re.S)
                sub_low = (m_d.group(1) if m_d else "").lower()
                low_xml = item_xml.lower()
                if not is_great:
                    if any(w in sub_low for w in EBERT_NEG_WORDS):
                        processed_set.add(vid)
                        continue
                    sub_pos = any(w in sub_low for w in EBERT_POS_WORDS)
                    pos = sum(1 for w in EBERT_POS_WORDS if w in low_xml)
                    neg = sum(1 for w in EBERT_NEG_WORDS if w in low_xml)
                    if not sub_pos and (pos < 2 or neg >= pos):
                        processed_set.add(vid)
                        continue
                m_yr = re.search(r"-(202\d)$", slug)
                yr = int(m_yr.group(1)) if m_yr else 2026
                badge = "★ Great Movie" if is_great else "★ Consigliato"
                new_ebert.append((vid, title, yr, link, badge))
        except Exception:
            pass

    print(f"  • {'RogerEbert.com':20s}: {len(new_ebert)} nuove recensioni positive dal feed")
    for vid, title, yr, link, badge in new_ebert:
        processed_set.add(vid)
        rec = {
            "creator": "Roger Ebert",
            "video_id": vid,
            "video_title": "Roger Ebert",
            "timestamp": "",
            "seconds": 0,
            "external_rec_url": link,
            "mentioned_as": title,
        }
        is_tv = "-tv-review-" in link
        cat = "show" if is_tv else "movie"
        m_slug = "shows" if is_tv else "movies"
        k = mcs.find_matching_movie_key(db_data["items"], title, target_year=yr)
        if k and k in db_data["items"]:
            existing_eb = [r for r in db_data["items"][k].get("recommendations", []) if r.get("creator") == "Roger Ebert"]
            if existing_eb:
                existing_eb[0]["external_rec_url"] = link
            else:
                db_data["items"][k]["recommendations"].append(rec)
                tt = db_data["items"][k].get("imdb_id", "")
                daily_log.append(
                    f"  • [Roger Ebert] {db_data['items'][k].get('it_title')} ({db_data['items'][k].get('year')})\n"
                    f"    🔗 Recensione: {link}\n"
                    f"    🎬 Trakt: https://app.trakt.tv/{m_slug}/{tt}"
                )
        else:
            enr = cd.enrich_movie(
                {
                    "raw_title": title,
                    "category": cat,
                    "inferred_year": yr,
                    "max_video_year": 2026,
                    "is_classic": False,
                    "director_hint": "",
                },
                headers,
                ch_map,
                check_ch=True,
            )
            if enr.get("imdb_id"):
                if is_tv:
                    enr["category"] = "show"
                    enr["media_type"] = "show"
                fid = enr["id"]
                if fid not in db_data["items"]:
                    enr["recommendations"] = [rec]
                    db_data["items"][fid] = enr
                else:
                    db_data["items"][fid]["recommendations"].append(rec)
                daily_log.append(
                    f"  • [Roger Ebert] {enr.get('it_title')} ({enr.get('year')})\n"
                    f"    🔗 Recensione: {link}\n"
                    f"    🎬 Trakt: https://app.trakt.tv/{m_slug}/{enr.get('imdb_id')}"
                )

    db_data["processed_videos"] = list(processed_set)


def sync_latest_scaruffi_cinema(db_data, headers, ch_map, daily_log=None):
    """
    Controlla https://www.scaruffi.com/cinema/best26.html e chro020.html
    per eventuali nuovi film >= 7.0 aggiunti da Piero Scaruffi.
    """
    if daily_log is None:
        daily_log = []
    processed_set = set(db_data.get("processed_videos", []))
    new_scar = []
    for p_name, def_yr in (("best26.html", 2026), ("best25.html", 2025), ("chro020.html", 2025)):
        u = f"https://www.scaruffi.com/cinema/{p_name}"
        try:
            r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code != 200:
                continue
            for line in r.text.splitlines():
                m = re.search(
                    r"(?:<br>|^)\s*([789]\.\d)\s+(?:<a\s+href=([^>]+)>)?([^<:]+?)(?:</a>)?\s*:?\s*<b>(.*?)</b>(?:\s*\(([^\)]+)\))?",
                    line,
                    re.I,
                )
                if not m:
                    continue
                href = (m.group(2) or "").strip("\"'").lstrip("./")
                director = re.sub(r"<.*?>", "", m.group(3)).strip()
                raw_titles = re.sub(r"<.*?>", "", m.group(4)).strip()
                parts = [p.strip(" `") for p in raw_titles.split("/") if p.strip(" `")]
                if not parts:
                    continue
                paren = (m.group(5) or "").strip()
                m_yr = re.search(r"\b(202\d)\b", paren)
                yr = int(m_yr.group(1)) if m_yr else def_yr
                slug = re.sub(r"\W+", "", parts[-1].lower())
                vid = f"scaruffi_{slug}_{yr}"
                if vid in processed_set:
                    continue
                link = f"https://www.scaruffi.com/{href}" if (href and not href.startswith("http")) else u
                new_scar.append((vid, parts[-1], director, yr, link))
        except Exception:
            pass

    print(f"  • {'Piero Scaruffi':20s}: {len(new_scar)} nuovi film >=7.0 da verificare")
    for vid, title, director, yr, link in new_scar:
        processed_set.add(vid)
        rec = {
            "creator": "Piero Scaruffi",
            "video_id": vid,
            "video_title": "Piero Scaruffi",
            "timestamp": "",
            "seconds": 0,
            "external_rec_url": link,
            "mentioned_as": title,
        }
        k = mcs.find_matching_movie_key(db_data["items"], title, target_year=yr, dir_hint=director)
        if k and k in db_data["items"]:
            if not any(r.get("creator") == "Piero Scaruffi" for r in db_data["items"][k].get("recommendations", [])):
                db_data["items"][k]["recommendations"].append(rec)
                tt = db_data["items"][k].get("imdb_id", "")
                daily_log.append(
                    f"  • [Piero Scaruffi] {db_data['items'][k].get('it_title')} ({db_data['items'][k].get('year')})\n"
                    f"    🔗 Scheda Scaruffi: {link}\n"
                    f"    🎬 Trakt: https://app.trakt.tv/movies/{tt}"
                )
        else:
            enr = cd.enrich_movie(
                {
                    "raw_title": title,
                    "category": "movie",
                    "inferred_year": yr,
                    "max_video_year": 2026,
                    "is_classic": False,
                    "director_hint": director,
                },
                headers,
                ch_map,
                check_ch=True,
            )
            if enr.get("imdb_id"):
                fid = enr["id"]
                if fid not in db_data["items"]:
                    enr["recommendations"] = [rec]
                    db_data["items"][fid] = enr
                else:
                    db_data["items"][fid]["recommendations"].append(rec)
                daily_log.append(
                    f"  • [Piero Scaruffi] {enr.get('it_title')} ({enr.get('year')})\n"
                    f"    🔗 Scheda Scaruffi: {link}\n"
                    f"    🎬 Trakt: https://app.trakt.tv/movies/{enr.get('imdb_id')}"
                )

    db_data["processed_videos"] = list(processed_set)


def update_daily_log_file(daily_log, total_items, total_watched):
    log_path = os.path.join(cd.BASE_DIR, "daily_updates.txt")
    docs_log_path = os.path.join(cd.BASE_DIR, "docs", "daily_updates.txt")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f"========================================================================\n"
        f"📅 SYNC DEL {now_str} | Opere nel Vault: {total_items} | Visti Trakt: {total_watched}\n"
        f"========================================================================\n"
    )
    if daily_log:
        body = f"✨ Nuovi video/recensioni aggiunti oggi ({len(daily_log)}):\n" + "\n".join(daily_log) + "\n\n"
    else:
        body = "✓ Nessun nuovo video/recensione uscito oggi (Trakt e Streaming CH/IT sincronizzati).\n\n"

    existing = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = ""

    # Rimuovi eventuale banner statico iniziale prima di prependere il nuovo blocco in cima
    banner = (
        "########################################################################\n"
        "# 🎬 MOMO VAULT — REGISTRO GIORNALIERO NUOVI VIDEO E LINK AGGIUNTI     #\n"
        "########################################################################\n\n"
    )
    if existing.startswith("####"):
        parts = existing.split("\n\n", 1)
        existing = parts[1] if len(parts) > 1 else ""

    new_content = banner + header + body + existing
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    if os.path.isdir(os.path.join(cd.BASE_DIR, "docs")):
        with open(docs_log_path, "w", encoding="utf-8") as f:
            f.write(new_content)


def main():
    print("🚀 Avvio Daily Autonomous Sync — Momo Vault...")
    headers = cd.get_trakt_headers()
    ch_map = cd.fetch_ch_sources_map(headers)
    watched_imdb, ratings_imdb = cd.fetch_user_trakt_state(headers)

    if not os.path.exists(cd.DB_PATH):
        raise RuntimeError(f"Database non trovato: {cd.DB_PATH}")

    with open(cd.DB_PATH, encoding="utf-8") as f:
        db_data = json.load(f)

    if watched_imdb:
        db_data["watched_imdb"] = list(watched_imdb)
        db_data["ratings_imdb"] = ratings_imdb
    else:
        watched_imdb = set(db_data.get("watched_imdb", []))
        ratings_imdb = db_data.get("ratings_imdb", {})

    processed_set = set(db_data.get("processed_videos", []))
    daily_log = []

    new_candidates = []
    for creator, ch_id in ALL_CHANNELS:
        latest = fetch_latest_channel_videos(creator, ch_id, max_vids=15)
        unseen = [x for x in latest if x["video_id"] not in processed_set]
        print(f"  • {creator:20s}: {len(unseen)} nuovi video da analizzare")
        new_candidates.extend(unseen)

    if new_candidates:
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(mcs.process_creator_video, new_candidates))

        to_enrich = []
        for vid, creator, meta, items in results:
            if not meta:
                continue
            processed_set.add(vid)
            for raw in items:
                explicit_yr = raw.get("inferred_year")
                match_yr = explicit_yr or (
                    raw.get("max_video_year") if len(items) == 1 else None
                )
                k = mcs.find_matching_movie_key(
                    db_data["items"],
                    raw["raw_title"],
                    target_year=match_yr,
                    dir_hint=raw.get("director_hint", ""),
                )
                rec = {
                    "creator": creator,
                    "video_id": vid,
                    "video_title": meta["title"],
                    "timestamp": raw["timestamp"],
                    "seconds": raw["seconds"],
                    "mentioned_as": raw["raw_title"],
                }
                if k and k in db_data["items"]:
                    db_data["items"][k]["recommendations"].append(rec)
                    tt = db_data["items"][k].get("imdb_id", "")
                    yt_url = f"https://youtu.be/{vid}?t={raw['seconds'] or 0}s"
                    daily_log.append(
                        f"  • [{creator}] {db_data['items'][k].get('it_title')} ({db_data['items'][k].get('year')}) — {meta['title']}\n"
                        f"    ▶️ Video YouTube: {yt_url}\n"
                        f"    🎬 Trakt: https://app.trakt.tv/movies/{tt}"
                    )
                else:
                    raw["inferred_year"] = explicit_yr
                    to_enrich.append((raw, rec))

        if to_enrich:
            print(f"  ✨ Arricchisco {len(to_enrich)} nuove opere su IMDb/Trakt CH+IT...")
            with ThreadPoolExecutor(max_workers=8) as pool:
                enriched_list = list(
                    pool.map(
                        lambda pair: (
                            cd.enrich_any(pair[0], headers, ch_map),
                            pair[1],
                        ),
                        to_enrich,
                    )
                )
            for enriched, rec in enriched_list:
                if not enriched.get("imdb_id") and enriched.get("category") == "movie":
                    continue
                fid = enriched["id"]
                if fid not in db_data["items"]:
                    enriched["recommendations"] = [rec]
                    db_data["items"][fid] = enriched
                else:
                    db_data["items"][fid]["recommendations"].append(rec)
                yt_url = f"https://youtu.be/{rec['video_id']}?t={rec.get('seconds') or 0}s"
                daily_log.append(
                    f"  • [{rec['creator']}] {enriched.get('it_title')} ({enriched.get('year')}) — {rec.get('video_title')}\n"
                    f"    ▶️ Video YouTube: {yt_url}\n"
                    f"    🎬 Trakt: https://app.trakt.tv/movies/{enriched.get('imdb_id', '')}"
                )

        db_data["processed_videos"] = list(processed_set)

    sync_latest_rogerebert_feed(db_data, headers, ch_map, daily_log)
    sync_latest_scaruffi_cinema(db_data, headers, ch_map, daily_log)
    cd.save_db(db_data)
    cd.generate_html(db_data, watched_imdb, ratings_imdb)
    update_daily_log_file(daily_log, len(db_data["items"]), len(watched_imdb))
    print(f"✅ Sync completato! Opere nel Vault: {len(db_data['items'])}")


if __name__ == "__main__":
    main()
