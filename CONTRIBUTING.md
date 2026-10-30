# Contributing

Thanks for helping make the Speed Editor work properly on Linux! This is a
small project, so contributing is easy.

## Ways to help

- **Test on other distros / BlueZ versions** — the README documents Arch
  (5.87) and Resolve 19.1.x. Reports from Fedora, Ubuntu, openSUSE, other
  BlueZ versions, or newer Resolve builds are very welcome (open an issue
  with the output of `./check.sh` and `./bluez-probe.py`).
- **Resolve binary offsets** — `resolve-patch.sh` holds offsets for 19.1.x.
  If a Resolve update moves them, please open an issue (or PR) with the new
  offsets. The offsets come from three `cmp eax, <size>` checks after
  `HIDIOCGFEATURE` (the values 7/32/9 in stock builds); `objdump -d
  /opt/resolve/bin/resolve | grep -B2 -A6 'c0004807'` finds them.
- **Other Blackmagic panels** — the udev rule already covers the Replay
  Editor (`DA11`) and ATEM Micro Panel (`BEF0`), untested. If you own one,
  try it and tell us.
- **Firmware variants** — if a newer Speed Editor firmware changes the
  `0x06` auth handshake, the tables in `read_hid.py` need updating (they are
  the public constants from `blackmagic-misc`).
- **Docs and translations** — README, forum post (pt-BR), anything that
  makes this easier to find.

## Rules of thumb

- Keep the license headers honest: code you add is MIT; anything derived
  from another project keeps its attribution in `NOTICE`.
- Test before opening a PR: `./check.sh` first, then a real pairing +
  Resolve run if you touched the auth path.
- Be kind. No formal code of conduct, just don't be a jerk.

## License

MIT for this repository's code. Third-party material is credited in
[NOTICE](NOTICE).
