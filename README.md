# bt-buds

Noctalia (v5+) bar widget + panel + service for **Redmi Buds 6 Lite** over Bluetooth:
live battery (L/R/case), ANC / transparency / off modes, Bluetooth codec switch,
and a real 5-band software EQ powered by ffmpeg — all from the bar.

## Features

- **Bar widget** — connection glyph, name / battery / mode pages (right-click),
  middle-click cycles ANC → transparency → off, tooltip with codec, mode and battery
- **Panel (340×620)** — hero image, battery columns with bars, noise-control
  buttons, codec select (SBC / SBC-XQ / AAC), EQ select, connect/disconnect,
  RU/EN language switch
- **Real EQ** — apps → `eq_in` null sink → ffmpeg DSP → buds; presets:
  Normal (flat), More Bass (+7 dB lowshelf), Boost Vocals, More Highs.
  Measured: +5.6 dB @ 100 Hz, +4.6 dB @ 8 kHz
- **Sound effects** on mode/language switch (freedesktop stereo sounds)
- **Persistent RFCOMM daemon** (ch 29) — one session, instant mode/battery
  commands over a unix socket (no EBUSY races)

## Requirements

- Noctalia 5.1+ (plugin API 21)
- `python3` (stdlib only), `ffmpeg` (with `ffplay` for sounds), `pactl` (PipeWire)
- Redmi Buds 6 Lite paired via Bluetooth (RFCOMM channel 29)

> The buds MAC is currently hardcoded in `buds-daemon.py`
> (`MAC = "78:99:87:AD:44:BA"`). Change it there for another headset.

## Install

```bash
git clone https://github.com/0swift135/bt-buds.git ~/.local/share/noctalia/plugins/bt-buds
cp ~/.local/share/noctalia/plugins/bt-buds/buds-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now buds-daemon.service
noctalia msg plugins enable jswift/bt-buds
```

## Usage

- **Left click** widget — open panel · **Right click** — name/battery/mode page ·
  **Middle click** — cycle ANC/TR/off
- **Panel** — noise-control buttons call `mode.py`, codec select calls
  `pactl set-card-profile` (the EQ chain is rebuilt automatically afterwards),
  EQ select calls `eq.py set <preset>`
- **Language** — globe button cycles Auto → RU → EN

## How it works

```
apps ──► eq_in (module-null-sink) ──► ffmpeg (bass/treble/peaking) ──► bluez buds
                                            ▲
panel ──► service.luau ──► eq.py set/get ──┘         (ok <preset> / err <reason>)

panel ──► service.luau ──► mode.py / battery.py ──► buds-daemon (unix sock) ──► RFCOMM ch29
```

- `eq.py` finds the `bluez_output.*` sink dynamically, pins ffmpeg's output to
  it (avoids feedback loop into `eq_in`), and routes app streams into `eq_in`.
  Runs in ~1.5 s to fit the plugin worker timeout; carries its own
  `XDG_RUNTIME_DIR`/`DBUS` env because the sandbox provides none.
- Codec profile switches destroy and recreate the bluez sink, so the service
  rebuilds the EQ chain after every switch.

## Files

| File | Role |
|---|---|
| `service.luau` | state, IPC (`refresh/hold/toggle/set_mode/cycle_mode/set_codec/cycle_codec/set_eq/cycle_eq/cycle_lang`) |
| `panel.luau` | floating panel UI (EN/RU via `translations/`) |
| `widget.luau` | bar widget + tooltip + gestures |
| `eq.py` | ffmpeg EQ chain manager (`set`/`get`) |
| `buds-daemon.py` | persistent RFCOMM session + unix-socket server |
| `buds-daemon.service` | systemd user unit for the daemon |
| `buds_proto.py` | Xiaomi framing/auth/battery protocol |
| `mode.py` / `battery.py` | thin daemon clients |
| `plugin.toml` | manifest (panel 340×620) |

## License

MIT
