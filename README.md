# P2
Dette repository er til P2 gruppe 230 på AAU.

## Overblik
Projektet indeholder et Python-værktøj til at beregne og sammenligne radio-linkbudget/RSRP og SNR samt analysere datarater (uplink/downlink) fra testdata.

Der er to måder at bruge værktøjet på:
- **CLI** via `Rasp.py` (terminal-baseret menu)
- **GUI** via `Rasp_gui.py` (FreeSimpleGUI)

Beregningerne understøtter:
- **FSPL** (Free Space Path Loss)
- **Hata** (empirisk path loss model)

## Dataanalyse (RSRP/SNR og datarater)
Repo’et indeholder to typer data:
- **Cell measurements** (`cell_log.json`): bruges til gennemsnitlig **RSRP** og **SNR**
- **Datarate tests** (`*.test`): bruges til at analysere **uplink/downlink datarater** pr. test

Datarate-filerne ligger i:
- `DATA/core-uplink/test*/` (uplink)
- `DATA/raspberrypi-downlink/test*/` (downlink)

## Indhold i repo
- `Rasp.py`  
  Logik for beregninger, afstand (geodesic), indlæsning af måledata fra JSON og metadata fra CSV.
- `Rasp_gui.py`  
  Grafisk brugerflade til beregninger + visning af data-tabeller (15 m og 120 m tests).
- `DATA/`  
  Måledata og testliste:
  - `DATA/testlist.csv` (testnr, koordinater, timestamp, højde)
  - `DATA/raspberrypi-downlink/test*/cell_log.json` (log med bl.a. `rsrp` og `snr`)
  - `.test`-filer i `DATA/core-uplink/test*/` og `DATA/raspberrypi-downlink/test*/` til datarate-analyse

## Krav
Python 3.x og følgende pakker:
- numpy
- geopy
- matplotlib
- FreeSimpleGUI eller PySimpleGUI

## Installation
1. Installer de nødvendige Python-pakker:
   ```bash
   pip install -r requirements.txt
   ```
2. Sørg for, at `DATA/`-mappen er korrekt placeret i projektstrukturen.

## Sådan køres programmet (CLI)
Kør:
```bash
python Rasp.py
```
CLI’en giver mulighed for:
- Beregning af teoretisk RSRP og SNR baseret på afstand og frekvens.
- Sammenligning af måledata med teoretiske værdier.

## Sådan køres programmet (GUI)
Kør:
```bash
python Rasp_gui.py
```
GUI’en har faner:
- **Teoretisk**: beregn for en afstand
- **Måling**: beregn ud fra drone/gNB koordinater + målt reference
- **Data**: bygger tabeller pr. test (grupperet i ~15 m og ~120 m)
- **Indstillinger**: carrier, BW, SCS, Tx power, gain, thermal noise, noise figure

## Dataformat
### `DATA/testlist.csv`
Indeholder metadata pr. test:
- `testnr`
- `latitude`, `longitude`
- `timestamp`
- `height` (fx 15 eller 120)

### `cell_log.json`
Forventes at indeholde linjer med JSON-objekter som inkluderer felter:
- `rsrp`
- `snr`

Programmet læser filen linje-for-linje og beregner gennemsnit.

### `*.test` (datarate testfiler)
Filerne bruges til at analysere uplink/downlink datarater pr. test (fx ved forskellige mål-hastigheder som 15.6 kbps, 65.5 kbps, 250 kbps, 1 mbps, 4 mbps).

## Kendte ting der skal tilpasses
I `Rasp.py` skal variablen `root_dir` ændres, så den peger på repo’ets data, fx til noget i stil med:
- `DATA/raspberrypi-downlink` eller
- hele `DATA`-mappen

Pt. er den hardcodet til en lokal sti på en bestemt PC.

Hvis du vil, kan jeg også lave et forslag til en lille ændring, så `root_dir` automatisk finder `DATA/` relativt til projektmappen.

## Gruppe
P2 gruppe 230 – Aalborg Universitet (AAU)
