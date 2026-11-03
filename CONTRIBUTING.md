# Contributing

Thanks for helping make the Speed Editor work properly on Linux! This is a
small project, so contributing is easy.

## Ways to help

- **Test on other distros / BlueZ versions** — the README documents Arch
  (5.87) and Resolve 21.1.1/21.1.2 (v21.1.1.0010, v21.1.2.0010). Reports from
  Fedora, Ubuntu, openSUSE, other
  BlueZ versions, or newer Resolve builds are very welcome (open an issue
  with the output of `./check.sh` and `./bluez-probe.py`).
- **Resolve binary offsets** — `resolve-patch.py` locates the three
  `cmp eax, <size>` checks by signature, so it does not need offsets per
  build. If a Resolve update changes that shape and the script refuses to
  patch, open an issue (or PR) with what it printed; the checks sit right
  after `HIDIOCGFEATURE` (values 7/32/9 in stock builds) and `objdump -d
  /opt/resolve/bin/resolve | grep -B2 -A6 'c0004807'` shows them.
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
