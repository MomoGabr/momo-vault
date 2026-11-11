from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import time
import urllib.parse
import webbrowser

import requests
from youtube_transcript_api import YouTubeTranscriptApi


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "trakt_token.json")
DB_PATH = os.path.join(BASE_DIR, "cine_db.json")
INDEX_5K_PATH = os.path.join(BASE_DIR, "frusciante_5k_index.json")
META_CACHE_PATH = os.path.join(BASE_DIR, "youtube_meta_cache.json")
HTML_PATH = os.path.join(BASE_DIR, "cine_dashboard.html")

YT_COOKIES = {"SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg"}

# Tutte le playlist ufficiali del canale di Federico Frusciante (UCeiW1AdgyfDyW5wPLjZqH2Q)
FRUSCIANTE_PLAYLISTS = [
    ("PLNcd4wyu88zrAmLcWShUIuISdUlbmOEgq", "Meglio e Peggio"),
    ("PLNcd4wyu88zp7QMS1Q8HJYaXYK7Iw1ggH", "I Consigli Musicali di Frusciante"),
    ("PLNcd4wyu88zpmF7wAvsgy9vzMHQ0AubPR", "I Consigli Letterari di Frusciante"),
    ("PLNcd4wyu88zpOp6CZQf3w_Q16IbLMVFJh", "I Classici"),
    ("PLNcd4wyu88zre_-qEpXl2FlG2Shyzcp-r", "Gli Imperdibili"),
    ("PLNcd4wyu88zp4qWIPnAjX_dn7iE0KBGa3", "Frusciante in Oriente"),
    ("PLNcd4wyu88zps7gHc4vdwun1GcL98bxOK", "Frusciante Underground"),
    ("PLNcd4wyu88zr5VPlgEiz7jkLoRksQm700", "Frusciante Underground 2"),
    ("PLNcd4wyu88zq6xu49b7RlfOepAsnUE8ln", "Underground"),
    ("PLNcd4wyu88zqJeG8iyocNvrSXlZOJkCvX", "I consigli di Frusciante: Invisibili"),
    ("PLNcd4wyu88zp5m4S4MENiyzb9HGSye4p-", "I Consigli di Frusciante"),
    ("PLNcd4wyu88zqRwXKw9bau6pxlxOLFIvfR", "Le Monografie di Frusciante"),
    ("PLNcd4wyu88zrudpmmwGVdNyUbksDarzIH", "Le Monografie di Frusciante 2012-2014"),
    ("PLNcd4wyu88zrJzVf_677dSkhjE-g8ENr6", "Le Saghe Cinematografiche"),
    ("PLNcd4wyu88zpz92n561aC-r4eSO2tNJxi", "I Reboot di Frusciante"),
    ("PLNcd4wyu88zqvFwIsu1ntEa2CFdvtqSQ5", "Musica"),
    ("PLNcd4wyu88zpOzVS8h92EuHWvWgb2wAJr", "Frusciante al Cinema"),
    ("PLNcd4wyu88zqtytGpJcQmsR3rs9by1urD", "Le recensioni di Frusciante 2011-2014"),
    ("PLNcd4wyu88zrA3XOuY5274-X9oEom4BHj", "Le recensioni di Frusciante Golden Age"),
]

# Ricerche extra per catturare tutti i video per anno e rubrica (anche quelli fuori playlist)
FRUSCIANTE_SEARCH_QUERIES = [
    "Federico Frusciante Meglio e Peggio",
    "I Consigli Musicali di Frusciante",
    "I Consigli Letterari di Frusciante",
    "I Classici di Frusciante",
    "I Consigli di Frusciante 2023 2024 2025",
    "I Consigli di Frusciante 2020 2021 2022",
    "I Consigli di Frusciante 2017 2018 2019",
    "Le Monografie di Frusciante",
    "Frusciante in Oriente",
    "Gli Imperdibili di Frusciante",
]

# Nei vecchi "Meglio e Peggio" (2013, 2017, 2018, 2020) Frusciante non aveva scritto la parola "PEGGIO:"
# sopra la seconda metà della scaletta: ecco il primo film del blocco PEGGIO per ciascuno di quei video.
MEGLIO_PEGGIO_CUTOFF_TITLES = {
    "JW6R3772Y6k": "attacco al potere",  # Meglio e Peggio 2013 (da 1:42:33 inizia il Peggio)
    "CNNtFujFlE0": "morgan",             # Meglio e Peggio 2017 (da 02:51:00 inizia il Peggio)
    "rQv9FYGLByY": "the nun",            # Meglio e Peggio 2018 (da 04:31:04 inizia il Peggio)
    "P7sYCDFPezM": "dolittle",           # Meglio e Peggio 2020 (da 4:57:28 inizia il Peggio)
}

# Nei Meglio e Peggio 2012 e 2015 i film belli e brutti erano alternati in ordine alfabetico:
# su questi usiamo l'analisi del sentiment nei sottotitoli segmento per segmento!
MEGLIO_PEGGIO_ALTERNATING_VIDS = {"i512c1ihtXE", "k92rXHKo0Ck"}
POS_PATTERNS = [
    r"acquisto obbligato",
    r"accattatev",
    r"capolavor",
    r"filmon",
    r"discon",
    r"libron",
    r"merita assolutamente",
    r"consigliatissim",
    r"della madonna",
    r"bellissim",
    r"straordinari",
    r"imperdibil",
    r"grande film",
    r"gran film",
    r"grande disco",
    r"gran disco",
    r"grande opera",
    r"da recuperare",
    r"da vedere",
    r"promoss",
    r"mi è piaciuto",
    r"film riuscito",
    r"opera straordinaria",
    r"cult",
    r"pietra miliare",
    r"meraviglios",
    r"grandissim",
    r"stupend",
    r"ottim",
    r"bomba",
]

NEG_PATTERNS = [
    r"cagat",
    r"boiat",
    r"schifezz",
    r"orrend",
    r"inascoltabil",
    r"inguardabil",
    r"insopportabil",
    r"tortura",
    r"veramente brutt",
    r"passo falso",
    r"evitate",
    r"state alla larga",
    r"non ci siamo",
    r"delusione",
    r"spazzatura",
    r"porcheri",
    r"roba da non prendere",
    r"bocciat",
    r"falliment",
    r"bruttissim",
    r"pessim",
    r"non funziona",
    r"brutto film",
    r"stroncat",
    r"demolit",
    r"asfaltat",
    r"sfondat",
    r"merda",
]


def load_trakt_credentials():
    env_cid = os.environ.get("TRAKT_CLIENT_ID")
    env_tok = os.environ.get("TRAKT_ACCESS_TOKEN")
    if env_cid and env_tok:
        return env_cid, env_tok
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(f"File credenziali Trakt non trovato: {TOKEN_PATH}")
    with open(TOKEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["client_id"], data["access_token"]


def get_trakt_headers():
    client_id, access_token = load_trakt_credentials()
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id,
        "Authorization": f"Bearer {access_token}",
    }


def timestamp_to_seconds(ts_str):
    if not ts_str:
        return 0
    parts = [int(p) for p in ts_str.strip().split(":") if p.isdigit()]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def score_frusciante_verdict(text):
    low = text.lower()
    pos_hits = [p for p in POS_PATTERNS if re.search(p, low)]
    neg_hits = [n for n in NEG_PATTERNS if re.search(n, low)]
    score = len(pos_hits) - (len(neg_hits) * 1.5)
    return score, pos_hits, neg_hits


def discover_frusciante_videos():
    """
    Scopre automaticamente centinaia di video da tutte le playlist ufficiali
    del canale di Federico Frusciante + ricerche recenti.
    """
    discovered = []
    seen = set()

    def fetch_playlist(pid_label):
        pid, label = pid_label
        url = f"https://www.youtube.com/playlist?list={pid}"
        try:
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                cookies=YT_COOKIES,
                timeout=15,
            )
            vids = list(
                dict.fromkeys(
                    re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
                )
            )
            return label, vids
        except Exception:
            return label, []

    with ThreadPoolExecutor(max_workers=6) as pool:
        for label, vids in pool.map(fetch_playlist, FRUSCIANTE_PLAYLISTS):
            for v in vids:
                if v not in seen:
                    seen.add(v)
                    discovered.append((v, "Federico Frusciante", label))

    for q in FRUSCIANTE_SEARCH_QUERIES:
        try:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)
            r = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                cookies=YT_COOKIES,
                timeout=15,
            )
            for m in re.finditer(
                r'"videoRenderer":\{"videoId":"([a-zA-Z0-9_-]{11})"', r.text
            ):
                vid = m.group(1)
                if vid not in seen:
                    seen.add(vid)
                    discovered.append((vid, "Federico Frusciante", "Recenti"))
        except Exception:
            pass

    return discovered


def detect_category_and_format(video_title, description, playlist_hint=""):
    t_low = video_title.lower()
    d_low = description.lower()
    p_low = playlist_hint.lower()

    # Formato del video
    if (
        "meglio e peggio" in t_low
        or "meglio e il peggio" in t_low
        or "meglio del peggio" in t_low
        or "\npeggio\n" in d_low
    ):
        v_format = "meglio_peggio"
    elif (
        any(
            k in t_low
            for k in (
                "consigli",
                "i classici",
                "imperdibili",
                "in oriente",
                "underground",
                "invisibili",
            )
        )
        or any(
            k in p_low
            for k in (
                "consigli",
                "classici",
                "imperdibili",
                "oriente",
                "underground",
            )
        )
    ):
        v_format = "consigli"
    elif (
        "monografi" in t_low
        or "monografi" in p_low
        or "le recensioni di frusciante -" in t_low
        or "saghe" in p_low
    ):
        v_format = "monografia"
    else:
        v_format = "single_review"

    # Categoria (movie / music / book)
    if (
        any(k in t_low for k in ("musicali", "dischi", "album", "musica"))
        or "lista dei dischi" in d_low
        or "musica" in p_low
    ):
        cat = "music"
    elif (
        any(k in t_low for k in ("letterari", "libri", "letture"))
        or "lista dei libri" in d_low
        or "letterari" in p_low
    ):
        cat = "book"
    else:
        cat = "movie"

    if v_format == "single_review" and " di " in t_low and "al cinema" in t_low:
        cat = "movie"

    return cat, v_format


