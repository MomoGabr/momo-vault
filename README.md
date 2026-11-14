# 🎬 Momo Vault — Cinema, Serie TV, Musica & Libri (`🇨🇭 CH` · `🇮🇹 IT` · `🇳🇴 NO`)

[![Daily Auto-Sync](https://github.com/MomoGabr/momo-vault/actions/workflows/auto_sync.yml/badge.svg)](https://github.com/MomoGabr/momo-vault/actions/workflows/auto_sync.yml)

### 🌐 👉 [**APRI LA WEB APP / PWA LIVE: https://momogabr.github.io/momo-vault/**](https://momogabr.github.io/momo-vault/) 👈
### 📄 👉 [**REGISTRO GIORNALIERO NUOVI VIDEO & RECENSIONI (`daily_updates.txt`)**](daily_updates.txt) 👈

---

## 🏛️ I 7 Autori del Vault (Solo Consigli Positivi Verificati)

| Autore | Ambito | Regola di Filtro Positivo |
| :--- | :--- | :--- |
| 🔴 **Federico Frusciante** | Cinema, Serie TV, Musica, Libri | Rubriche cult (*Classici*, *Imperdibili*, *In Oriente*, *Underground*, *Monografie*, *Meglio dell'Anno*, *Consigli del Mese* esclusi gli ultimi 3 sconsigli) + recensioni singole verificate da parlato/descrizione |
| 🔵 **Victorlaszlo88** | Cinema & Serie TV | Classifiche *Top*, *ViConsiglio*, *CULT* + recensioni singole (*MovieBlog*, *FlashVic*) verificate da descrizione e parlato finale |
| 🩵 **Francesco Alò** | Cinema & Serie TV | Classifiche e recensioni singole verificate da parlato finale (`YouTubeTranscriptApi`) e sentiment |
| 🟣 **Piero Scaruffi** | Cinema, Musica, Libri | Solo film `>= 7.0/10`, dischi `>= 7.5/10` + *Best Jazz*, e liste romanzi storici (`scaruffi.com`) |
| 🟡 **Roger Ebert** | Cinema & Serie TV | Solo film e serie con **`>= 3.0 ★ su 4`** (*1967–2026+*) + collezione *Great Movies* (`4/4 ★`) |
| 🟠 **Mr. Marra** | Cinema & Serie TV | Rubriche *CULT* e recensioni positive |
| 🟢 **I Criticoni** | Cinema & Serie TV | Rubriche *CULT*, *Criticoni Talk* e recensioni corali positive |

---

## ⚡ Struttura del Repository

```text
momo-vault/
├── .github/workflows/
│   └── auto_sync.yml          # GitHub Action automatica (3x/giorno: 07:23, 13:23, 19:23 UTC)
├── docs/                      # Sito web / PWA servito da GitHub Pages
│   ├── index.html             # App completa (installabile su iPhone/Android/Mac)
│   ├── daily_updates.txt      # Copia web del registro aggiornamenti giornalieri
│   ├── manifest.json          # Configurazione PWA
│   ├── icon-180.png           # Icona Apple Touch
│   └── icon-512.png           # Icona PWA HD
├── cine_db.json               # Database master (10.500+ opere arricchite con IMDb, Wikidata e JustWatch)
├── daily_updates.txt          # Registro cronologico testuale dei nuovi video/recensioni aggiunti
├── daily_sync.py              # Motore di sincronizzazione giornaliera (YouTube + Ebert + Scaruffi + Trakt + JustWatch)
├── cine_dashboard.py          # Motore di arricchimento e generatore UI/PWA
├── multi_creator_scanner.py   # Analizzatore YouTube (trascrizioni parlate, capitoli, commenti fissati)
└── requirements.txt           # Dipendenze Python per GitHub Actions
```
