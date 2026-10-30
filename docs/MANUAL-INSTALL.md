# Instalação manual do Resolve no davincibox (quando o instalador oficial falha)

O instalador headless do DaVinci Resolve 21.1.2 (`AppRun -i -a -y`) falha
com `Error: Installer failed / Failed to create temporary files` em alguns
ambientes (inclusive no davincibox, onde o `/tmp` do container é um tmpfs
compartilhado com o host). Ele sai com código 0, então o `setup-davinci`
não percebe e reporta sucesso.

Felizmente o instalador é só um copiador de arquivos com alguns hooks
(vazios). Dá para instalar manualmente — é o que o PKGBUILD do AUR faz.

## Passos (host + container davincibox)

1. Baixar o instalador (Studio) via API da Blackmagic:

       curl -s "https://www.blackmagicdesign.com/api/support/latest-stable-version/davinci-resolve-studio/linux" \
         | grep -oE '"downloadId":"[^"]+"'
       # POST em https://www.blackmagicdesign.com/api/register/us/download/<id>
       # com o JSON de cadastro (veja o davinci.sh do LinuxToys) -> URL do zip
       curl -L -o DaVinci_Resolve_Studio_X_Linux.zip "<url>"

2. Extrair:

       unzip DaVinci_Resolve_Studio_X_Linux.zip
       chmod +x DaVinci_Resolve_Studio_X_Linux.run
       ./DaVinci_Resolve_Studio_X_Linux.run --appimage-extract

3. Copiar a árvore para o container (precisa de ~16 GB livres no `/home`):

       podman exec davincibox sh -c 'rm -rf /opt/resolve/* ; cp -a ~/Downloads/squashfs-root/. /opt/resolve/'

4. Aplicar os workarounds do zelikos dentro do container:

       podman exec davincibox sh -c '
         find /opt/resolve/bin -executable -type f -exec sudo patchelf \
           --add-needed libglib-2.0.so.0 --add-needed libgdk_pixbuf-2.0.so.0 \
           --add-needed libgio-2.0.so.0 --add-needed libgmodule-2.0.so.0 {} \; ;
         sudo mv /opt/resolve/BlackmagicRAWPlayer/BlackmagicRawAPI/libDecoderOpenCL.so \
                 /opt/resolve/BlackmagicRAWPlayer/BlackmagicRawAPI/libDecoderOpenCL.so.bak ;
         sudo mv /opt/resolve/BlackmagicRAWSpeedTest/BlackmagicRawAPI/libDecoderOpenCL.so \
                 /opt/resolve/BlackmagicRAWSpeedTest/BlackmagicRawAPI/libDecoderOpenCL.so.bak'

5. Aplicar o patch de 3 bytes (checks do Bluetooth):

       podman exec -u root davincibox sh resolve-patch.sh

6. Limpar (libera ~16 GB):

       rm -rf ~/Downloads/squashfs-root ~/Downloads/DaVinci_Resolve_Studio_X_Linux.{zip,run}

7. Abrir: o launcher `DaVinci Resolve` do menu, ou:

       distrobox enter davincibox -- /usr/bin/run-davinci /opt/resolve/bin/resolve