def get_video_metadata(video_id, playlist_hint=""):
    """
    Usa l'endpoint JSON leggero YouTube Innertube (/youtubei/v1/next)
    che non soffre dei blocchi rate-limit di /player o delle pagine HTML.
    """
    ctx = {
        "client": {
            "clientName": "WEB",
            "clientVersion": "2.20250101.00.00",
            "hl": "it",
            "gl": "IT",
        }
    }
    title = ""
    desc = ""
    length_sec = 0
    comment_token = ""

    try:
        r_next = requests.post(
            "https://www.youtube.com/youtubei/v1/next?prettyPrint=false",
            json={"videoId": video_id, "context": ctx},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if r_next.status_code == 200:
            raw_txt = r_next.text
            m_title = re.search(
                r'"videoPrimaryInfoRenderer":\{"title":\{"runs":\[\{"text":"((?:\\.|[^"\\])*)"',
                raw_txt,
            )
            if m_title:
                title = json.loads(f'"{m_title.group(1)}"')
            m_desc = re.search(
                r'"attributedDescriptionBodyText":\{"content":"((?:\\.|[^"\\])*)"',
                raw_txt,
            )
            if m_desc:
                desc = json.loads(f'"{m_desc.group(1)}"')
            m_tok = re.search(
                r'"continuationCommand":\{"token":"([^"]+)"', raw_txt
            )
            if m_tok:
                comment_token = json.loads(f'"{m_tok.group(1)}"')
    except Exception:
        pass

    if not title:
        resp = requests.post(
            "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
            json={"videoId": video_id, "context": ctx},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        vd = resp.json().get("videoDetails", {})
        title = vd.get("title") or ""
        desc = vd.get("shortDescription") or ""
        length_sec = int(vd.get("lengthSeconds") or 0)

    if not title:
        return None
    cat, v_format = detect_category_and_format(title, desc, playlist_hint)

    # Estrai l'anno massimo possibile dal titolo del video (es. un video del 2019 non può parlare di un film del 2023!)
    all_years_in_title = [int(y) for y in re.findall(r"\b(20\d{2})\b", title) if int(y) >= 2006]
    max_video_year = max(all_years_in_title) if all_years_in_title else 2026

    inferred_year = None
    is_classic = "classici" in title.lower() or "classici" in playlist_hint.lower()
    is_decade_range = "decennio" in title.lower() or bool(
        re.search(r"\b(?:19|20)\d{2}\s*[-–/]\s*(?:19|20)\d{2}\b", title)
    )
    if not is_classic and not is_decade_range:
        if v_format == "meglio_peggio":
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", title)
            if year_match:
                inferred_year = int(year_match.group(1))
        elif v_format == "single_review":
            # Nei single_review l'anno del film è tra parentesi, es. "(2023)", per non confonderlo con "Fear Street 1978" o "1917"
            year_match = re.search(r"\((?:[^\)]*\b)?(19\d{2}|20\d{2})\)", title)
            if year_match:
                inferred_year = int(year_match.group(1))

    return {
        "video_id": video_id,
        "title": title,
        "author": "Federico Frusciante",
        "description": desc,
        "comment_token": comment_token,
        "length_seconds": length_sec,
        "inferred_year": inferred_year,
        "max_video_year": max_video_year,
        "is_classic": is_classic,
        "category": cat,
        "format": v_format,
    }


def extract_timestamped_lines(
    description,
    category,
    inferred_year=None,
    video_id="",
    is_classic=False,
    max_video_year=2026,
    director_hint="",
):
    if not description:
        return []
    items = []
    in_negative = False
    current_cat = category
    ts_pattern = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
    cutoff_prefix = MEGLIO_PEGGIO_CUTOFF_TITLES.get(video_id)

    for raw_line in description.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper().strip(": -►•*")
        if upper in {"PEGGIO", "IL PEGGIO", "FLOP", "SCONSIGLIATI", "I PEGGIORI"}:
            in_negative = True
            continue
        if upper in {"MEGLIO", "IL MEGLIO", "TOP", "CONSIGLIATI", "I MIGLIORI"}:
            in_negative = False
            continue
        if not ts_pattern.search(line):
            if re.match(r"^(?:DISCH|DISCO|MUSIC|ALBUM)", upper):
                current_cat = "music"
                continue
            if re.match(r"^(?:LIBR|LETTUR)", upper):
                current_cat = "book"
                continue
            if re.match(r"^(?:LISTA DEI FILM|FILM)", upper):
                current_cat = "movie"
                continue
        if in_negative:
            continue

        ts_match = ts_pattern.search(line)
        if not ts_match:
            continue
        timestamp = ts_match.group(1)

        url_match = re.search(r"(https?://\S+)", line)
        amazon_url = url_match.group(1) if url_match else ""

        cleaned = re.sub(r"https?://\S+", "", line)
        cleaned = cleaned.replace(timestamp, "")
        cleaned = re.sub(r"[►•*]+", " ", cleaned)
        cleaned = re.sub(r"\s*-\s*$", "", cleaned)
        cleaned = re.sub(r"^\s*-\s*", "", cleaned).strip(" -–—:•\t")
        cleaned = re.sub(r"\s*[-–—]?\s*\(\s*\)\s*$", "", cleaned).strip(" -–—:•\t")
        if not cleaned or len(cleaned) < 2 or "(?)" in cleaned:
            continue
        c_low = cleaned.lower()
        if c_low in {
            "intro",
            "introduzione",
            "outro",
            "conclusioni",
            "saluti",
        } or any(
            bad in c_low
            for bad in (
                "seguimi in live",
                "attenzione 2:",
                "prevendita",
                "come nasce il meglio e il peggio",
                "non ci sono più vie di mezzo",
                "non si discute più",
                "il talento di frusciante",
                "filmografia cinema di",
            )
        ):
            continue

        # Nei Meglio e Peggio 2013/2017/2018/2020 senza scritta "PEGGIO", fermati al primo film del Peggio!
        if cutoff_prefix and cleaned.lower().startswith(cutoff_prefix):
            in_negative = True
            continue

        # Se nella riga stessa c'è un anno tra parentesi es. "Brother (2001) Takeshi Kitano", estrai sia l'anno sia il regista!
        item_year = inferred_year
        line_director = director_hint
        ym = re.search(r"\((19\d{2}|20\d{2})\)", cleaned)
        if ym and current_cat != "music":
            item_year = int(ym.group(1))
            before_year = cleaned[: ym.start()].strip(" -–—")
            after_year = cleaned[ym.end() :].strip(" -–—")
            if after_year and len(after_year) >= 3:
                line_director = after_year
            if len(before_year) >= 2:
                cleaned = before_year
            else:
                cleaned = re.sub(
                    r"\(\s*(?:19\d{2}|20\d{2})\s*\)", "", cleaned
                ).strip()

        items.append(
            {
                "raw_title": cleaned,
                "category": current_cat,
                "timestamp": timestamp,
                "seconds": timestamp_to_seconds(timestamp),
                "inferred_year": item_year,
                "max_video_year": item_year or max_video_year,
                "is_classic": is_classic,
                "director_hint": line_director,
                "amazon_url": amazon_url,
            }
        )

    # Fallback per i video storici 2011-2013 ("Le Recensioni di Frusciante - Tarantino/Carpenter...")
    # dove sotto "Lista dei films citati:" c'è "Titolo (1974)" o "Titolo - 1992" senza timestamp MM:SS!
    if not items and "lista dei film" in description.lower():
        after_header = re.split(
            r"lista dei films?\s+citati\s*:", description, flags=re.I
        )[-1]
        for raw_line in after_header.splitlines():
            line = raw_line.strip(" -•*►\t")
            if not line or line.upper().startswith("DISCLAIMER"):
                break
            ym = re.search(r"(?:\(\s*(19\d{2}|20\d{2})\s*\)|-\s*(19\d{2}|20\d{2})\b)", line)
            if ym:
                yr = int(ym.group(1) or ym.group(2))
                t_part = line[: ym.start()].strip(" -–—:")
                if len(t_part) >= 2 and "frusciante" not in t_part.lower():
                    items.append(
                        {
                            "raw_title": t_part,
                            "category": category,
                            "timestamp": "00:00",
                            "seconds": 0,
                            "inferred_year": yr,
                            "max_video_year": yr,
                            "is_classic": yr <= 2000,
                            "director_hint": director_hint,
                            "amazon_url": "",
                        }
                    )
    return items


def filter_segments_by_sentiment(video_id, meta, ts_items):
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["it"])
    except Exception:
        with_amz = [it for it in ts_items if it.get("amazon_url")]
        return with_amz if with_amz else ts_items

    approved = []
    total_len = meta["length_seconds"] or (
        int(transcript[-1].start) + 60 if transcript else 0
    )
    for idx, item in enumerate(ts_items):
        start_s = item["seconds"]
        end_s = (
            ts_items[idx + 1]["seconds"]
            if idx + 1 < len(ts_items)
            else total_len
        )
        win_start = max(start_s, end_s - 100)
        seg_text = " ".join(
            s.text for s in transcript if win_start <= s.start <= end_s
        )
        score, _, _ = score_frusciante_verdict(seg_text)
        if score > 0:
            approved.append(item)
    return approved


def extract_positive_items_from_video(video_id, meta, verify_transcripts=True):
    v_format = meta["format"]
    cat = meta["category"]
    desc = meta["description"]
    inferred_year = meta["inferred_year"]
    is_classic = meta.get("is_classic", False)

    # Ignora video puramente di "Peggio" (es. "Il Meglio del Peggio")
    if "meglio del peggio" in meta["title"].lower():
        return []

    ts_items = extract_timestamped_lines(
        desc,
        cat,
        inferred_year,
        video_id=video_id,
        is_classic=is_classic,
        max_video_year=meta.get("max_video_year", 2026),
        director_hint=extract_director_hint_from_video_title(meta["title"]),
    )

    # Nei Meglio e Peggio 2012 e 2015 i film belli e brutti sono alternati -> filtra coi sottotitoli!
    if video_id in MEGLIO_PEGGIO_ALTERNATING_VIDS and ts_items:
        return filter_segments_by_sentiment(video_id, meta, ts_items)

    # Caso 1: Rubriche 100% positive e Meglio & Peggio (già tagliati prima del blocco PEGGIO)
    if v_format in ("consigli", "meglio_peggio") and ts_items:
        return ts_items

    # Caso 2: Monografia con scaletta in descrizione
    if v_format == "monografia" and ts_items:
        if not verify_transcripts:
            return ts_items
        return filter_segments_by_sentiment(video_id, meta, ts_items)

    # Caso 3: Recensione singola (Frusciante al Cinema / Patreon Minirece)
    if ts_items and len(ts_items) >= 2:
        return ts_items

    if not verify_transcripts:
        return []

    # Usa i top 20 commenti via /youtubei/v1/next (non soffre MAI del blocco IP 429 dei sottotitoli!)
    verdict_text = ""
    comment_tok = meta.get("comment_token", "")
    if comment_tok:
        try:
            ctx = {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20250101.00.00",
                    "hl": "it",
                    "gl": "IT",
                }
            }
            rc = requests.post(
                "https://www.youtube.com/youtubei/v1/next?prettyPrint=false",
                json={"continuation": comment_tok, "context": ctx},
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
                verdict_text = " ".join(comments)
        except Exception:
            pass

    if not verdict_text:
        return []

    score, _, _ = score_frusciante_verdict(verdict_text)
    if score <= 0:
        return []

    # Rileva dai commenti (e dal titolo) se la minirece Patreon è un Film o un Disco Musicale!
    v_low = verdict_text.lower()
    music_hits = len(
        re.findall(
            r"\b(disco|album|brani|canzoni|band|ascolt|musica|pezzi|chitarra|voce|riff)\b",
            v_low,
        )
    )
    movie_hits = len(
        re.findall(
            r"\b(film|regista|regia|cinema|pellicola|attor|scen|serie|stagione|anime|episod)\b",
            v_low,
        )
    )
    if re.search(r"\(\d{4}\)\s+di\s+", meta["title"], re.I) or movie_hits > music_hits:
        cat = "movie"
    elif music_hits > movie_hits and music_hits >= 2:
        cat = "music"
    else:
        cat = "movie"

    subject_title = ""
    amazon_url = ""
    director_from_title = ""

    # Estrai eventuale regista/artista dal titolo del video es. "Patreon: Titolo (1989) di Nanni Moretti - Minirece..."
    m_dir = re.search(
        r"\(\d{4}\)\s*(?:di|-)\s*([^-(\n]+?)(?:\s*-\s*(?:minirece|richiest|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|gennaio)|$)",
        meta["title"],
        re.I,
    )
    if m_dir:
        director_from_title = m_dir.group(1).strip()

    m_desc = re.search(
        r"Lista dei (?:film|dischi|libri) citati:\s*\n\s*([^\n►]+)(?:►\s*(https?://\S+))?",
        desc,
        re.I,
    )
    if m_desc:
        subject_title = m_desc.group(1).strip(" -•*")
        # Rimuovi eventuale "(2013) di Bong Joon-ho" scritto anche dentro la descrizione
        subject_title = re.sub(r"\(\s*(?:19\d{2}|20\d{2})\s*\).*$", "", subject_title).strip(" -–—")
        amazon_url = m_desc.group(2) or ""
    if not subject_title:
        # Accetta dal titolo del video SOLO se è una vera recensione singola (con "Patreon:", "Frusciante al Cinema:", "Minirece" e un anno "(YYYY)")
        if not re.search(r"\((?:19\d{2}|20\d{2})\)", meta["title"]):
            return []
        t_clean = re.sub(
            r"^(?:patreon|frusciante al cinema|minirece[^\:]*)\s*:\s*",
            "",
            meta["title"],
            flags=re.I,
        )
        t_clean = re.sub(r"\(\d{4}\).*$", "", t_clean).strip(" -")
        subject_title = t_clean

    bad_titles = {"le recensioni", "frusciante", "best of", "il meglio"}
    if (
        not subject_title
        or len(subject_title) < 2
        or any(b in subject_title.lower() for b in bad_titles)
    ):
        return []

    # Se è musica e abbiamo l'artista dal titolo, formattalo come "Album - Artista"
    if cat == "music" and director_from_title and director_from_title.lower() not in subject_title.lower():
        subject_title = f"{subject_title} - {director_from_title}"

    return [
        {
            "raw_title": subject_title,
            "category": cat,
            "timestamp": "00:00",
            "seconds": 0,
            "inferred_year": inferred_year,
            "max_video_year": inferred_year or meta.get("max_video_year", 2026),
            "is_classic": bool(inferred_year and inferred_year <= 2000),
            "director_hint": director_from_title if cat == "movie" else "",
            "amazon_url": amazon_url,
        }
    ]


def resolve_amazon_asin_cover(amazon_url):
    if not amazon_url:
        return "", ""
    try:
        r = requests.head(
            amazon_url,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", r.url)
        if m:
            asin = m.group(1)
            img = f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg"
            return img, r.url
    except Exception:
        pass
    return "", amazon_url


DIRECTOR_ALIASES = {
    "fulci": "Lucio Fulci",
    "lucio fulci": "Lucio Fulci",
    "argento": "Dario Argento",
    "dario argento": "Dario Argento",
    "cronenberg": "David Cronenberg",
    "david cronenberg": "David Cronenberg",
    "burton": "Tim Burton",
    "tim burton": "Tim Burton",
    "raimi": "Sam Raimi",
    "sam raimi": "Sam Raimi",
    "carpenter": "John Carpenter",
    "john carpenter": "John Carpenter",
    "tarantino": "Quentin Tarantino",
    "quentin tarantino": "Quentin Tarantino",
    "leone": "Sergio Leone",
    "sergio leone": "Sergio Leone",
    "nolan": "Christopher Nolan",
    "christopher nolan": "Christopher Nolan",
    "zombie": "Rob Zombie",
    "rob zombie": "Rob Zombie",
    "kim jee": "Kim Jee-woon",
    "kim jee-woon": "Kim Jee-woon",
    "m. l. lester": "Mark L. Lester",
    "mark l. lester": "Mark L. Lester",
    "j. carpenter": "John Carpenter",
    "s. kubrick": "Stanley Kubrick",
    "stanley kubrick": "Stanley Kubrick",
    "m. scorsese": "Martin Scorsese",
    "martin scorsese": "Martin Scorsese",
    "b. de palma": "Brian De Palma",
    "brian de palma": "Brian De Palma",
    "w. hill": "Walter Hill",
    "walter hill": "Walter Hill",
    "s. peckinpah": "Sam Peckinpah",
    "sam peckinpah": "Sam Peckinpah",
    "g. a. romero": "George A. Romero",
    "george a. romero": "George A. Romero",
    "d. lynch": "David Lynch",
    "david lynch": "David Lynch",
    "a. hitchcock": "Alfred Hitchcock",
    "alfred hitchcock": "Alfred Hitchcock",
    "r. polanski": "Roman Polanski",
    "roman polanski": "Roman Polanski",
    "w. friedkin": "William Friedkin",
    "william friedkin": "William Friedkin",
    "m. bava": "Mario Bava",
    "mario bava": "Mario Bava",
}

NON_DIRECTOR_PHRASES = (
    "meglio e peggio",
    "meglio del peggio",
    "morte al cinema",
    "scifi",
    "sci-fi",
    "san valentino",
    "8 marzo",
    "frusciante",
    "canale nuovo",
    "golden age",
    "licaoni",
    "action",
    "porno",
    "nerd",
    "critica",
    "classici",
    "consigli",
    "imperdibili",
    "oriente",
    "underground",
    "saghe",
    "invisibili",
    "interviste",
    "reboot",
    "cinematograf",
)


def normalize_director_name(raw_dir):
    if not raw_dir:
        return ""
    cleaned = re.sub(r"\b(?:pt|parte|part)\.?\s*[0-9ivx]+\b", "", raw_dir, flags=re.I)
    cleaned = re.sub(r"\(\s*\d+\s*di\s*\d+\s*\)", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" -–—:.,/()")
    low = cleaned.lower()
    if not cleaned or len(cleaned) < 3 or len(cleaned) > 32:
        return ""
    if any(bad in low for bad in NON_DIRECTOR_PHRASES):
        return ""
    if re.search(r"\d", cleaned):
        return ""
    if low in DIRECTOR_ALIASES:
        return DIRECTOR_ALIASES[low]
    return cleaned


def extract_director_hint_from_video_title(video_title):
    """
    Se il video è una Monografia (es. 'Le Monografie di Frusciante: Takeshi Kitano (Luglio 2019)'
    o 'Le Recensioni di Frusciante - Mario Bava'), estrae il nome pulito del regista!
    """
    m = re.search(
        r"(?:monografie|recensioni)\s+di\s+frusciante\s*[:\-]+\s*([^\(\-\n]+)",
        video_title,
        re.I,
    )
    if m:
        return normalize_director_name(m.group(1))
    return ""


WIKI_HEADERS = {
    "User-Agent": "MomoCineVault/1.0 (https://github.com/mohamedgabr; thedream.cairo@gmail.com)"
}


def resolve_imdb_via_wikipedia_wikidata(
    it_title, director_hint="", is_classic=False, max_video_year=2026, ref_year=None
):
    """
    Usa Wikipedia Italia + English Wikipedia + Wikidata (proprietà P345 = IMDb ID) per trovare
    l'IMDb ID esatto del film, verificando titolo, regista e compatibilità dell'anno!
    """
    clean_title = re.sub(r"\s*\(\d{4}\)\s*", "", it_title).strip()
    clean_title = re.sub(r"\s*[-–—]?\s*\(\s*\)\s*$", "", clean_title).strip()
    first_part = re.split(r"\s*[-–—:]\s*", clean_title)[0].strip()
    ct_alnum = re.sub(r"\W+", "", clean_title.lower())
    fp_alnum = re.sub(r"\W+", "", first_part.lower())

    year_str = str(ref_year) if ref_year else ""
    queries = [
        ("it", f'intitle:"{clean_title}" {director_hint} {year_str} film'.strip()),
        ("it", f'intitle:"{clean_title}" {director_hint} film'.strip()),
        ("it", f'intitle:"{first_part}" {director_hint} film'.strip()),
        ("en", f'intitle:"{first_part}" {director_hint} film'.strip()),
    ]
    seen_q = set()
    for lang, q in queries:
        if (lang, q) in seen_q:
            continue
        seen_q.add((lang, q))
        try:
            r = None
            for attempt in range(2):
                r = requests.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": q,
                        "gsrlimit": 10,
                        "prop": "pageprops",
                        "ppprop": "wikibase_item",
                        "format": "json",
                    },
                    headers=WIKI_HEADERS,
                    timeout=8,
                )
                if r.status_code == 429:
                    time.sleep(0.6 * (attempt + 1))
                    continue
                break
            if not r or r.status_code != 200:
                continue
            pages = sorted(
                r.json().get("query", {}).get("pages", {}).values(),
                key=lambda x: x.get("index", 99),
            )
            qids = []
            for p in pages:
                pt = p.get("title", "").lower()
                if "disambigua" in pt or "disambiguation" in pt:
                    continue
                m_py = re.search(r"\((?:[^\)]*\s+)?(19\d{2}|20\d{2})(?:\s+film)?\)", pt)
                if m_py and ref_year and abs(int(m_py.group(1)) - ref_year) > 2:
                    continue
                if m_py and int(m_py.group(1)) > max_video_year:
                    continue
                pt_base = re.sub(r"\s*\(.*?\)", "", pt).strip()
                pt_alnum = re.sub(r"\W+", "", pt_base)
                # Accetta match esatto sul titolo o sul prefisso prima del sottotitolo/regista
                if (
                    pt_alnum not in (ct_alnum, fp_alnum)
                    and not pt_base.startswith(first_part.lower() + " -")
                    and not pt_base.startswith(first_part.lower() + " di ")
                ):
                    continue
                q_item = p.get("pageprops", {}).get("wikibase_item")
                if q_item:
                    qids.append(q_item)

            if not qids:
                continue

            wd = requests.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(qids[:4]),
                    "props": "claims",
                    "format": "json",
                },
                headers=WIKI_HEADERS,
                timeout=8,
            ).json()

            for qid in qids[:4]:
                claims = wd.get("entities", {}).get(qid, {}).get("claims", {})
                if "P345" in claims:
                    imdb_val = (
                        claims["P345"][0]
                        .get("mainsnak", {})
                        .get("datavalue", {})
                        .get("value", "")
                    )
                    if imdb_val.startswith("tt"):
                        return imdb_val
        except Exception:
            pass
    return None


