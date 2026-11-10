"""
Momo Vault — Daily Autonomous Production Sync (GitHub Actions & Local Cron)
Controlla i nuovi video pubblicati dai 5 canali YouTube, sincronizza Trakt (visti + voti)
e rigenera index.html + cine_dashboard.html in ~15 secondi.
"""

from concurrent.futures import ThreadPoolExecutor
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
)
EBERT_NEG_WORDS = (
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
)


def sync_latest_rogerebert_feed(db_data, headers, ch_map):
    """
    Scarica le ultime recensioni da https://www.rogerebert.com/reviews/feed
    e https://www.rogerebert.com/category/great-movies/feed e aggiunge quelle positive!
    """
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
                low_xml = item_xml.lower()
                pos = sum(1 for w in EBERT_POS_WORDS if w in low_xml)
                neg = sum(1 for w in EBERT_NEG_WORDS if w in low_xml)
                if not is_great and (pos < 2 or neg >= pos):
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
        k = mcs.find_matching_movie_key(db_data["items"], title, target_year=yr)
        if k and k in db_data["items"]:
            db_data["items"][k]["recommendations"].append(rec)
        else:
            enr = cd.enrich_movie(
                {
                    "raw_title": title,
                    "category": "movie",
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
                fid = enr["id"]
                if fid not in db_data["items"]:
                    enr["recommendations"] = [rec]
                    db_data["items"][fid] = enr
                else:
                    db_data["items"][fid]["recommendations"].append(rec)

    db_data["processed_videos"] = list(processed_set)


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

        db_data["processed_videos"] = list(processed_set)

    sync_latest_rogerebert_feed(db_data, headers, ch_map)
    cd.save_db(db_data)
    cd.generate_html(db_data, watched_imdb, ratings_imdb)
    print(f"✅ Sync completato! Opere nel Vault: {len(db_data['items'])}")


if __name__ == "__main__":
    main()
