# Como aplicar o patch no BlueZ (Arch Linux)

O bug do ultimo byte ja esta corrigido no BlueZ upstream (commit
dc2eb1394f, "shared/uhid: Fix size of Get Report reply with a Report ID",
24/set/2026) e deve sair no BlueZ 5.88. Quem nao quiser esperar pode
compilar o 5.87 com o patch de uma linha:

## Via PKGBUILD do Arch

1. Baixe o PKGBUILD oficial do bluez:

       mkdir -p ~/build/bluez && cd ~/build/bluez
       git clone https://gitlab.archlinux.org/archlinux/packaging/packages/bluez.git .
       git checkout tags/5.87-2    # (ou o pkgver atual do repo)

2. Copie o patch para a pasta e adicione na array source/sha256 do PKGBUILD,
   ou mais simples: edite o PKGBUILD e adicione `prepare()`:

       prepare() {
         patch -Np1 -i ../bluez-uhid-getreport-size.patch
       }

3. Compile e instale:

       makepkg -si

4. Reinicie o bluetooth:

       sudo systemctl restart bluetooth

5. Teste:

       ./install.sh --check     # bluez-probe.py deve dizer "OK (tamanho correto)"

6. **Atencao:** com o BlueZ corrigido, o Resolve original REJEITA o painel
   ("BlueZ daemon version too old, reports malformed data.") — os checks
   internos dele esperam o tamanho truncado. Rode o `resolve-patch.sh`
   dentro do container antes de abrir o Resolve:

       podman exec -u root davincibox sh ./resolve-patch.sh

## Nota

O patch muda UMA linha em src/shared/uhid.c (tamanho do reply de
GET_REPORT com Report ID). Sem ele, qualquer leitura de feature/input
report numerado via HID-over-GATT perde o ultimo byte.
