from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import sys
import time

import requests
import cine_dashboard as cd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MULTI_INDEX_PATH = os.path.join(BASE_DIR, "multi_creators_index.json")

CHANNELS = [
    ("Francesco Alò", "VLUU64x__-nUk0PiHv4Vmzs0NA"),
    ("I Criticoni", "VLUUqhjRUQGCnX4Y22kR_KD-Yg"),
    ("Mr. Marra", "VLUU_FaoEnCojZYsumBP_MFgfw"),
    ("Victorlaszlo88", "VLUUIfXF2g-jES4VTAPQzgIRUw"),
]

CTX = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20250101.00.00",
        "hl": "it",
        "gl": "IT",
    }
}


def build_or_load_multi_creator_index():
    if os.path.exists(MULTI_INDEX_PATH):
        try:
            with open(MULTI_INDEX_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if len(data) > 3000:
                return data
        except Exception:
            pass

    print("📥 Costruisco l'indice completo dei canali: Francesco Alò, I Criticoni, Mr. Marra, Victorlaszlo88...")
    all_vids = []
    seen = set()

    for creator, browse_id in CHANNELS:
        payload = {"browseId": browse_id, "context": CTX}
        ch_count = 0
        while True:
            try:
                r = requests.post(
                    "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false",
                    json=payload,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=20,
                )
                if r.status_code != 200:
                    break
                txt = r.text
                for vid in re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', txt):
                    if vid not in seen:
                        seen.add(vid)
                        ch_count += 1
                        all_vids.append({"video_id": vid, "creator": creator})
                cont = re.findall(r'"continuationCommand":\{"token":"([^"]+)"', txt)
                if not cont:
                    break
                payload = {"continuation": cont[-1], "context": CTX}
            except Exception:
                break
        print(f"   • {creator:18} -> {ch_count} video indicizzati")

    with open(MULTI_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(all_vids, f, ensure_ascii=False, indent=2)
    print(f"✅ Indice multi-creator salvato ({len(all_vids)} video totali)!")
    return all_vids


def extract_single_movie_from_creator_title(creator, title):
    """
    Riconosce i formati di recensione singola di ciascun creator:
    - Francesco Alò: '"Titolo" di Regista - recensione'
    - I Criticoni: 'CRITICONI su “Titolo” di Regista' / 'Cine-Deathmatch su “Titolo”'
    - Mr. Marra: 'Ho Visto “Titolo”' / 'RECENSIONE “Titolo”'
    - Victorlaszlo88: 'MovieBlog- 1118: Recensione Titolo' / 'Recensione: Titolo'
    """
    t_low = title.lower()
    if any(
        bad in t_low
        for bad in (
            "peggiori",
            "pegigo",
            "flop",
            "trailer",
            "box office",
            "oscar",
            "classifica",
            "attesi",
            "pesce d'aprile",
            "schifati",
        )
    ):
        return None, ""

    # 1. Titolo tra virgolette ("..." o “...” o «...»)
    m_q = re.search(r'["“«]([^"”»]{2,65})["”»]', title)
    if m_q and (
        creator in ("Francesco Alò", "I Criticoni")
        or any(k in t_low for k in ("recension", "ho visto", "criticoni su", "deathmatch"))
    ):
        movie_title = m_q.group(1).strip()
        m_dir = re.search(r'["”»]\s+di\s+([^-|\n(]+)', title, re.I)
        director = cd.normalize_director_name(m_dir.group(1)) if m_dir else ""
        if movie_title.lower() not in ("no spoiler", "spoiler", "con spoiler", "recensione"):
            return movie_title, director

    # 2. Formato Mr. Marra / generico con pipe: "<Titolo> [di Regista] | RECENSIONE [No Spoiler]"
    m_pipe = re.match(r"^\s*([^|]+?)\s*\|\s*recensione\b", title, re.I)
    if m_pipe:
        left = m_pipe.group(1).strip(" -–—\"“”")
        left = re.split(r"\s*:\s*|\s+è\s+un\s+", left, flags=re.I)[0].strip()
        m_d = re.search(r"^(.+?)\s+di\s+([A-ZÀ-Úa-zà-ú\.\-\s]{3,30})$", left)
        if m_d:
            left = m_d.group(1).strip(" -–—\"“”")
            dir_h = cd.normalize_director_name(m_d.group(2))
        else:
            dir_h = ""
        if 2 <= len(left) <= 60 and left.lower() not in ("no spoiler", "spoiler", "recensione"):
            return left, dir_h

    # 3. Victorlaszlo88 / generico: "MovieBlog - NNN: Recensione <Titolo>" o "Recensione <Titolo>"
    m_rec = re.search(
        r"(?:movieblog\s*[-–:]?\s*\d*\s*[:\-]?\s*)?recensione\s*(?:no\s+spoiler\s*|con\s+spoiler\s*)?[:\-]?\s*([^|\n(]+)",
        title,
        re.I,
    )
    if m_rec:
        cand = m_rec.group(1).strip(" -–—\"“”")
        cand = re.sub(
            r"\s*(?:\b(?:no\s+spoiler|con\s+spoiler|spoiler)\b).*$",
            "",
            cand,
            flags=re.I,
        ).strip(" -–—\"“”")
        m_d = re.search(r"^(.+?)\s+di\s+([A-ZÀ-Ú][a-zà-ú\.\-]+\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\.\-\s]{2,25})$", cand)
        if m_d:
            cand = m_d.group(1).strip(" -–—\"“”")
            dir_h = cd.normalize_director_name(m_d.group(2))
        else:
            dir_h = ""
        if (
            2 <= len(cand) <= 65
            and cand.lower() not in ("no spoiler", "spoiler", "con spoiler", "recensione")
        ):
            return cand, dir_h

    # 4. Formato recente Victorlaszlo88 / generico: "<Titolo Film>: <Commento positivo>"
    if ":" in title and not t_low.startswith(("movieblog", "criticoni", "live", "speciale", "oscar", "venezia", "cannes")):
        left = title.split(":", 1)[0].strip(" -–—\"“”")
        m_dir = re.search(r"\bdi\s+([A-ZÀ-Ú][a-zà-ú\.\-]+\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\.\-\s]{2,25})", title)
        dir_h = cd.normalize_director_name(m_dir.group(1)) if m_dir else ""
        if 2 <= len(left) <= 48 and left.lower() not in ("no spoiler", "spoiler", "recensione", "trailer"):
            return left, dir_h

    return None, ""


def process_creator_video(v_entry):
    vid = v_entry["video_id"]
    creator = v_entry["creator"]
    meta = cd.get_video_metadata(vid)
    if not meta:
        return vid, creator, None, []

    title = meta["title"]
    t_low = title.lower()
    if any(w in t_low for w in ("peggiori film", "il peggio", "flop dell")):
        return vid, creator, meta, []

    desc = meta["description"]
    ref_yr = meta.get("inferred_year")
    max_yr = meta.get("max_video_year", 2026)

    comment_text = ""
    if meta.get("comment_token"):
        try:
            rc = requests.post(
                "https://www.youtube.com/youtubei/v1/next?prettyPrint=false",
                json={"continuation": meta["comment_token"], "context": CTX},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=12,
            )
            if rc.status_code == 200:
                comments = [
                    json.loads(f'"{c}"')
                    for c in re.findall(
                        r'"content":\{"content":"((?:\\.|[^"\\])*)"', rc.text
                    )
                ]
                comment_text = " ".join(comments)
        except Exception:
            pass

    # 1. Se il titolo del video è una Recensione Singola (Alò / Criticoni / Marra / Victorlaszlo MovieBlog),
    # usa PRIMA il parlato vero del creator (YouTubeTranscriptApi, seconda metà del video + descrizione)
    # e usa i commenti solo come fallback se i sottotitoli non sono disponibili!
    single_title, dir_hint = extract_single_movie_from_creator_title(creator, title)
    if single_title:
        if (meta.get("length_seconds") or 999) <= 110:
            return vid, creator, meta, []
        verdict_ok = None
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            tr = YouTubeTranscriptApi().fetch(vid, languages=["it", "en"])
            full_t = " ".join(s.text for s in tr)
            # Valuta soprattutto il verdetto finale (ultimo 45% del parlato) + la descrizione
            end_t = full_t[int(len(full_t) * 0.55) :] + " " + desc
            score_tr, _, neg_tr = cd.score_frusciante_verdict(end_t)
            verdict_ok = (score_tr > 0) or (score_tr == 0 and len(neg_tr) == 0)
        except Exception:
            verdict_ok = None

        if verdict_ok is False:
            return vid, creator, meta, []
        if verdict_ok is None:
            if comment_text:
                score, _, neg_c = cd.score_frusciante_verdict(desc + " " + comment_text)
                if score < 0 or len(neg_c) >= 2:
                    return vid, creator, meta, []
            else:
                return vid, creator, meta, []

        return (
            vid,
            creator,
            meta,
            [
                {
                    "raw_title": single_title,
                    "category": "movie",
                    "timestamp": "00:00",
                    "seconds": 0,
                    "inferred_year": ref_yr,
                    "max_video_year": max_yr,
                    "is_classic": False,
                    "director_hint": dir_hint,
                }
            ],
        )

    # 2. Altrimenti, solo se il video è un Listone / Classifica / Migliori Film / Consigli, estrai i film coi timestamp!
    is_list_video = (
        any(
            w in t_low
            for w in (
                "migliori film",
                "top ",
                "consigli",
                "film preferiti",
                "film del 20",
                "film del decennio",
            )
        )
        and "attesi" not in t_low
        and "peggiori" not in t_low
    )
    if not is_list_video:
        return vid, creator, meta, []

    items = []
    in_neg = False
    for raw_line in desc.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        up = line.upper().strip(": -►•*")
        if up in {"PEGGIO", "IL PEGGIO", "FLOP", "SCONSIGLIATI", "I PEGGIORI"}:
            in_neg = True
            continue
        if up in {"MEGLIO", "IL MEGLIO", "TOP", "CONSIGLIATI", "I MIGLIORI"}:
            in_neg = False
            continue
        if in_neg:
            continue

        ts_m = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", line)
        if not ts_m:
            continue
        ts = ts_m.group(1)
        cleaned = re.sub(r"https?://\S+", "", line).replace(ts, "")
        cleaned = re.sub(
            r"\([^\)]*(?:sky|netflix|prime|sala|noleggio|disney|mubi|apple|hbo|disponibile)[^\)]*\)",
            "",
            cleaned,
            flags=re.I,
        )
        # Se nella riga c'è un titolo tra virgolette (es. '1’ consiglio Frusciante: “Zombeavers”'), estrai quello!
        m_quoted = re.search(r'["“«]([^"”»]{2,55})["”»]', cleaned)
        if m_quoted:
            cleaned = m_quoted.group(1).strip()
        else:
            cleaned = cleaned.strip(" -–—:•►*\t")

        c_low = cleaned.lower()
        bad_chapter_words = (
            "intro",
            "introduzione",
            "spiegazione",
            "conclusioni",
            "outro",
            "saluti",
            "considerazioni",
            "menzioni",
            "fine",
            "classifica",
            "bonus",
            "sponsor",
        )
        if (
            not cleaned
            or len(cleaned) < 2
            or len(cleaned) > 55
            or c_low in bad_chapter_words
            or any(c_low.startswith(bw + " ") for bw in bad_chapter_words)
            or "guardate tutti" in c_low
        ):
            continue
        items.append(
            {
                "raw_title": cleaned,
                "category": "movie",
                "timestamp": ts,
                "seconds": cd.timestamp_to_seconds(ts),
                "inferred_year": ref_yr,
                "max_video_year": max_yr,
                "is_classic": False,
                "director_hint": "",
            }
        )

    return vid, creator, meta, (items if len(items) >= 3 else [])


def find_matching_movie_key(items_dict, raw_title, target_year=None, dir_hint=""):
    """
    Cerca un film già presente nel Vault verificando che, in caso di omonimi
    (es. 'Superman' 1978 vs 2025, 'Nosferatu' 1922 vs 2024, 'Alien' 1979 vs 2024),
    l'anno o il regista siano compatibili col video del creator!
    """
    tl = raw_title.lower().strip()
    candidates = []
    for k, it in items_dict.items():
        if it.get("category") != "movie":
            continue
        it_t = (it.get("it_title") or "").lower().strip()
        or_t = (it.get("orig_title") or "").lower().strip()
        if tl in (it_t, or_t):
            candidates.append((k, it))

    if not candidates:
        return None

    if dir_hint:
        dh_low = dir_hint.lower()
        for k, it in candidates:
            if dh_low in (it.get("director") or "").lower():
                return k

    if target_year:
        near = [
            (k, it)
            for k, it in candidates
            if isinstance(it.get("year"), int)
            and abs(it["year"] - target_year) <= 2
        ]
        if near:
            return near[0][0]
        # Se ci sono solo classici lontani dall'anno target (es. 1978 vs 2025), NON agganciare al classico!
        if any(
            isinstance(it.get("year"), int) and abs(it["year"] - target_year) > 5
            for _, it in candidates
        ):
            return None

    # Preferisci il candidato più recente se non è specificato altro
    candidates.sort(key=lambda x: x[1].get("year") or 0, reverse=True)
    return candidates[0][0]


def main():
    headers = cd.get_trakt_headers()
    db_data = json.load(open(cd.DB_PATH, encoding="utf-8"))
    watched_imdb = set(db_data.get("watched_imdb", []))
    ratings_imdb = db_data.get("ratings_imdb", {})

    processed_set = set(db_data.get("processed_videos", []))
    all_multi = build_or_load_multi_creator_index()
    total_multi = len(all_multi)

    pending = [
        (idx + 1, entry)
        for idx, entry in enumerate(all_multi)
        if entry["video_id"] not in processed_set
    ]
    print(
        f"📊 Multi-Creator Scanner: {total_multi - len(pending)}/{total_multi} già completati. "
        f"In coda: {len(pending)} video."
    )

    by_it = {
        it["it_title"].lower().strip(): k
        for k, it in db_data["items"].items()
        if it.get("category") == "movie" and it.get("it_title")
    }
    by_orig = {
        it["orig_title"].lower().strip(): k
        for k, it in db_data["items"].items()
        if it.get("category") == "movie" and it.get("orig_title")
    }
    by_imdb = {
        it["imdb_id"]: k
        for k, it in db_data["items"].items()
        if it.get("category") == "movie" and it.get("imdb_id")
    }

    batch_size = 25
    for b_start in range(0, len(pending), batch_size):
        batch = pending[b_start : b_start + batch_size]
        f_idx = batch[0][0]
        l_idx = batch[-1][0]
        cr_name = batch[0][1]["creator"]
        print(
            f"\n--- [{cr_name}] Video #{f_idx}..#{l_idx} / {total_multi} ---"
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda x: process_creator_video(x[1]), batch))

        new_to_enrich = []
        for vid, creator, meta, items in results:
            if not meta:
                continue
            processed_set.add(vid)
            for raw in items:
                explicit_yr = raw.get("inferred_year")
                match_yr = explicit_yr or (
                    raw.get("max_video_year")
                    if len(items) == 1
                    else None
                )
                k = find_matching_movie_key(
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
                    # NON forzare inferred_year=2026 su enrich_movie se il video non ha un anno esplicito!
                    raw["inferred_year"] = explicit_yr
                    new_to_enrich.append((raw, rec))

        if new_to_enrich:
            print(f"    + Arricchisco {len(new_to_enrich)} film consigliati da {cr_name}...")
            with ThreadPoolExecutor(max_workers=8) as pool:
                enriched = list(
                    pool.map(
                        lambda x: (
                            cd.enrich_movie(x[0], headers, {}, check_ch=False),
                            x[1],
                        ),
                        new_to_enrich,
                    )
                )
            for info, rec in enriched:
                tt = info.get("imdb_id")
                if tt and tt in by_imdb and by_imdb[tt] in db_data["items"]:
                    db_data["items"][by_imdb[tt]]["recommendations"].append(rec)
                else:
                    info["recommendations"] = [rec]
                    db_data["items"][info["id"]] = info
                    if tt:
                        by_imdb[tt] = info["id"]
                    by_it[info["it_title"].lower().strip()] = info["id"]

        db_data["processed_videos"] = list(processed_set)
        cd.save_db(db_data)
        cd.generate_html(db_data, watched_imdb, ratings_imdb)
        print(
            f"    💾 Salvato checkpoint multi-creator (#{l_idx}/{total_multi}) — Opere nel Vault: {len(db_data['items'])}"
        )


if __name__ == "__main__":
    main()