def enrich_movie(item, headers, ch_sources_map, check_ch=True):
    title = item["raw_title"]
    is_classic = item.get("is_classic", False)
    ref_year = item.get("inferred_year")
    max_video_year = item.get("max_video_year") or ref_year or 2026
    director_hint = item.get("director_hint", "")

    imdb_id = None
    orig_title = title
    year = ref_year
    poster_url = ""
    media_type = "movies"
    cast = ""

    # 1. Prova prima risoluzione esatta tramite Wikipedia IT -> Wikidata P345 (IMDb ID)
    if True:
        wiki_imdb = resolve_imdb_via_wikipedia_wikidata(
            title,
            director_hint=director_hint,
            is_classic=is_classic,
            max_video_year=max_video_year,
            ref_year=ref_year,
        )
        if wiki_imdb:
            try:
                r_tt = requests.get(
                    f"https://v3.sg.media-imdb.com/suggestion/x/{wiki_imdb}.json",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=8,
                )
                if r_tt.status_code == 200:
                    d_list = r_tt.json().get("d", [])
                    if d_list:
                        best = d_list[0]
                        cand_y = best.get("y")
                        min_allowed_year = 1895 if (is_classic or (ref_year and ref_year < 1930)) else 1930
                        year_ok = (not isinstance(cand_y, int)) or (
                            min_allowed_year <= cand_y <= max_video_year
                            and (not ref_year or abs(cand_y - ref_year) <= 2)
                        )
                        if year_ok:
                            imdb_id = wiki_imdb
                            orig_title = best.get("l") or title
                            year = cand_y or year
                            cast = best.get("s") or ""
                            img = best.get("i", {}).get("imageUrl", "")
                            if img:
                                poster_url = re.sub(
                                    r"\._V1_.*\.jpg$", "._V1_UX400_.jpg", img
                                )
                            media_type = (
                                "shows"
                                if best.get("qid") in ("tvMiniSeries", "tvSeries")
                                else "movies"
                            )
            except Exception:
                pass

    # 2. Se Wikidata non ha trovato l'ID (o il film è recentissimo e non su Wiki IT), usa IMDb Suggestion
    if not imdb_id:
        search_term = re.sub(r"\bpt\.?\s*(\d+)", r"parte \1", title, flags=re.I)
        search_term = re.sub(r"\s*[-–—]?\s*\(\s*\)\s*$", "", search_term).strip()
        # Se il titolo ha "Titolo - Sottotitolo", prova sia la prima parte sia la seconda se >20 caratteri
        terms_to_try = [search_term[:20]]
        if len(search_term) > 20 and re.search(r"\s*[-–—]\s*", search_term):
            parts = [
                p.strip()
                for p in re.split(r"\s*[-–—]\s*", search_term)
                if len(p.strip()) >= 3
            ]
            if parts:
                terms_to_try = [parts[0][:20], parts[-1][:20]]
        if ref_year:
            terms_to_try.append(f"{search_term[:16]} {ref_year}")
            terms_to_try.append(f"{search_term[:16]} {ref_year - 1}")
            terms_to_try.append(f"{search_term[:16]} {ref_year - 2}")
        if director_hint:
            terms_to_try.append(f"{search_term[:15]} {director_hint.split()[-1]}")

        for st in dict.fromkeys(terms_to_try):
            query = urllib.parse.quote(st.lower().strip())
            imdb_url = f"https://v3.sg.media-imdb.com/suggestion/x/{query}.json"
            try:
                r = requests.get(
                    imdb_url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept-Language": "it-IT,it;q=0.9",
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    valid_qids = (
                        ("movie", "tvMovie", "short")
                        if is_classic
                        else ("movie", "tvMovie", "short", "tvMiniSeries", "tvSeries")
                    )
                    candidates = [
                        d
                        for d in r.json().get("d", [])
                        if d.get("qid") in valid_qids
                        and str(d.get("id", "")).startswith("tt")
                    ]
                    # Scarta i corti/programmi amatoriali privi di locandina su IMDb (che danno 404 su Trakt!)
                    with_poster = [
                        c for c in candidates if c.get("i", {}).get("imageUrl")
                    ]
                    if with_poster:
                        candidates = with_poster

                    time_valid = [
                        c
                        for c in candidates
                        if isinstance(c.get("y"), int) and min_allowed_year <= c["y"] <= max_video_year
                    ]
                    if time_valid:
                        candidates = time_valid

                    if is_classic:
                        candidates = [
                            c
                            for c in candidates
                            if isinstance(c.get("y"), int) and c["y"] <= 2005
                        ] or candidates

                    if candidates:
                        exact_matches = [
                            c
                            for c in candidates
                            if (c.get("l") or "").strip().lower()
                            in (title.strip().lower(), st.strip().lower())
                        ]
                        pool = exact_matches if exact_matches else candidates

                        if ref_year:
                            near = [
                                c
                                for c in pool
                                if isinstance(c.get("y"), int)
                                and (ref_year - 2) <= c["y"] <= (ref_year + 1)
                            ]
                            if not near:
                                near = [
                                    c
                                    for c in candidates
                                    if isinstance(c.get("y"), int)
                                    and (ref_year - 2) <= c["y"] <= (ref_year + 1)
                                ]
                            best = near[0] if near else None
                        else:
                            best = pool[0]

                        if best:
                            imdb_id = best["id"]
                            orig_title = best.get("l") or orig_title
                            year = best.get("y") or year
                            cast = best.get("s") or ""
                            img = best.get("i", {}).get("imageUrl", "")
                            if img:
                                poster_url = re.sub(
                                    r"\._V1_.*\.jpg$", "._V1_UX400_.jpg", img
                                )
                            media_type = (
                                "shows"
                                if best.get("qid") in ("tvMiniSeries", "tvSeries")
                                else "movies"
                            )
                            break
            except Exception:
                pass

    # 3. Se ancora non trovato e abbiamo le credenziali Trakt, cerca sul motore TMDB/Trakt
    if not imdb_id and headers:
        try:
            q_trakt = re.sub(r"\s*[-–—]?\s*\(\s*\)\s*$", "", title).strip()
            r_tk = requests.get(
                "https://api.trakt.tv/search/movie",
                params={"query": q_trakt},
                headers=headers,
                timeout=10,
            )
            if r_tk.status_code == 200:
                min_allowed_year = 1895 if (is_classic or (ref_year and ref_year < 1930)) else 1930
                tk_cands = []
                q_alnum = re.sub(r"\W+", "", q_trakt.lower())
                for row in r_tk.json():
                    mv = row.get("movie") or {}
                    tt = (mv.get("ids") or {}).get("imdb")
                    my = mv.get("year")
                    mt = mv.get("title") or ""
                    if not tt or not str(tt).startswith("tt"):
                        continue
                    if isinstance(my, int) and not (min_allowed_year <= my <= max_video_year):
                        continue
                    if ref_year and isinstance(my, int) and abs(my - ref_year) > 2:
                        continue
                    if not ref_year and re.sub(r"\W+", "", mt.lower()) != q_alnum:
                        continue
                    tk_cands.append((tt, mt or title, my))
                if tk_cands:
                    imdb_id, orig_title, year = tk_cands[0][0], tk_cands[0][1], tk_cands[0][2] or year
                    try:
                        r_tt = requests.get(
                            f"https://v3.sg.media-imdb.com/suggestion/x/{imdb_id}.json",
                            headers={"User-Agent": "Mozilla/5.0"},
                            timeout=8,
                        )
                        if r_tt.status_code == 200 and r_tt.json().get("d"):
                            b0 = r_tt.json()["d"][0]
                            cast = b0.get("s") or ""
                            img = b0.get("i", {}).get("imageUrl", "")
                            if img:
                                poster_url = re.sub(r"\._V1_.*\.jpg$", "._V1_UX400_.jpg", img)
                    except Exception:
                        pass
        except Exception:
            pass

    if not poster_url and item.get("amazon_url"):
        poster_url, _ = resolve_amazon_asin_cover(item["amazon_url"])

    ch_flatrate = []
    it_flatrate = []
    if imdb_id and check_ch:
        try:
            wn_url = f"https://api.trakt.tv/{media_type}/{imdb_id}/watchnow"
            wn_resp = requests.get(wn_url, headers=headers, timeout=10)
            if wn_resp.status_code == 200:
                wn_json = wn_resp.json()
                for c_code, target_list in (("ch", ch_flatrate), ("it", it_flatrate)):
                    c_data = wn_json.get(c_code, {})
                    seen_flat = set()
                    for bucket in ("subscription", "free"):
                        for offer in c_data.get(bucket, []):
                            src = offer.get("source")
                            if src and src not in seen_flat:
                                seen_flat.add(src)
                                meta = ch_sources_map.get(src, {})
                                target_list.append(
                                    {
                                        "source": src,
                                        "name": meta.get(
                                            "name", src.replace("_", " ").title()
                                        ),
                                        "link": "https://" + offer["link"].lstrip("/")
                                        if offer.get("link")
                                        else "",
                                    }
                                )
        except Exception:
            pass

    final_id = (
        f"movie:{title.lower()}:{imdb_id}"
        if imdb_id
        else f"movie:{title.lower()}:{'classic' if is_classic else (year or 'any')}"
    )
    return {
        "id": final_id,
        "imdb_id": imdb_id,
        "category": "movie",
        "it_title": title,
        "orig_title": orig_title,
        "year": year,
        "cast": cast,
        "poster_url": poster_url,
        "media_type": "show" if media_type == "shows" else "movie",
        "ch_flatrate": ch_flatrate,
        "it_flatrate": it_flatrate,
        "external_url": f"https://app.trakt.tv/{'shows' if media_type == 'shows' else 'movies'}/{imdb_id}"
        if imdb_id
        else "",
    }


def enrich_music(item):
    raw = item["raw_title"]
    year = None
    ym = re.search(r"\((19\d{2}|20\d{2})\)", raw)
    if ym:
        year = int(ym.group(1))
        raw_no_year = re.sub(r"\(\s*(?:19\d{2}|20\d{2})\s*\)", "", raw).strip()
    else:
        raw_no_year = raw

    parts = [p.strip() for p in raw_no_year.split(" - ") if p.strip()]
    album_title = parts[0] if parts else raw_no_year
    artist = parts[1] if len(parts) > 1 else ""

    poster_url = ""
    genre = ""
    apple_url = ""
    try:
        term = f"{album_title} {artist}".strip()
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": term, "entity": "album", "limit": 1},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                top = results[0]
                art = top.get("artworkUrl100", "")
                if art:
                    poster_url = art.replace("100x100bb.jpg", "600x600bb.jpg")
                artist = artist or top.get("artistName", "")
                genre = top.get("primaryGenreName", "")
                apple_url = top.get("collectionViewUrl", "")
                if not year and top.get("releaseDate"):
                    year = int(top["releaseDate"][:4])
    except Exception:
        pass

    if not poster_url and item.get("amazon_url"):
        poster_url, _ = resolve_amazon_asin_cover(item["amazon_url"])

    spotify_q = urllib.parse.quote(f"{album_title} {artist}".strip())
    return {
        "id": f"music:{album_title.lower()}:{artist.lower()}",
        "category": "music",
        "it_title": album_title,
        "orig_title": artist,
        "year": year,
        "cast": genre,
        "poster_url": poster_url,
        "ch_flatrate": [],
        "external_url": f"https://open.spotify.com/search/{spotify_q}",
        "apple_url": apple_url,
    }


def enrich_book(item):
    raw = item["raw_title"]
    poster_url, full_amz = resolve_amazon_asin_cover(item.get("amazon_url", ""))
    author = ""
    year = item.get("inferred_year")

    try:
        r = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": raw, "maxResults": 1},
            timeout=10,
        )
        if r.status_code == 200:
            items = r.json().get("items") or []
            if items:
                vi = items[0].get("volumeInfo", {})
                authors = vi.get("authors") or []
                if authors:
                    author = ", ".join(authors)
                pub = vi.get("publishedDate", "")
                if pub[:4].isdigit():
                    year = int(pub[:4])
                if not poster_url:
                    thumb = vi.get("imageLinks", {}).get("thumbnail", "")
                    if thumb:
                        poster_url = thumb.replace("http://", "https://")
    except Exception:
        pass

    return {
        "id": f"book:{raw.lower()}",
        "category": "book",
        "it_title": raw,
        "orig_title": author,
        "year": year,
        "cast": "",
        "poster_url": poster_url,
        "ch_flatrate": [],
        "external_url": full_amz
        or f"https://www.goodreads.com/search?q={urllib.parse.quote(raw)}",
    }


