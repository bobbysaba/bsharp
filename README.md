# bsharp

A command-line tool and Python library for generating atmospheric sounding figures from SPC-format data files. Built on the backend of the SHARPpy library.

## Credit

This project is derived from [SHARPpy (Sounding/Hodograph Analysis and Research Program in Python)](https://github.com/sharppy/SHARPpy), developed by Patrick Marsh, Kelton Halbert, Greg Blumberg, and Tim Supinie. The atmospheric analysis routines (`sharptab`), visualization widgets (`viz`), and database assets are sourced directly from that project. bsharp strips the interactive GUI and data-fetching infrastructure, leaving the core analysis and rendering engine accessible as an installable CLI and library.

---

## Installation

```bash
conda env create -f environment.yml
conda activate bsharp
pip install -e .
```

## CLI usage

```bash
# Output named automatically: YYYYMMDD_HHMM_<station>.png
bsharp input.txt

# Specify output path
bsharp input.txt -o my_output.png
```

## Scripting

```python
from bsharp.io.spc_decoder import SPCDecoder
from bsharp.sharptab import profile, params, winds, interp, utils

# From a file
dec = SPCDecoder('input.txt')
prof_col = dec.getProfiles()
prof = prof_col.getHighlightedProf()

# Or build a profile from raw arrays
prof = profile.create_profile(
    profile='convective',
    pres=pres_array,   # hPa
    hght=hght_array,   # m
    tmpc=tmpc_array,   # C
    dwpc=dwpc_array,   # C
    wdir=wdir_array,   # deg
    wspd=wspd_array,   # kts
    strictQC=False
)

# Access computed parameters
print(prof.mupcl.bplus)    # MUCAPE
print(prof.mlpcl.lclhght)  # MLLCL
print(prof.pwat)           # PWV

srwind = params.bunkers_storm_motion(prof)
srh = winds.helicity(prof, 0, 3000., stu=srwind[0], stv=srwind[1])
```

## Input format

Files must be in SPC format:

```
%TITLE%
STATION_ID YYMMDD/HHMM
%RAW%
pressure,height,temperature,dewpoint,wind_dir,wind_speed
...
%END%
```

Columns are comma-delimited. Units: pressure (hPa), height (m), temperature (C), dewpoint (C), wind direction (deg), wind speed (kts).

## Project structure

```
bsharp/
├── pyproject.toml
├── environment.yml
├── plot_sounding.py       # convenience shim (works without installing)
└── bsharp/
    ├── __init__.py        # __version__
    ├── cli.py             # bsharp entry point
    ├── config.py          # Qt config management
    ├── utils.py           # Qt utilities
    ├── viz/               # Qt rendering widgets (SPCWindow, skew, hodo, etc.)
    ├── sharptab/          # atmospheric analysis (params, winds, interp, thermo, ...)
    ├── io/                # SPC file decoder
    └── databases/         # SARS analogues, PWV climatology
```
