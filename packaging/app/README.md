# SubDrive com janelas

O mesmo que o SubDrive CLI faz (verificar, corrigir, criar PGS, aplicar a sincronia, pendrives, preparar,
atualizar e as regras), numa janela do sistema, sem instalar nada. O código fica em `subdrive_app/` e usa
o pacote `subdrive/` sem mudar nada nele.

    pip install -r requirements-app.txt
    python -m subdrive_app                                   # abre a janela
    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_app
    pyinstaller packaging/app/subdrive_app.spec              # SubDrive.exe / SubDrive / SubDrive.app em dist/
    python tools/app_smoke.py dist/SubDrive smoke            # confere o programa empacotado neste sistema
    python tools/make_app_download.py --program dist/SubDrive --package pacote-uhd.zip --system Linux --output out

O workflow `.github/workflows/app.yml` monta e confere em Windows, macOS (Apple Silicon e Intel) e Linux.
Para a atualização pelo programa, o índice assinado de cada versão precisa das chaves
`app-windows-x86_64`, `app-linux-x86_64`, `app-macos-arm64` e `app-macos-x86_64` (o `.app` vai num ZIP);
o workflow de publicação (`build.yml`, "Publicar esta versão") já monta o SubDrive com janelas nos 4 sistemas,
põe essas chaves no índice assinado e publica os 8 downloads dele junto com os do CLI. Uma versão publicada
sem elas faz a atualização trocar só o pacote do player, com um aviso.

Onde está cada comando e opção do CLI na janela: `PARIDADE.md`.