def enrich_any(item, headers, ch_sources_map):
    cat = item.get("category", "movie")
    if cat == "music":
        return enrich_music(item)
    if cat == "book":
        return enrich_book(item)
    return enrich_movie(item, headers, ch_sources_map)


def fetch_ch_sources_map(headers):
    sources_map = {}
    for c_code in ("ch", "it"):
        try:
            r = requests.get(
                f"https://api.trakt.tv/watchnow/sources/{c_code}",
                headers=headers,
                timeout=15,
            )
            if r.status_code == 200:
                for group in r.json():
                    for src in group.get(c_code, []):
                        key = src.get("source")
                        logo = src.get("images", {}).get("logo", "")
                        sources_map[key] = {
                            "name": (src.get("name") or key).strip(),
                            "logo": f"https://{logo}" if logo else "",
                        }
        except Exception:
            pass
    return sources_map


def fetch_user_trakt_state(headers):
    watched_imdb = set()
    ratings_imdb = {}
    try:
        for endpoint, key_name in (("movies", "movie"), ("shows", "show")):
            page = 1
            while True:
                w_resp = requests.get(
                    f"https://api.trakt.tv/users/me/watched/{endpoint}",
                    params={"page": page, "limit": 250},
                    headers=headers,
                    timeout=15,
                )
                if w_resp.status_code != 200:
                    break
                rows = w_resp.json()
                if not rows:
                    break
                for row in rows:
                    imdb_id = row.get(key_name, {}).get("ids", {}).get("imdb")
                    if imdb_id:
                        watched_imdb.add(imdb_id)
                if len(rows) < 250:
                    break
                page += 1

            page = 1
            while True:
                r_resp = requests.get(
                    f"https://api.trakt.tv/users/me/ratings/{endpoint}",
                    params={"page": page, "limit": 250},
                    headers=headers,
                    timeout=15,
                )
                if r_resp.status_code != 200:
                    break
                rows = r_resp.json()
                if not rows:
                    break
                for row in rows:
                    imdb_id = row.get(key_name, {}).get("ids", {}).get("imdb")
                    if imdb_id:
                        ratings_imdb[imdb_id] = row.get("rating")
                        watched_imdb.add(imdb_id)
                if len(rows) < 250:
                    break
                page += 1
    except Exception as e:
        print(f"Avviso sync Trakt utente: {e}")
    return watched_imdb, ratings_imdb


def infer_item_metadata_for_ui(item):
    recs = item.get("recommendations", [])
    directors = set()
    if item.get("director"):
        for part in item["director"].split(","):
            nd = normalize_director_name(part.strip())
            if nd:
                directors.add(nd)
    rubriche = set()
    for r in recs:
        vt = r.get("video_title", "")
        vt_low = vt.lower()
        if not directors:
            dh = extract_director_hint_from_video_title(vt)
            if dh:
                directors.add(dh)
            else:
                m_dir = re.search(
                    r"\(\d{4}\)\s*(?:di|-)\s*([^-(\n]+?)(?:\s*-\s*(?:minirece|mini|richiest|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre|gennaio)|$)",
                    vt,
                    re.I,
                )
                if m_dir:
                    nd = normalize_director_name(m_dir.group(1))
                    if nd:
                        directors.add(nd)

        if "meglio e peggio" in vt_low or "meglio e il peggio" in vt_low:
            rubriche.add("🏆 Meglio dell'Anno")
        elif "classici" in vt_low:
            rubriche.add("🏛️ I Classici")
        elif "imperdibili" in vt_low or "perdibili" in vt_low:
            rubriche.add("💎 Gli Imperdibili")
        elif "oriente" in vt_low:
            rubriche.add("🏮 In Oriente")
        elif "underground" in vt_low:
            rubriche.add("🕳️ Underground")
        elif "monografi" in vt_low or "le recensioni di frusciante -" in vt_low:
            rubriche.add("🎥 Monografie")
        elif "saghe" in vt_low:
            rubriche.add("🎞️ Le Saghe")
        elif "patreon" in vt_low or "minirece" in vt_low:
            rubriche.add("💌 Patreon Minirece")
        elif "consigli" in vt_low:
            rubriche.add("👍 I Consigli del Mese")
        else:
            rubriche.add("🎬 Frusciante al Cinema")

    return sorted(directors), sorted(rubriche)


