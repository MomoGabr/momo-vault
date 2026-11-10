# 🎬 Momo Vault — Cinema, Musica & Libri (🇨🇭 CH / 🇮🇹 IT)

### 🌐 👉 [**APRI LA WEB APP LIVE: https://momogabr.github.io/momo-vault/**](https://momogabr.github.io/momo-vault/) 👈

---

## 📌 Caratteristiche
- **7 Fonti / Cinefili integrati:**
  - 🔴 **Federico Frusciante** (Cinema, Serie TV, Musica, Libri)
  - 🔵 **Victorlaszlo88**
  - 🩵 **Francesco Alò**
  - 🟣 **Piero Scaruffi** (Cinema & Musica)
  - 🟡 **Roger Ebert / RogerEbert.com** (*Great Movies* + Recensioni storiche e recenti `2017–2026`)
  - 🟠 **Mr. Marra**
  - 🟢 **I Criticoni**
- **Sincronizzazione Automatica Giornaliera (`GitHub Actions`):**
  - Ogni giorno alle **08:30** (`06:30 UTC`) il workflow [`.github/workflows/auto_sync.yml`](.github/workflows/auto_sync.yml) esegue `daily_sync.py`:
    1. Controlla gli ultimi video pubblicati sui 5 canali YouTube;
    2. Legge le ultime recensioni positive da `rogerebert.com/reviews/feed`;
    3. Sincronizza i **Film e Serie TV Visti e Votati su Trakt**;
    4. Aggiorna i cataloghi streaming **🇨🇭 Svizzera (CH)** e **🇮🇹 Italia (IT)** e pubblica la pagina aggiornata su GitHub Pages.