def generate_html(db_data, watched_imdb, ratings_imdb):
    items_out = []
    for item_id, item in db_data["items"].items():
        copy_it = dict(item)
        imdb_key = item.get("imdb_id") or item_id
        copy_it["watched"] = imdb_key in watched_imdb
        copy_it["my_rating"] = ratings_imdb.get(imdb_key)
        dirs, rubs = infer_item_metadata_for_ui(copy_it)
        copy_it["directors"] = dirs
        copy_it["rubriche"] = rubs
        copy_it["rec_count"] = len(copy_it.get("recommendations", []))
        creators_list = sorted(
            {
                r.get("creator", "Federico Frusciante")
                for r in copy_it.get("recommendations", [])
            }
        )
        copy_it["creators"] = creators_list
        copy_it["creator_count"] = len(creators_list)
        yr = copy_it.get("year")
        copy_it["decade"] = f"{(yr // 10) * 10}s" if isinstance(yr, int) and 1910 <= yr <= 2030 else ""
        # Compatta il payload JSON rimuovendo chiavi vuote o ridondanti per dimezzare il peso di index.html
        copy_it.pop("id", None)
        copy_it.pop("rubriche", None)
        if not copy_it.get("ch_flatrate"):
            copy_it.pop("ch_flatrate", None)
        if not copy_it.get("it_flatrate"):
            copy_it.pop("it_flatrate", None)
        if not copy_it.get("my_rating"):
            copy_it.pop("my_rating", None)
        if not copy_it.get("watched"):
            copy_it.pop("watched", None)
        if copy_it.get("imdb_id") and copy_it.get("category") in ("movie", "show"):
            copy_it.pop("external_url", None)
        items_out.append(copy_it)

    items_out.sort(
        key=lambda x: (
            x.get("creator_count", 1),
            x.get("year") or 0,
        ),
        reverse=True,
    )

    cp = db_data.get("last_checkpoint", {})
    done_vids = len(db_data.get("processed_videos", []))
    tot_vids = 11330  # 5499 (Frusciante) + 5831 (Alò + Criticoni + Marra + Victorlaszlo88)
    last_vid_label = f"#{done_vids} / {tot_vids}"
    data_json = json.dumps(items_out, ensure_ascii=False, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0f1014">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Momo Vault">
<link rel="apple-touch-icon" sizes="180x180" href="icon-180.png">
<link rel="icon" type="image/png" sizes="180x180" href="icon-180.png">
<link rel="manifest" href="manifest.json">
<title>Momo Vault 🇨🇭 — Cinema, Musica & Libri</title>
<style>
  :root {{
    --bg: #0f1014;
    --card: #181a20;
    --card-alt: #1e2129;
    --accent: #ed1c24;
    --accent-purple: #9b51e0;
    --green: #1db954;
    --gold: #f5c518;
    --text: #f1f3f5;
    --muted: #8b929a;
    --border: #2a2e39;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    min-height: 100vh;
  }}
  header {{
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(15, 16, 20, 0.95);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 14px 28px;
  }}
  .top-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 14px;
    max-width: 1480px;
    margin: 0 auto;
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .brand-badge {{
    background: linear-gradient(135deg, #ed1c24, #9b51e0);
    color: #fff;
    font-weight: 800;
    padding: 6px 11px;
    border-radius: 8px;
    font-size: 13px;
    letter-spacing: 0.5px;
  }}
  .brand h1 {{ font-size: 19px; font-weight: 700; }}
  .tabs {{
    display: flex;
    gap: 6px;
    background: #13151a;
    padding: 4px;
    border-radius: 10px;
    border: 1px solid var(--border);
  }}
  .tab-btn {{
    background: transparent;
    color: var(--muted);
    border: none;
    padding: 8px 15px;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s;
  }}
  .tab-btn.active {{
    background: var(--card);
    color: var(--text);
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
  }}
  .stats-pills {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .stat-pill {{
    background: var(--card);
    border: 1px solid var(--border);
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 12px;
    color: var(--muted);
  }}
  .stat-pill strong {{ color: var(--text); }}
  .filters-bar {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    max-width: 1480px;
    margin: 10px auto 0;
    padding-top: 10px;
    border-top: 1px solid rgba(255,255,255,0.06);
  }}
  .filter-group {{
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    background: #12141a;
    padding: 4px 6px;
    border-radius: 10px;
    border: 1px solid var(--border);
  }}
  .filter-group-label {{
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--muted);
    padding: 0 6px;
  }}
  .cine-chip {{
    background: transparent;
    color: var(--muted);
    border: 1px solid transparent;
    padding: 5px 10px;
    border-radius: 7px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s;
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }}
  .cine-chip:hover {{ color: var(--text); background: rgba(255,255,255,0.05); }}
  .cine-chip.active {{
    background: rgba(255,255,255,0.12);
    color: #fff;
    border-color: rgba(255,255,255,0.28);
  }}
  .cine-chip[data-cr="Federico Frusciante"].active {{ background: rgba(237, 28, 36, 0.22); border-color: #ed1c24; color: #ff9ea2; }}
  .cine-chip[data-cr="Piero Scaruffi"].active {{ background: rgba(155, 81, 224, 0.24); border-color: #9b51e0; color: #debaff; }}
  .cine-chip[data-cr="Victorlaszlo88"].active {{ background: rgba(56, 189, 248, 0.22); border-color: #38bdf8; color: #bae6fd; }}
  .cine-chip[data-cr="Mr. Marra"].active {{ background: rgba(249, 115, 22, 0.22); border-color: #f97316; color: #fed7aa; }}
  .cine-chip[data-cr="I Criticoni"].active {{ background: rgba(16, 185, 129, 0.22); border-color: #10b981; color: #a7f3d0; }}
  .cine-chip[data-cr="Francesco Alò"].active {{ background: rgba(6, 182, 212, 0.22); border-color: #06b6d4; color: #a5f3fc; }}
  .cine-chip[data-cr="Roger Ebert"].active {{ background: rgba(245, 197, 24, 0.22); border-color: #f5c518; color: #fde68a; }}
  .seg-ctrl {{
    display: inline-flex;
    background: #0d0f14;
    border-radius: 7px;
    padding: 2px;
    border: 1px solid rgba(255,255,255,0.07);
  }}
  .seg-btn {{
    background: transparent;
    color: var(--muted);
    border: none;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.15s;
  }}
  .seg-btn.active {{
    background: var(--card-alt);
    color: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.4);
  }}
  input[type="search"], select {{
    background: #12141a;
    color: var(--text);
    border: 1px solid var(--border);
    padding: 6px 11px;
    border-radius: 7px;
    font-size: 12px;
    font-weight: 600;
    outline: none;
  }}
  input[type="search"] {{ width: 250px; padding: 7px 12px; font-size: 13px; }}
  input[type="search"]:focus, select:focus {{ border-color: #525b70; }}
  .toggle-btn, .action-btn {{
    background: #12141a;
    color: var(--text);
    border: 1px solid var(--border);
    padding: 6px 11px;
    border-radius: 7px;
    font-size: 12px;
    cursor: pointer;
    font-weight: 700;
    transition: all 0.15s;
  }}
  .toggle-btn.active {{
    background: rgba(29, 185, 84, 0.18);
    border-color: var(--green);
    color: #5ff28d;
  }}
  .action-btn.purple {{
    background: rgba(155, 81, 224, 0.16);
    border-color: rgba(155, 81, 224, 0.5);
    color: #d2a8ff;
  }}
  .action-btn.purple:hover {{ background: var(--accent-purple); color: #fff; }}
  .action-btn.gold {{
    background: rgba(245, 197, 24, 0.14);
    border-color: rgba(245, 197, 24, 0.5);
    color: var(--gold);
  }}
  .action-btn.gold:hover {{ background: var(--gold); color: #000; }}

  .active-filters {{
    display: none;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    max-width: 1480px;
    margin: 10px auto 0;
    padding-top: 8px;
    border-top: 1px dashed var(--border);
  }}
  .active-filters.show {{ display: flex; }}
  .active-tag {{
    background: rgba(237, 28, 36, 0.2);
    border: 1px solid var(--accent);
    color: #ffb3b6;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    cursor: pointer;
  }}
  .reset-all-btn {{
    background: #2b303c;
    border: 1px solid #454d5e;
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 999px;
    cursor: pointer;
  }}
  .reset-all-btn:hover {{ background: var(--accent); border-color: var(--accent); }}
  main {{
    max-width: 1480px;
    margin: 20px auto 60px;
    padding: 0 28px;
  }}

  /* Insights / Hall of Fame Drawer */
  .insights-panel {{
    display: none;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 18px;
    margin-bottom: 24px;
  }}
  .insights-panel.open {{ display: grid; }}
  .insight-box {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
  }}
  .insight-box h3 {{
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .chip-cloud {{
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
  }}
  .chip {{
    background: var(--card-alt);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 10px;
    border-radius: 999px;
    font-size: 12px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
  }}
  .chip:hover, .chip.active {{
    border-color: var(--accent);
    background: rgba(237, 28, 36, 0.18);
    color: #ff9ea2;
  }}
  .chip-count {{
    background: rgba(255,255,255,0.1);
    padding: 1px 6px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(215px, 1fr));
    gap: 20px;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    transition: transform 0.18s ease, border-color 0.18s ease;
    position: relative;
  }}
  .card:hover {{
    transform: translateY(-4px);
    border-color: #444b5e;
    z-index: 20;
  }}
  .poster-wrap {{
    position: relative;
    aspect-ratio: 2 / 3;
    background: #121318;
    overflow: hidden;
    border-radius: 11px 11px 0 0;
  }}
  .poster-wrap.square {{ aspect-ratio: 1 / 1; }}
  .poster-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }}
  .watched-ribbon {{
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(29, 185, 84, 0.92);
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 8px;
    border-radius: 6px;
  }}
  .rating-ribbon {{
    position: absolute;
    top: 10px;
    left: 10px;
    background: rgba(0, 0, 0, 0.85);
    border: 1px solid var(--gold);
    color: var(--gold);
    font-size: 12px;
    font-weight: 800;
    padding: 4px 8px;
    border-radius: 6px;
  }}
  .mentions-ribbon {{
    position: absolute;
    top: 10px;
    left: 10px;
    background: rgba(237, 28, 36, 0.9);
    color: #fff;
    font-size: 11px;
    font-weight: 800;
    padding: 4px 8px;
    border-radius: 6px;
  }}
  .ch-strip {{
    position: absolute;
    bottom: 8px;
    left: 8px;
    right: 8px;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .ch-pill {{
    background: rgba(15, 16, 20, 0.92);
    border: 1px solid var(--green);
    color: #6df799;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 8px;
    border-radius: 6px;
    text-decoration: none;
  }}
  .ch-pill:hover {{ background: var(--green); color: #000; }}
  .card-body {{
    padding: 12px 14px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
  }}
  .movie-title {{
    font-size: 15px;
    font-weight: 700;
    line-height: 1.25;
  }}
  .movie-sub {{
    font-size: 12px;
    color: var(--muted);
  }}
  .dir-badge {{
    display: inline-block;
    background: rgba(155, 81, 224, 0.16);
    color: #d2a8ff;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 5px;
    cursor: pointer;
    width: fit-content;
  }}
  .dir-badge:hover {{ background: var(--accent-purple); color: #fff; }}
  .rec-list {{
    margin-top: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    padding-top: 6px;
  }}
  .cr-pill {{
    background: rgba(237, 28, 36, 0.14);
    border: 1px solid rgba(237, 28, 36, 0.45);
    color: #ff8085;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }}
  .cr-pill:hover {{ background: var(--accent); color: #fff; }}
  .cr-pill.scaruffi {{
    background: rgba(245, 197, 24, 0.14);
    border-color: rgba(245, 197, 24, 0.55);
    color: #ffe066;
  }}
  .cr-pill.scaruffi:hover {{ background: var(--gold); color: #000; }}
  .cr-pill.victor {{
    background: rgba(45, 156, 219, 0.16);
    border-color: rgba(45, 156, 219, 0.55);
    color: #7fd1ff;
  }}
  .cr-pill.victor:hover {{ background: #2d9cdb; color: #fff; }}
  .cr-pill.marra {{
    background: rgba(155, 81, 224, 0.18);
    border-color: rgba(155, 81, 224, 0.55);
    color: #d8aaff;
  }}
  .cr-pill.marra:hover {{ background: var(--accent-purple); color: #fff; }}
  .cr-pill.criticoni {{
    background: rgba(29, 185, 84, 0.16);
    border-color: rgba(29, 185, 84, 0.55);
    color: #6df799;
  }}
  .cr-pill.criticoni:hover {{ background: var(--green); color: #000; }}
  .cr-pill.alo {{
    background: rgba(0, 210, 211, 0.15);
    border-color: rgba(0, 210, 211, 0.55);
    color: #66f2f2;
  }}
  .cr-pill.alo:hover {{ background: #00d2d3; color: #000; }}
  .cr-pill.ebert {{
    background: rgba(245, 158, 11, 0.16);
    border-color: rgba(245, 158, 11, 0.55);
    color: #fcd34d;
  }}
  .cr-pill.ebert:hover {{ background: #f59e0b; color: #000; }}

  .cr-dropdown {{
    position: relative;
    display: inline-block;
  }}
  .cr-menu {{
    display: none;
    position: absolute;
    bottom: calc(100% + 6px);
    left: 0;
    min-width: 230px;
    background: #14161c;
    border: 1px solid #3a4050;
    border-radius: 10px;
    padding: 6px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.75);
    z-index: 100;
    flex-direction: column;
    gap: 4px;
  }}
  .cr-dropdown.open .cr-menu {{
    display: flex;
  }}
  .cr-menu-item {{
    color: var(--text);
    text-decoration: none;
    font-size: 11.5px;
    padding: 6px 8px;
    border-radius: 6px;
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }}
  .cr-menu-item:hover {{
    background: #252934;
    color: #ff8085;
  }}
  .card-links {{
    display: flex;
    gap: 10px;
    font-size: 11px;
    margin-top: 4px;
  }}
  .card-links a {{
    color: var(--muted);
    text-decoration: none;
  }}
  .card-links a:hover {{ color: var(--text); text-decoration: underline; }}
  @media (max-width: 768px) {{
    header {{
      position: relative;
      padding: max(12px, env(safe-area-inset-top)) 12px 12px;
    }}
    main {{
      padding: 12px 10px max(24px, env(safe-area-inset-bottom));
    }}
    .tabs {{
      width: 100%;
      overflow-x: auto;
      justify-content: space-between;
    }}
    .tab-btn {{
      padding: 7px 10px;
      font-size: 12px;
      white-space: nowrap;
      flex: 1;
      text-align: center;
    }}
    input[type="search"] {{
      min-width: 0;
      width: 100%;
      flex: 1;
    }}
    .filter-group {{
      width: 100%;
      overflow-x: auto;
      flex-wrap: nowrap;
      padding: 7px 9px;
      -webkit-overflow-scrolling: touch;
    }}
    .cine-chip, .toggle-btn, .seg-btn, .action-btn, select {{
      white-space: nowrap;
      flex-shrink: 0;
    }}
    .grid {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .card-body {{
      padding: 9px;
      gap: 5px;
    }}
    .movie-title {{
      font-size: 13.5px;
    }}
  }}
</style>
</head>
<body>

<header>
  <div class="top-row">
    <div class="brand">
      <span class="brand-badge">MOMO VAULT 🇨🇭</span>
      <div class="tabs">
        <button class="tab-btn active" data-cat="movie" id="tabMovie">🎬 Film</button>
        <button class="tab-btn" data-cat="show" id="tabShow">📺 Serie TV</button>
        <button class="tab-btn" data-cat="music" id="tabMusic">🎵 Musica & Dischi</button>
        <button class="tab-btn" data-cat="book" id="tabBook">📚 Libri</button>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      <input type="search" id="searchInput" placeholder="🔍 Cerca titolo, regista, attore, anno...">
      <button class="action-btn purple" id="btnRoulette" title="Pesca un film a caso tra i filtri attivi non ancora visto!">🎲 Cosa Guardo Stasera?</button>
    </div>

    <div class="stats-pills" id="statsPills"></div>
  </div>

  <div class="filters-bar">
    <!-- Gruppo 1: Barra interattiva Cinefili -->
    <div class="filter-group" id="cinefiliBar">
      <span class="filter-group-label">🎙️ Cinefili</span>
      <button class="cine-chip active" data-cr="ALL" onclick="selectCreatorChip('ALL')">Tutti</button>
      <button class="cine-chip" data-cr="Federico Frusciante" onclick="selectCreatorChip('Federico Frusciante')">🔴 Frusciante</button>
      <button class="cine-chip" data-cr="Victorlaszlo88" onclick="selectCreatorChip('Victorlaszlo88')">🔵 Laszlo</button>
      <button class="cine-chip" data-cr="Francesco Alò" onclick="selectCreatorChip('Francesco Alò')">🩵 Alò</button>
      <button class="cine-chip" data-cr="Piero Scaruffi" onclick="selectCreatorChip('Piero Scaruffi')">🟣 Scaruffi</button>
      <button class="cine-chip" data-cr="Roger Ebert" onclick="selectCreatorChip('Roger Ebert')">🟡 Ebert</button>
      <button class="cine-chip" data-cr="Mr. Marra" onclick="selectCreatorChip('Mr. Marra')">🟠 Marra</button>
      <button class="cine-chip" data-cr="I Criticoni" onclick="selectCreatorChip('I Criticoni')">🟢 Criticoni</button>
      <button class="action-btn gold" id="btnCreatorMode" style="display:none" onclick="toggleCreatorMatchMode()" title="Scegli se vedere i film consigliati da TUTTI i cinefili selezionati (In Comune) o da ALMENO UNO (Unione)">🔗 In Comune (AND)</button>
      <button class="toggle-btn" id="btnMultiCreator" title="Mostra solo opere consigliate da almeno 2 cinefili diversi!">🤝 2+ Consenso</button>
      <select id="creatorFilter" style="display:none"><option value="ALL">Tutti</option></select>
    </div>

    <!-- Gruppo 2: Streaming (Paese CH/IT + Piattaforma) -->
    <div class="filter-group" id="streamingGroup">
      <div class="seg-ctrl" id="countrySeg">
        <button class="seg-btn active" data-c="CH" onclick="setStreamCountry('CH')">🇨🇭 CH</button>
        <button class="seg-btn" data-c="IT" onclick="setStreamCountry('IT')">🇮🇹 IT</button>
      </div>
      <button class="action-btn gold" id="btnCountry" style="display:none">🇨🇭</button>
      <button class="toggle-btn" id="btnOnlyCh">⚡ Solo Streaming</button>
      <select id="providerFilter">
        <option value="ALL">Tutte le piattaforme</option>
      </select>
    </div>

    <!-- Gruppo 3: Trakt, Epoca & Ordinamento -->
    <div class="filter-group">
      <div class="seg-ctrl" id="watchedSeg">
        <button class="seg-btn active" data-w="ALL" onclick="setWatchedMode('ALL')">Tutti</button>
        <button class="seg-btn" data-w="UNWATCHED" onclick="setWatchedMode('UNWATCHED')">Da Vedere</button>
        <button class="seg-btn" data-w="WATCHED" onclick="setWatchedMode('WATCHED')">✓ Visti</button>
      </div>
      <select id="watchedFilter" style="display:none">
        <option value="ALL">Tutti</option>
        <option value="UNWATCHED">Solo Da Vedere</option>
        <option value="WATCHED">Già Visti su Trakt</option>
      </select>
      <select id="rubricaFilter" style="display:none"><option value="ALL">Tutte</option></select>
      <select id="directorFilter" style="display:none"><option value="ALL">Tutti</option></select>
      <select id="decadeFilter">
        <option value="ALL">🕰️ Tutte le Epoche</option>
      </select>
      <select id="sortFilter">
        <option value="CONSENSUS">🤝 Ordina: Consenso Cinefili</option>
        <option value="YEAR_DESC">📅 Anno (Recenti → Storici)</option>
        <option value="YEAR_ASC">🏛️ Anno (Storici → Recenti)</option>
        <option value="MY_RATING">⭐ Il mio voto Trakt</option>
        <option value="TITLE_ASC">🔤 Titolo (A → Z)</option>
      </select>
    </div>
  </div>
  <div class="active-filters" id="activeFiltersBar"></div>
</header>

<main>
  <section class="insights-panel" id="insightsPanel" style="display:none!important">
    <div id="topMentionedCloud"></div>
    <div id="topDirectorsCloud"></div>
    <div id="topDecadesCloud"></div>
  </section>

  <div class="grid" id="moviesGrid"></div>
  <div id="scrollSentinel" style="height:40px;margin-top:20px;"></div>
</main>

<script>
const ITEMS = {data_json};
let activeCategory = 'movie';
let onlyChStreaming = false;
let onlyMultiCreator = false;
let selectedCreators = new Set();
let creatorMatchMode = 'AND'; // 'AND' = in comune a tutti i selezionati, 'OR' = almeno uno
let streamCountry = localStorage.getItem('momo_vault_country') || 'CH';

const searchInput = document.getElementById('searchInput');
const btnInsights = document.getElementById('btnInsights');
const btnRoulette = document.getElementById('btnRoulette');
const btnMultiCreator = document.getElementById('btnMultiCreator');
const btnCreatorMode = document.getElementById('btnCreatorMode');
const btnCountry = document.getElementById('btnCountry');
const btnOnlyCh = document.getElementById('btnOnlyCh');
const creatorFilter = document.getElementById('creatorFilter');
const providerFilter = document.getElementById('providerFilter');
const rubricaFilter = document.getElementById('rubricaFilter');
const directorFilter = document.getElementById('directorFilter');
const decadeFilter = document.getElementById('decadeFilter');
const watchedFilter = document.getElementById('watchedFilter');
const sortFilter = document.getElementById('sortFilter');
const moviesGrid = document.getElementById('moviesGrid');
const statsPills = document.getElementById('statsPills');
const insightsPanel = document.getElementById('insightsPanel');

function getActiveFlatrate(m) {{
  return streamCountry === 'IT' ? (m.it_flatrate || []) : (m.ch_flatrate || []);
}}
function getCountryFlag() {{
  return streamCountry === 'IT' ? '🇮🇹' : '🇨🇭';
}}

const counts = {{ movie: 0, show: 0, music: 0, book: 0 }};
const creatorsMap = {{}};
const rubricheMap = {{}};
const directorsMap = {{}};
const decadesMap = {{}};

ITEMS.forEach(m => {{
  const cat = m.category || 'movie';
  counts[cat] = (counts[cat] || 0) + 1;
  (m.creators || []).forEach(c => {{ creatorsMap[c] = (creatorsMap[c] || 0) + 1; }});
  (m.rubriche || []).forEach(r => {{ rubricheMap[r] = (rubricheMap[r] || 0) + 1; }});
  if (cat === 'movie' || cat === 'show') {{
    (m.directors || []).forEach(d => {{ directorsMap[d] = (directorsMap[d] || 0) + 1; }});
    if (m.decade) decadesMap[m.decade] = (decadesMap[m.decade] || 0) + 1;
  }}
}});

document.getElementById('tabMovie').textContent = `🎬 Film (${{counts.movie || 0}})`;
document.getElementById('tabShow').textContent = `📺 Serie TV (${{counts.show || 0}})`;
document.getElementById('tabMusic').textContent = `🎵 Musica & Dischi (${{counts.music || 0}})`;
document.getElementById('tabBook').textContent = `📚 Libri (${{counts.book || 0}})`;

Object.entries(creatorsMap).sort((a,b) => b[1] - a[1]).forEach(([c, cnt]) => {{
  const opt = document.createElement('option');
  opt.value = c;
  opt.textContent = `🎙️ ${{c}} (${{cnt}})`;
  creatorFilter.appendChild(opt);
}});

function rebuildCountryUI() {{
  const flag = getCountryFlag();
  btnOnlyCh.textContent = `⚡ Solo Streaming ${{streamCountry}}`;
  const badge = document.querySelector('.brand-badge');
  if (badge) badge.textContent = `MOMO VAULT ${{flag}}`;
  document.querySelectorAll('#countrySeg .seg-btn').forEach(b => {{
    b.classList.toggle('active', b.dataset.c === streamCountry);
  }});

  const prevVal = providerFilter.value;
  providerFilter.innerHTML = `<option value="ALL">Piattaforme ${{streamCountry}} (Tutte)</option>`;
  const pSet = new Set();
  ITEMS.forEach(m => {{
    getActiveFlatrate(m).forEach(p => pSet.add(p.name));
  }});
  Array.from(pSet).sort().forEach(p => {{
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = `${{flag}} ${{p}}`;
    providerFilter.appendChild(opt);
  }});
  if (pSet.has(prevVal)) providerFilter.value = prevVal;
}}
window.setStreamCountry = function(c) {{
  streamCountry = c;
  localStorage.setItem('momo_vault_country', streamCountry);
  rebuildCountryUI();
  render();
}};
function syncCreatorChipsUI() {{
  document.querySelectorAll('#cinefiliBar .cine-chip').forEach(btn => {{
    if (btn.dataset.cr === 'ALL') {{
      btn.classList.toggle('active', selectedCreators.size === 0);
    }} else {{
      btn.classList.toggle('active', selectedCreators.has(btn.dataset.cr));
    }}
  }});
  if (btnCreatorMode) {{
    btnCreatorMode.style.display = selectedCreators.size >= 2 ? '' : 'none';
    btnCreatorMode.textContent = creatorMatchMode === 'AND' ? '🔗 In Comune (AND)' : '➕ Unione (OR)';
  }}
}}
window.selectCreatorChip = function(cr) {{
  if (cr === 'ALL') {{
    selectedCreators.clear();
  }} else {{
    if (selectedCreators.has(cr)) {{
      selectedCreators.delete(cr);
    }} else {{
      selectedCreators.add(cr);
    }}
  }}
  syncCreatorChipsUI();
  render();
}};
window.removeCreatorChip = function(cr) {{
  selectedCreators.delete(cr);
  syncCreatorChipsUI();
  render();
}};
window.toggleCreatorMatchMode = function() {{
  creatorMatchMode = (creatorMatchMode === 'AND') ? 'OR' : 'AND';
  syncCreatorChipsUI();
  render();
}};
window.setWatchedMode = function(w) {{
  watchedFilter.value = w;
  document.querySelectorAll('#watchedSeg .seg-btn').forEach(btn => {{
    btn.classList.toggle('active', btn.dataset.w === w);
  }});
  render();
}};
rebuildCountryUI();

Object.entries(rubricheMap).sort((a,b) => b[1] - a[1]).forEach(([r, cnt]) => {{
  const opt = document.createElement('option');
  opt.value = r;
  opt.textContent = `${{r}} (${{cnt}})`;
  rubricaFilter.appendChild(opt);
}});

Object.entries(directorsMap).sort((a,b) => b[1] - a[1]).slice(0, 80).forEach(([d, cnt]) => {{
  const opt = document.createElement('option');
  opt.value = d;
  opt.textContent = `🎬 ${{d}} (${{cnt}})`;
  directorFilter.appendChild(opt);
}});

Object.keys(decadesMap).sort().forEach(dec => {{
  const opt = document.createElement('option');
  opt.value = dec;
  opt.textContent = `🕰️ ${{dec}} (${{decadesMap[dec]}})`;
  decadeFilter.appendChild(opt);
}});

function buildInsightsClouds() {{
  const catItems = ITEMS.filter(m => (m.category || 'movie') === activeCategory);
  // Top Mentioned
  const topM = [...catItems].sort((a,b) => (b.rec_count || 0) - (a.rec_count || 0)).slice(0, 18);
  document.getElementById('topMentionedCloud').innerHTML = topM.map(m =>
    `<span class="chip" onclick="filterBySearch('${{m.it_title.replace(/'/g, "\\'")}}')">
      ${{m.it_title}} <span class="chip-count">🔥 ${{m.rec_count}}x</span>
    </span>`
  ).join('');

  // Top Directors
  const topD = Object.entries(directorsMap).sort((a,b) => b[1] - a[1]).slice(0, 20);
  document.getElementById('topDirectorsCloud').innerHTML = topD.map(([d, cnt]) =>
    `<span class="chip ${{directorFilter.value === d ? 'active' : ''}}" onclick="selectDirector('${{d.replace(/'/g, "\\'")}}')">
      🎬 ${{d}} <span class="chip-count">${{cnt}}</span>
    </span>`
  ).join('');

  // Decades & Rubriche
  const decChips = Object.keys(decadesMap).sort().map(dec =>
    `<span class="chip ${{decadeFilter.value === dec ? 'active' : ''}}" onclick="selectDecade('${{dec}}')">
      🕰️ ${{dec}} <span class="chip-count">${{decadesMap[dec]}}</span>
    </span>`
  ).join('');
  document.getElementById('topDecadesCloud').innerHTML = decChips;
}}

window.resetAllFilters = function() {{
  searchInput.value = '';
  onlyChStreaming = false;
  onlyMultiCreator = false;
  btnOnlyCh.classList.remove('active');
  btnMultiCreator.classList.remove('active');
  selectedCreators.clear();
  creatorFilter.value = 'ALL';
  syncCreatorChipsUI();
  providerFilter.value = 'ALL';
  rubricaFilter.value = 'ALL';
  directorFilter.value = 'ALL';
  decadeFilter.value = 'ALL';
  setWatchedMode('ALL');
  buildInsightsClouds();
  render();
}};

let roulettePick = null;
window.clearRoulettePick = function() {{
  roulettePick = null;
  btnRoulette.textContent = '🎲 Cosa Guardo Stasera?';
  render();
}};

function renderActiveFiltersBar() {{
  const bar = document.getElementById('activeFiltersBar');
  const tags = [];
  if (roulettePick) {{
    tags.push(`<span class="active-tag" onclick="clearRoulettePick()">🎲 Pescato a sorte: "${{roulettePick.it_title}}" ✕</span>`);
  }}
  if (searchInput.value.trim()) {{
    tags.push(`<span class="active-tag" onclick="searchInput.value=''; render();">🔍 "${{searchInput.value.trim()}}" ✕</span>`);
  }}
  if (onlyMultiCreator) {{
    tags.push(`<span class="active-tag" onclick="onlyMultiCreator=false; btnMultiCreator.classList.remove('active'); render();">🤝 Consenso 2+ Cinefili ✕</span>`);
  }}
  selectedCreators.forEach(c => {{
    tags.push(`<span class="active-tag" onclick="removeCreatorChip('${{c.replace(/'/g, "\\'")}}')">🎙️ ${{c}} ✕</span>`);
  }});
  if (onlyChStreaming) {{
    tags.push(`<span class="active-tag" onclick="onlyChStreaming=false; btnOnlyCh.classList.remove('active'); render();">${{getCountryFlag()}} Solo Streaming ${{streamCountry}} ✕</span>`);
  }}
  if (providerFilter.value !== 'ALL') {{
    tags.push(`<span class="active-tag" onclick="providerFilter.value='ALL'; render();">${{getCountryFlag()}} ${{providerFilter.value}} ✕</span>`);
  }}
  if (rubricaFilter.value !== 'ALL') {{
    tags.push(`<span class="active-tag" onclick="rubricaFilter.value='ALL'; render();">${{rubricaFilter.value}} ✕</span>`);
  }}
  if (directorFilter.value !== 'ALL') {{
    tags.push(`<span class="active-tag" onclick="selectDirector('${{directorFilter.value.replace(/'/g, "\\'")}}')">🎬 ${{directorFilter.value}} ✕</span>`);
  }}
  if (decadeFilter.value !== 'ALL') {{
    tags.push(`<span class="active-tag" onclick="selectDecade('${{decadeFilter.value}}')">🕰️ ${{decadeFilter.value}} ✕</span>`);
  }}
  if (watchedFilter.value !== 'ALL') {{
    tags.push(`<span class="active-tag" onclick="setWatchedMode('ALL')">👁️ ${{watchedFilter.value}} ✕</span>`);
  }}

  if (tags.length > 0) {{
    bar.classList.add('show');
    bar.innerHTML = `<span style="font-size:12px;color:var(--muted);">Filtri attivi:</span> ` + tags.join('') + ` <button class="reset-all-btn" onclick="resetAllFilters()">🔄 Azzera tutti i filtri</button>`;
  }} else {{
    bar.classList.remove('show');
    bar.innerHTML = '';
  }}
}}
window.filterBySearch = function(title) {{
  searchInput.value = (searchInput.value === title) ? '' : title;
  render();
}};
window.selectDirector = function(dir) {{
  directorFilter.value = (directorFilter.value === dir) ? 'ALL' : dir;
  buildInsightsClouds();
  render();
}};
window.selectDecade = function(dec) {{
  decadeFilter.value = (decadeFilter.value === dec) ? 'ALL' : dec;
  buildInsightsClouds();
  render();
}};

if (btnInsights) {{
  btnInsights.addEventListener('click', () => {{
    insightsPanel.classList.toggle('open');
  }});
}}

btnRoulette.addEventListener('click', () => {{
  const prevPick = roulettePick;
  roulettePick = null;
  let pool = getFilteredItems().filter(m => !m.watched);
  if (pool.length === 0) pool = getFilteredItems();
  if (pool.length === 0) return;
  if (pool.length > 1 && prevPick) {{
    pool = pool.filter(m => m !== prevPick);
  }}
  roulettePick = pool[Math.floor(Math.random() * pool.length)];
  btnRoulette.textContent = '🎲 Gira ancora!';
  render(true);
}});

document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeCategory = btn.dataset.cat;
    const isVideo = activeCategory === 'movie' || activeCategory === 'show';
    document.getElementById('streamingGroup').style.display = isVideo ? '' : 'none';
    document.getElementById('watchedSeg').style.display = isVideo ? '' : 'none';
    decadeFilter.style.display = isVideo ? '' : 'none';
    buildInsightsClouds();
    render();
  }});
}});

btnMultiCreator.addEventListener('click', () => {{
  onlyMultiCreator = !onlyMultiCreator;
  btnMultiCreator.classList.toggle('active', onlyMultiCreator);
  render();
}});
btnCountry.addEventListener('click', () => {{
  streamCountry = (streamCountry === 'CH') ? 'IT' : 'CH';
  localStorage.setItem('momo_vault_country', streamCountry);
  rebuildCountryUI();
  render();
}});
btnOnlyCh.addEventListener('click', () => {{
  onlyChStreaming = !onlyChStreaming;
  btnOnlyCh.classList.toggle('active', onlyChStreaming);
  render();
}});
searchInput.addEventListener('input', render);
creatorFilter.addEventListener('change', render);
providerFilter.addEventListener('change', render);
rubricaFilter.addEventListener('change', render);
directorFilter.addEventListener('change', () => {{ buildInsightsClouds(); render(); }});
decadeFilter.addEventListener('change', () => {{ buildInsightsClouds(); render(); }});
watchedFilter.addEventListener('change', render);
sortFilter.addEventListener('change', render);

function getFilteredItems() {{
  const q = searchInput.value.trim().toLowerCase();
  const prov = providerFilter.value;
  const rub = rubricaFilter.value;
  const dir = directorFilter.value;
  const dec = decadeFilter.value;
  const wMode = watchedFilter.value;
  const sortMode = sortFilter.value;
  const isVideo = activeCategory === 'movie' || activeCategory === 'show';

  const catItems = ITEMS.filter(m => (m.category || 'movie') === activeCategory);
  const selArr = Array.from(selectedCreators);
  const filtered = catItems.filter(m => {{
    if (onlyMultiCreator && (m.creator_count || 1) < 2) return false;
    if (selArr.length > 0) {{
      const mCrs = m.creators || [];
      if (creatorMatchMode === 'AND') {{
        if (!selArr.every(c => mCrs.includes(c))) return false;
      }} else {{
        if (!selArr.some(c => mCrs.includes(c))) return false;
      }}
    }}
    if (isVideo) {{
      const flat = getActiveFlatrate(m);
      if (onlyChStreaming && flat.length === 0) return false;
      if (prov !== 'ALL' && !flat.some(p => p.name === prov)) return false;
      if (wMode === 'UNWATCHED' && m.watched) return false;
      if (wMode === 'WATCHED' && !m.watched) return false;
      if (dir !== 'ALL' && !(m.directors || []).includes(dir)) return false;
      if (dec !== 'ALL' && m.decade !== dec) return false;
    }}
    if (rub !== 'ALL' && !(m.rubriche || []).includes(rub)) return false;
    if (q) {{
      const recTitles = (m.recommendations || []).map(r => r.video_title).join(' ');
      const dirs = (m.directors || []).join(' ');
      const hay = `${{m.it_title}} ${{m.orig_title || ''}} ${{m.year || ''}} ${{m.cast || ''}} ${{dirs}} ${{recTitles}}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  filtered.sort((a, b) => {{
    if (sortMode === 'CONSENSUS') return (b.creator_count || 1) - (a.creator_count || 1) || (b.year || 0) - (a.year || 0);
    if (sortMode === 'YEAR_DESC') return (b.year || 0) - (a.year || 0);
    if (sortMode === 'YEAR_ASC') return (a.year || 9999) - (b.year || 9999);
    if (sortMode === 'MY_RATING') return (b.my_rating || 0) - (a.my_rating || 0);
    if (sortMode === 'TITLE_ASC') return (a.it_title || '').localeCompare(b.it_title || '');
    return 0;
  }});

  return filtered;
}}

let currentFiltered = [];
let renderedCount = 0;
const PAGE_SIZE = 120;

function renderCardHtml(m) {{
    const sameTitle = m.it_title.toLowerCase() === (m.orig_title || '').toLowerCase();
    const subLine = [m.year, (!sameTitle && m.orig_title) ? m.orig_title : ''].filter(Boolean).join(' • ');
    const flag = getCountryFlag();
    const chBadges = getActiveFlatrate(m).map(p =>
      `<a class="ch-pill" href="${{p.link || '#'}}" target="_blank" rel="noopener">${{flag}} ${{p.name}}</a>`
    ).join('');

    const dirBadges = (m.directors || []).map(d =>
      `<span class="dir-badge" onclick="selectDirector('${{d.replace(/'/g, "\\'")}}')">🎬 ${{d}}</span>`
    ).join(' ');

    const byCreator = {{}};
    (m.recommendations || []).forEach(r => {{
      const cr = r.creator || 'Federico Frusciante';
      if (!byCreator[cr]) byCreator[cr] = [];
      byCreator[cr].push(r);
    }});

    const recButtons = Object.entries(byCreator).map(([cr, rList]) => {{
      let pillClass = 'cr-pill';
      let shortCr = 'Frusciante';
      let icon = '▶';
      if (cr === 'Piero Scaruffi') {{ pillClass += ' scaruffi'; shortCr = 'Scaruffi'; icon = '📖'; }}
      else if (cr === 'Victorlaszlo88') {{ pillClass += ' victor'; shortCr = 'Laszlo'; }}
      else if (cr === 'Mr. Marra') {{ pillClass += ' marra'; shortCr = 'Marra'; }}
      else if (cr === 'I Criticoni') {{ pillClass += ' criticoni'; shortCr = 'Criticoni'; }}
      else if (cr === 'Francesco Alò') {{ pillClass += ' alo'; shortCr = 'Alò'; }}
      else if (cr === 'Roger Ebert') {{ pillClass += ' ebert'; shortCr = 'Ebert'; icon = '👍'; }}

      if (rList.length === 1) {{
        const r = rList[0];
        const href = r.external_rec_url
          ? r.external_rec_url
          : `https://youtu.be/${{r.video_id}}?t=${{r.seconds || 0}}s`;
        const showTs = r.timestamp && r.timestamp !== '00:00' && cr !== 'Piero Scaruffi' && cr !== 'Roger Ebert' && !String(r.timestamp).startsWith('★');
        const tsBadge = showTs ? ` <span style="opacity:0.8">${{r.timestamp}}</span>` : '';
        const tipTitle = (cr === 'Piero Scaruffi' || cr === 'Roger Ebert') ? `Consigliato da ${{cr}}` : (r.video_title || '');
        return `<a class="${{pillClass}}" href="${{href}}" target="_blank" rel="noopener" title="${{tipTitle}}">
          ${{icon}} ${{shortCr}}${{tsBadge}}
        </a>`;
      }}

      const menuItems = rList.map(r => {{
        const href = r.external_rec_url
          ? r.external_rec_url
          : `https://youtu.be/${{r.video_id}}?t=${{r.seconds || 0}}s`;
        const cleanVT = (r.video_title || '')
          .replace(/^Federico Frusciante\s*[:\-]\s*/i, '')
          .replace(/^Le Monografie di Frusciante\s*[:\-]\s*/i, 'Monografia: ')
          .replace(/^I Consigli (?:Musicali|Letterari|di) (?:Frusciante)?\s*[:\-]?\s*/i, 'Consigli: ')
          .replace(/^Patreon\s*:\s*/i, 'Patreon: ');
        return `<a class="cr-menu-item" href="${{href}}" target="_blank" rel="noopener" title="${{r.video_title}}">
          <span>▶ ${{cleanVT.slice(0, 26)}}</span>
          <span style="color:var(--muted)">${{r.timestamp || ''}}</span>
        </a>`;
      }}).join('');

      return `<div class="cr-dropdown">
        <span class="${{pillClass}}" onclick="toggleCrMenu(event, this)">
          ${{icon}} ${{shortCr}} ▾
        </span>
        <div class="cr-menu">${{menuItems}}</div>
      </div>`;
    }}).join('');

    let extLabel = 'Apri su Trakt ↗';
    if (m.category === 'music') extLabel = '🎵 Ascolta su Spotify ↗';
    if (m.category === 'book') extLabel = '📚 Scheda Libro ↗';
    const extUrl = m.external_url || (m.imdb_id ? `https://app.trakt.tv/${{(m.category === 'show' || m.media_type === 'show') ? 'shows' : 'movies'}}/${{m.imdb_id}}` : '');

    const leftRibbon = m.my_rating
      ? `<span class="rating-ribbon">★ ${{m.my_rating}}/10</span>`
      : '';

    return `
      <div class="card">
        <div class="poster-wrap ${{m.category === 'music' ? 'square' : ''}}">
          ${{m.poster_url ? `<img src="${{m.poster_url}}" alt="${{m.it_title}}" loading="lazy">` : ''}}
          ${{m.watched ? `<span class="watched-ribbon">✓ VISTO</span>` : ''}}
          ${{leftRibbon}}
          <div class="ch-strip">${{chBadges}}</div>
        </div>
        <div class="card-body">
          <div class="movie-title">${{m.it_title}}</div>
          <div class="movie-sub">${{subLine}}</div>
          ${{dirBadges ? `<div>${{dirBadges}}</div>` : ''}}
          ${{m.cast ? `<div class="movie-sub">${{m.cast}}</div>` : ''}}
          <div class="rec-list">${{recButtons}}</div>
          <div class="card-links">
            ${{extUrl ? `<a href="${{extUrl}}" target="_blank" rel="noopener">${{extLabel}}</a>` : ''}}
            ${{m.imdb_id ? `<a href="https://www.imdb.com/title/${{m.imdb_id}}/" target="_blank" rel="noopener">IMDb ↗</a>` : ''}}
            ${{m.apple_url ? `<a href="${{m.apple_url}}" target="_blank" rel="noopener">Apple Music ↗</a>` : ''}}
          </div>
        </div>
      </div>
    `;
}}

function appendNextBatch() {{
  if (renderedCount >= currentFiltered.length) return;
  const slice = currentFiltered.slice(renderedCount, renderedCount + PAGE_SIZE);
  moviesGrid.insertAdjacentHTML('beforeend', slice.map(renderCardHtml).join(''));
  renderedCount += slice.length;
}}

function render(keepRoulette = false) {{
  if (keepRoulette !== true && roulettePick) {{
    roulettePick = null;
    btnRoulette.textContent = '🎲 Cosa Guardo Stasera?';
  }}
  renderActiveFiltersBar();
  const isVideo = activeCategory === 'movie' || activeCategory === 'show';
  const catItems = ITEMS.filter(m => (m.category || 'movie') === activeCategory);
  const fullFiltered = getFilteredItems();
  currentFiltered = roulettePick ? [roulettePick] : fullFiltered;
  renderedCount = 0;

  if (isVideo) {{
    const flag = getCountryFlag();
    const totalFlat = catItems.filter(m => getActiveFlatrate(m).length > 0).length;
    const totalWatched = catItems.filter(m => m.watched).length;
    statsPills.innerHTML = `
      <span class="stat-pill">Mostrati: <strong>${{currentFiltered.length}}</strong> / ${{catItems.length}}</span>
      <span class="stat-pill">${{flag}} In Abbonamento ${{streamCountry}}: <strong>${{totalFlat}}</strong></span>
      <span class="stat-pill">👁️ Visti su Trakt: <strong>${{totalWatched}}</strong></span>
    `;
  }} else {{
    statsPills.innerHTML = `
      <span class="stat-pill">Mostrati: <strong>${{currentFiltered.length}}</strong> / ${{catItems.length}}</span>
    `;
  }}

  moviesGrid.innerHTML = '';
  appendNextBatch();
}}

const sentinel = document.getElementById('scrollSentinel');
if (sentinel && 'IntersectionObserver' in window) {{
  const io = new IntersectionObserver((entries) => {{
    if (entries[0].isIntersecting) appendNextBatch();
  }}, {{ rootMargin: '600px' }});
  io.observe(sentinel);
}}

window.toggleCrMenu = function(e, el) {{
  e.stopPropagation();
  const parent = el.parentElement;
  const wasOpen = parent.classList.contains('open');
  document.querySelectorAll('.cr-dropdown.open').forEach(d => d.classList.remove('open'));
  if (!wasOpen) parent.classList.add('open');
}};
document.addEventListener('click', () => {{
  document.querySelectorAll('.cr-dropdown.open').forEach(d => d.classList.remove('open'));
}});

buildInsightsClouds();
render();

// Live Client-Side Trakt Sync (0 secondi di attesa: legge tutte le pagine del profilo pubblico momo-gabr all'apertura della pagina!)
async function fetchAllTraktPages(baseUrl, hdrs) {{
  const all = [];
  for (let page = 1; page <= 20; page++) {{
    const r = await fetch(`${{baseUrl}}?page=${{page}}&limit=250`, {{ headers: hdrs, cache: 'no-store' }});
    if (!r.ok) break;
    const rows = await r.json();
    if (!Array.isArray(rows) || rows.length === 0) break;
    all.push(...rows);
    const totalPages = parseInt(r.headers.get('X-Pagination-Page-Count') || '1', 10);
    if (page >= totalPages || rows.length < 250) break;
  }}
  return all;
}}

async function syncLiveTraktFromBrowser() {{
  const TRAKT_PUB_KEY = '201dc70c5ec6af530f12f079ea1922733f6e1085ad7b02f36d8e011b75bcea7d';
  const hdrs = {{ 'trakt-api-version': '2', 'trakt-api-key': TRAKT_PUB_KEY }};
  try {{
    const [wMov, wShow, rMov, rShow] = await Promise.all([
      fetchAllTraktPages('https://api.trakt.tv/users/momo-gabr/watched/movies', hdrs),
      fetchAllTraktPages('https://api.trakt.tv/users/momo-gabr/watched/shows', hdrs),
      fetchAllTraktPages('https://api.trakt.tv/users/momo-gabr/ratings/movies', hdrs),
      fetchAllTraktPages('https://api.trakt.tv/users/momo-gabr/ratings/shows', hdrs),
    ]);
    const liveWatched = new Set();
    const liveRatings = {{}};
    wMov.forEach(x => {{ const id = x.movie?.ids?.imdb; if (id) liveWatched.add(id); }});
    wShow.forEach(x => {{ const id = x.show?.ids?.imdb; if (id) liveWatched.add(id); }});
    rMov.forEach(x => {{ const id = x.movie?.ids?.imdb; if (id) {{ liveWatched.add(id); liveRatings[id] = x.rating; }} }});
    rShow.forEach(x => {{ const id = x.show?.ids?.imdb; if (id) {{ liveWatched.add(id); liveRatings[id] = x.rating; }} }});
    if (liveWatched.size > 0) {{
      let changed = false;
      ITEMS.forEach(m => {{
        if (!m.imdb_id) return;
        const w = liveWatched.has(m.imdb_id);
        const rt = liveRatings[m.imdb_id];
        if (Boolean(m.watched) !== w || m.my_rating !== rt) {{
          m.watched = w;
          if (rt) m.my_rating = rt; else delete m.my_rating;
          changed = true;
        }}
      }});
      if (changed) render();
    }}
  }} catch (err) {{
    console.warn('Live Trakt sync skip:', err);
  }}
}}
syncLiveTraktFromBrowser();
</script>
</body>
</html>
"""
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    index_path = os.path.join(BASE_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)


def build_or_load_full_5k_index():
    """
    Scarica (una sola volta) l'elenco completo di TUTTI i ~5.337 video del canale
    di Federico Frusciante paginando la playlist master VLUUeiW1AdgyfDyW5wPLjZqH2Q
    tramite YouTube Innertube API e lo salva in frusciante_5k_index.json.
    """
    if os.path.exists(INDEX_5K_PATH):
        try:
            with open(INDEX_5K_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if len(data) > 4000:
                return data
        except Exception:
            pass

    print("📥 Costruisco l'indice completo di tutti i ~5.337 video del canale di Frusciante...")
    videos = []
    seen = set()

    # 1. Prima metti in testa i video delle playlist principali (così i listoni vengono processati per primi)
    for vid, creator, label in discover_frusciante_videos():
        if vid not in seen:
            seen.add(vid)
            videos.append({"video_id": vid, "creator": creator, "hint": label})

    # 2. Poi pagina l'intera playlist Uploads (VLUUeiW1AdgyfDyW5wPLjZqH2Q) fino all'ultimo video del 2006!
    ctx = {
        "client": {
            "clientName": "WEB",
            "clientVersion": "2.20250101.00.00",
            "hl": "it",
            "gl": "IT",
        }
    }
    payload = {"browseId": "VLUUeiW1AdgyfDyW5wPLjZqH2Q", "context": ctx}
    page = 0
    while True:
        page += 1
        try:
            r = requests.post(
                "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false",
                json=payload,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
            if r.status_code != 200:
                break
            text = r.text
            for vid in re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', text):
                if vid not in seen:
                    seen.add(vid)
                    videos.append(
                        {
                            "video_id": vid,
                            "creator": "Federico Frusciante",
                            "hint": "Uploads",
                        }
                    )
            cont_matches = re.findall(
                r'"continuationCommand":\{"token":"([^"]+)"', text
            )
            if not cont_matches:
                break
            payload = {"continuation": cont_matches[-1], "context": ctx}
            if page % 10 == 0:
                print(f"   ... paginazione canale: {len(videos)} video indicizzati finora")
        except Exception as e:
            print(f"   Avviso fine paginazione a pagina {page}: {e}")
            break

    with open(INDEX_5K_PATH, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"✅ Indice completo salvato in {INDEX_5K_PATH}: {len(videos)} video totali!")
    return videos


def raw_lookup_key(
    cat, raw_title, is_classic=False, inferred_year=None, director_hint=""
):
    if cat != "movie":
        return (cat, raw_title.lower().strip(), "any")
    if director_hint:
        era = f"dir:{director_hint.lower()}"
    elif is_classic:
        era = "classic"
    elif inferred_year:
        era = f"y:{(inferred_year // 4) * 4}"
    else:
        era = "general"
    return (cat, raw_title.lower().strip(), era)
def clean_movie_display_title(raw_t):
    if not raw_t:
        return ""
    # Rimuove code tipo "(2013) di Bong Joon-ho" o "- ()" dai titoli
    cleaned = re.sub(r"\s*\(\s*(?:19\d{2}|20\d{2})\s*\)\s*(?:di\s+.*)?$", "", raw_t, flags=re.I)
    cleaned = re.sub(r"\s*[-–—]?\s*\(\s*\)\s*$", "", cleaned)
    return cleaned.strip(" -–—")


def titles_are_compatible_for_same_imdb(t1, t2, orig_title=""):
    """
    Due voci con lo stesso IMDb ID sono lo stesso film SOLO SE:
    - sono identiche (dopo aver tolto '(ANNO) di Regista'), OPPURE
    - una è prefisso/suffisso completo dell'altra col separatore ':' o ' -'
      (es. 'Furiosa' e 'Furiosa: A Mad Max Saga', 'Il castello nel cielo' e 'Laputa - Il castello nel cielo').
    NON fonde mai due film con titoli diversi (es. 'Shin Godzilla' vs 'Godzilla II King of the Monsters')!
    """
    a = clean_movie_display_title(t1).lower()
    b = clean_movie_display_title(t2).lower()
    if a == b:
        return True
    if (
        a.startswith(b + ":")
        or a.startswith(b + " -")
        or b.startswith(a + ":")
        or b.startswith(a + " -")
    ):
        return True
    if a.endswith("- " + b) or b.endswith("- " + a):
        return True
    return False


def dedup_recs_list(recs):
    unique = []
    seen = set()
    for r in recs:
        cr = r.get("creator", "Federico Frusciante")
        # Piero Scaruffi e Roger Ebert contano al massimo 1 volta per opera
        if cr in ("Piero Scaruffi", "Roger Ebert"):
            key = (cr,)
        else:
            key = (cr, r.get("video_id"))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def normalize_and_deduplicate_items(items_dict):
    """
    Unifica automaticamente i doppioni (es. 'Furiosa' e 'Furiosa: A Mad Max Saga',
    o schede rimaste senza IMDb ID con la corrispondente scheda dotata di IMDb ID)
    e rimuove le schede orfane prive di raccomandazioni.
    """
    merged = {}
    by_imdb = {}
    by_alnum_title = {}

    # Ordina in modo da processare PRIMA le schede che hanno già un imdb_id valido
    sorted_items = sorted(
        items_dict.values(),
        key=lambda x: (0 if x.get("imdb_id") else 1, -len(x.get("recommendations", []))),
    )

    for item in sorted_items:
        cat = item.get("category", "movie")
        if cat in ("movie", "show"):
            item["it_title"] = clean_movie_display_title(item.get("it_title", ""))
        item["recommendations"] = dedup_recs_list(item.get("recommendations", []))
        if not item["recommendations"]:
            continue
        t_low = (item.get("it_title") or "").strip().lower()
        t_alnum = re.sub(r"\W+", "", t_low)
        imdb_id = item.get("imdb_id")
        if cat in ("movie", "show") and imdb_id and not item.get("external_url"):
            m_slug = "shows" if (cat == "show" or item.get("media_type") == "show") else "movies"
            item["external_url"] = f"https://app.trakt.tv/{m_slug}/{imdb_id}"

        if cat in ("movie", "show") and imdb_id and imdb_id in by_imdb:
            canon_key = by_imdb[imdb_id]
        elif cat in ("movie", "show") and not imdb_id and t_alnum in by_alnum_title:
            cand_keys = by_alnum_title[t_alnum]
            it_yr = item.get("year")
            matched_key = None
            for ck in cand_keys:
                c_item = merged[ck]
                c_yr = c_item.get("year")
                if not it_yr or not c_yr or abs(int(c_yr) - int(it_yr)) <= 2:
                    matched_key = ck
                    break
            canon_key = (
                matched_key
                if matched_key
                else f"{cat}:{t_low}:{item.get('year') or 'any'}"
            )
        elif cat in ("movie", "show"):
            canon_key = (
                f"{cat}:{t_low}:{imdb_id}"
                if imdb_id
                else f"{cat}:{t_low}:{item.get('year') or 'any'}"
            )
            if imdb_id:
                by_imdb[imdb_id] = canon_key
        else:
            canon_key = item.get("id") or f"{cat}:{t_low}"

        if canon_key in merged:
            merged[canon_key]["recommendations"] = dedup_recs_list(
                merged[canon_key].get("recommendations", [])
                + item.get("recommendations", [])
            )
            if not merged[canon_key].get("ch_flatrate") and item.get("ch_flatrate"):
                merged[canon_key]["ch_flatrate"] = item["ch_flatrate"]
            if not merged[canon_key].get("it_flatrate") and item.get("it_flatrate"):
                merged[canon_key]["it_flatrate"] = item["it_flatrate"]
            if not merged[canon_key].get("director") and item.get("director"):
                merged[canon_key]["director"] = item["director"]
        else:
            item["id"] = canon_key
            merged[canon_key] = item
            if cat == "movie" and imdb_id and t_alnum:
                by_alnum_title.setdefault(t_alnum, []).append(canon_key)
    return merged


def enrich_directors_via_wikidata_sparql(items_dict):
    """
    Recupera in blocco il vero Regista ufficiale (proprietà Wikidata P57) per tutti i film
    dotati di IMDb ID in pochi secondi tramite una query SPARQL batch su Wikidata!
    """
    missing_tt = []
    for it in items_dict.values():
        if it.get("category", "movie") == "movie" and not it.get("director"):
            tt = it.get("imdb_id")
            if tt and tt.startswith("tt"):
                missing_tt.append(tt)

    unique_tt = list(dict.fromkeys(missing_tt))
    if not unique_tt:
        return

    tt_to_dirs = {}
    chunk_size = 120
    for i in range(0, len(unique_tt), chunk_size):
        chunk = unique_tt[i : i + chunk_size]
        values_str = " ".join(f'"{tt}"' for tt in chunk)
        sparql = f"""
        SELECT ?imdb ?dirLabel WHERE {{
          VALUES ?imdb {{ {values_str} }}
          ?item wdt:P345 ?imdb ;
                wdt:P57 ?dir .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
        }}
        """
        try:
            r = requests.post(
                "https://query.wikidata.org/sparql",
                data={"query": sparql, "format": "json"},
                headers=WIKI_HEADERS,
                timeout=20,
            )
            if r.status_code == 200:
                for row in r.json().get("results", {}).get("bindings", []):
                    imdb_val = row.get("imdb", {}).get("value")
                    d_label = row.get("dirLabel", {}).get("value", "")
                    if imdb_val and d_label and not re.match(r"^Q\d+$", d_label):
                        tt_to_dirs.setdefault(imdb_val, [])
                        if d_label not in tt_to_dirs[imdb_val]:
                            tt_to_dirs[imdb_val].append(d_label)
            time.sleep(0.35)
        except Exception:
            pass

    for it in items_dict.values():
        tt = it.get("imdb_id")
        if tt and tt in tt_to_dirs:
            it["director"] = ", ".join(tt_to_dirs[tt][:2])


def save_db(db_data):
    if "items" in db_data:
        db_data["items"] = normalize_and_deduplicate_items(db_data["items"])
        enrich_directors_via_wikidata_sparql(db_data["items"])
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)


def main():
    max_videos = (
        int(sys.argv[1])
        if len(sys.argv) > 1 and sys.argv[1].isdigit()
        else 5500
    )
    headers = get_trakt_headers()
    print("1/4 Recupero catalogo piattaforme streaming Svizzera (CH) e tuo profilo Trakt...")
    ch_sources_map = fetch_ch_sources_map(headers)
    watched_imdb, ratings_imdb = fetch_user_trakt_state(headers)

    db_data = {"items": {}, "processed_videos": [], "last_checkpoint": {}}
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, encoding="utf-8") as f:
                loaded = json.load(f)
                if "items" in loaded:
                    db_data = loaded
        except Exception:
            pass

    if watched_imdb:
        db_data["watched_imdb"] = list(watched_imdb)
        db_data["ratings_imdb"] = ratings_imdb
    else:
        watched_imdb = set(db_data.get("watched_imdb", []))
        ratings_imdb = db_data.get("ratings_imdb", {})

    processed_set = set(db_data.get("processed_videos", []))
    existing_by_raw = {}
    for item_id, it in db_data["items"].items():
        cat = it.get("category", "movie")
        t_low = it.get("it_title", "").lower().strip()
        yr = it.get("year")
        is_cl = isinstance(yr, int) and yr <= 2000
        existing_by_raw[raw_lookup_key(cat, t_low, is_cl, yr)] = item_id
        existing_by_raw[(cat, t_low, "general")] = item_id

    print("2/4 Carico l'indice completo dei ~5.337 video del canale di Frusciante...")
    all_indexed = build_or_load_full_5k_index()
    total_channel = len(all_indexed)

    pending_videos = [
        (idx + 1, entry["video_id"], entry["creator"], entry.get("hint", ""))
        for idx, entry in enumerate(all_indexed)
        if entry["video_id"] not in processed_set
    ][:max_videos]

    last_cp = db_data.get("last_checkpoint", {})
    if last_cp:
        print(
            f"🔄 RIPRENDO DAL CHECKPOINT: ultimo video completato #{last_cp.get('global_index')} / {total_channel} "
            f"({last_cp.get('video_id')} - {last_cp.get('title')})"
        )
    print(
        f"📊 Stato avanzamento: {len(processed_set)} / {total_channel} video già completati. "
        f"In coda adesso: {len(pending_videos)} video."
    )

    def process_one_video(v_tuple):
        g_idx, vid, creator, pl_hint = v_tuple
        try:
            meta = get_video_metadata(vid, pl_hint)
            if not meta:
                return g_idx, vid, creator, None, []
            items = extract_positive_items_from_video(
                vid,
                meta,
                verify_transcripts=(meta["format"] in ("monografia", "single_review")),
            )
            return g_idx, vid, creator, meta, items
        except Exception:
            return g_idx, vid, creator, None, []

    batch_size = 20
    for b_start in range(0, len(pending_videos), batch_size):
        batch = pending_videos[b_start : b_start + batch_size]
        first_idx = batch[0][0]
        last_idx = batch[-1][0]
        print(
            f"\n--- Processo video #{first_idx}..#{last_idx} su {total_channel} "
            f"(Completati: {len(processed_set)}/{total_channel}) ---"
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            video_results = list(pool.map(process_one_video, batch))

        new_raw_to_enrich = []
        seen_in_batch = set()
        for g_idx, vid, creator, meta, raw_items in video_results:
            if not meta:
                continue
            cat = meta["category"]
            for raw in raw_items:
                key = raw_lookup_key(
                    cat,
                    raw["raw_title"],
                    raw.get("is_classic", False),
                    raw.get("inferred_year"),
                    raw.get("director_hint", ""),
                )
                if key not in existing_by_raw and key not in seen_in_batch:
                    seen_in_batch.add(key)
                    new_raw_to_enrich.append(raw)

        if new_raw_to_enrich:
            print(
                f"    + Arricchisco {len(new_raw_to_enrich)} nuove opere promosse..."
            )
            with ThreadPoolExecutor(max_workers=8) as pool:
                enriched_list = list(
                    pool.map(
                        lambda it: enrich_any(it, headers, ch_sources_map),
                        new_raw_to_enrich,
                    )
                )
            for raw, info in zip(new_raw_to_enrich, enriched_list):
                item_id = info["id"]
                if item_id in db_data["items"]:
                    info["recommendations"] = db_data["items"][item_id].get(
                        "recommendations", []
                    )
                db_data["items"][item_id] = info
                r_key = raw_lookup_key(
                    raw["category"],
                    raw["raw_title"],
                    raw.get("is_classic", False),
                    raw.get("inferred_year"),
                    raw.get("director_hint", ""),
                )
                existing_by_raw[r_key] = item_id

        for g_idx, vid, creator, meta, raw_items in video_results:
            if not meta:
                continue
            processed_set.add(vid)
            db_data["last_checkpoint"] = {
                "global_index": g_idx,
                "total_channel_videos": total_channel,
                "video_id": vid,
                "title": meta["title"],
                "timestamp_saved": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            cat = meta["category"]
            for raw in raw_items:
                r_key = raw_lookup_key(
                    cat,
                    raw["raw_title"],
                    raw.get("is_classic", False),
                    raw.get("inferred_year"),
                    raw.get("director_hint", ""),
                )
                item_id = existing_by_raw.get(r_key)
                if not item_id or item_id not in db_data["items"]:
                    continue
                info = db_data["items"][item_id]
                recs = info.get("recommendations", [])
                rec_entry = {
                    "creator": creator,
                    "video_id": vid,
                    "video_title": meta["title"],
                    "timestamp": raw["timestamp"],
                    "seconds": raw["seconds"],
                    "mentioned_as": raw["raw_title"],
                }
                if not any(
                    r["video_id"] == vid and r["timestamp"] == raw["timestamp"]
                    for r in recs
                ):
                    recs.append(rec_entry)
                info["recommendations"] = recs

        db_data["processed_videos"] = list(processed_set)
        save_db(db_data)
        generate_html(db_data, watched_imdb, ratings_imdb)
        cp = db_data.get("last_checkpoint", {})
        print(
            f"    💾 Checkpoint salvato al video #{cp.get('global_index')}/{total_channel} "
            f"[{cp.get('video_id')}] — Totale opere nel Vault: {len(db_data['items'])}"
        )
    counts = {"movie": 0, "music": 0, "book": 0}
    for it in db_data["items"].values():
        counts[it.get("category", "movie")] += 1
    ch_movies = sum(
        1
        for it in db_data["items"].values()
        if it.get("category") == "movie" and it.get("ch_flatrate")
    )
    watched_movies = sum(
        1
        for k, it in db_data["items"].items()
        if it.get("category") == "movie"
        and (it.get("imdb_id") or k) in watched_imdb
    )

    print(
        f"\n✅ Momo Vault Completo generato in: {HTML_PATH}\n"
        f"   • Video del canale processati: {len(processed_set)}\n"
        f"   • 🎬 Film & Serie promossi: {counts['movie']} ({ch_movies} in Streaming CH, {watched_movies} già visti da te su Trakt)\n"
        f"   • 🎵 Dischi Musicali promossi: {counts['music']}\n"
        f"   • 📚 Libri promossi: {counts['book']}"
    )
    if "--no-open" not in sys.argv:
        webbrowser.open(f"file://{HTML_PATH}")


if __name__ == "__main__":
    main()
