"""SubDrive Desktop: Qt desktop widgets, native file dialogs, no browser/server."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QStandardPaths, QTimer, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QTabWidget, QComboBox, QFileDialog, QLineEdit,
    QCheckBox, QSpinBox, QDoubleSpinBox, QFormLayout, QPlainTextEdit, QProgressBar,
    QMessageBox, QGroupBox, QScrollArea, QSizePolicy)

from . import VERSION, cli, drives, package, pgs, ui, update
from . import desktop_service as service


class Worker(QThread):
    line = Signal(str)
    progress = Signal(int, int, str)
    result = Signal(object)
    failure = Signal(str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action

    def run(self):
        try:
            self.result.emit(self.action(service.Output(self.line.emit, self.progress.emit)))
        except Exception as e:
            if isinstance(e, update.UpdateError):
                message = {"offline": "Não foi possível acessar o servidor. Confira sua conexão e tente novamente.",
                    "signature": "A assinatura da atualização não confere. Nenhum download foi instalado.",
                    "damaged": "O download está incompleto ou não passou na verificação. Tente novamente."}.get(e.code, "Não foi possível atualizar: " + e.code)
            elif isinstance(e, package.PackageError):
                message = "Confira a pasta do pacote: ele está ausente, incompleto ou inválido. " + e.name
            elif isinstance(e, PermissionError):
                message = "Sem permissão para gravar. Escolha uma pasta sua ou confira a proteção do pendrive."
            else:
                message = str(e) or type(e).__name__
            self.failure.emit(message)


def label(text, role=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if role:
        widget.setObjectName(role)
    return widget


def button(text, action, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.PointingHandCursor)
    widget.clicked.connect(action)
    if primary:
        widget.setObjectName("primary")
    return widget


class PathField(QWidget):
    changed = Signal()

    def __init__(self, title, mode="file", placeholder="Selecione…", file_filter="Todos os arquivos (*)"):
        super().__init__()
        self.title, self.mode, self.file_filter = title, mode, file_filter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAccessibleName(title)
        self.edit.textChanged.connect(self.changed)
        layout.addWidget(self.edit, 1)
        browse = button("Escolher…", self.browse)
        browse.setAccessibleName("Escolher: " + title)
        layout.addWidget(browse)

    def browse(self):
        if self.mode == "folder":
            value = QFileDialog.getExistingDirectory(self, self.title, self.edit.text())
        else:
            value, _ = QFileDialog.getOpenFileName(self, self.title, self.edit.text(), self.file_filter)
        if value:
            self.edit.setText(value)

    def path(self):
        return Path(self.edit.text()).expanduser() if self.edit.text().strip() else None


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SubDrive Desktop")
        self.resize(1000, 820)
        self.setMinimumSize(700, 640)
        self.setAcceptDrops(True)
        self.worker = None
        self.paths = []
        self.release = None
        self.result_handler = None
        self.pending_result = None
        self.failed = False
        self.settings = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
        self.settings.mkdir(parents=True, exist_ok=True)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 24, 30, 22)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(label("SubDrive", "brand"))
        header.addStretch()
        header.addWidget(label("DESKTOP  ·  " + VERSION, "muted"))
        layout.addLayout(header)
        layout.addWidget(label("Suas legendas, prontas para o player.", "muted"))
        self.tabs = QTabWidget()
        self.tabs.addTab(self.subtitle_page(), "Legendas")
        self.tabs.addTab(self.drive_page(), "Pendrive")
        self.tabs.addTab(self.help_page(), "Ajuda e atualizações")
        layout.addWidget(self.tabs, 1)
        self.status = label("Pronto para começar", "status")
        self.status.setAccessibleName("Estado da operação")
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Progresso")
        self.progress.hide()
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Resultado e orientações")
        self.log.setPlaceholderText("Os resultados e as orientações aparecem aqui.")
        self.log.setMinimumHeight(110)
        self.log.setMaximumHeight(160)
        self.log.hide()
        layout.addWidget(self.log)
        footer = QHBoxLayout()
        self.save_report_button = button("Salvar relatório…", self.save_report)
        self.save_report_button.setEnabled(False)
        self.log.textChanged.connect(lambda: self.save_report_button.setEnabled(bool(self.log.toPlainText())))
        footer.addWidget(self.save_report_button)
        footer.addStretch()
        self.open_folder_button = button("Abrir pasta da legenda", self.open_folder)
        self.open_folder_button.setEnabled(False)
        footer.addWidget(self.open_folder_button)
        layout.addLayout(footer)
        QShortcut(QKeySequence.Open, self, activated=self.pick_files)
        self.apply_style()

    def apply_style(self):
        # Explicit foreground/background pairs stay legible with a dark OS theme.
        self.setStyleSheet("""
            QWidget { color: #182c3b; font-size: 14px; }
            QMainWindow, QTabWidget::pane, QWidget#page { background: #f4f7fa; }
            QLabel#brand { font-size: 29px; font-weight: 700; color: #075f62; }
            QLabel#heading { font-size: 22px; font-weight: 600; }
            QLabel#muted { color: #526573; }
            QLabel#status { font-weight: 600; padding-top: 3px; }
            QTabWidget::pane { border: 1px solid #d3dfe5; border-radius: 8px; }
            QTabBar::tab { background: #e8eef2; padding: 11px 20px; margin-right: 3px; }
            QTabBar::tab:selected { background: #075f62; color: white; }
            QPushButton { background: white; border: 1px solid #adbec9; border-radius: 6px; padding: 9px 14px; }
            QPushButton:hover { background: #e5f2f1; }
            QPushButton#primary { background: #075f62; color: white; border-color: #075f62; font-weight: 600; }
            QPushButton#primary:hover { background: #084b4d; }
            QPushButton:disabled { background: #edf0f2; color: #63717a; border-color: #d3dfe5; }
            QPushButton#primary:disabled { background: #edf0f2; color: #63717a; border-color: #d3dfe5; }
            QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #137b89; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { background: white; border: 1px solid #adbec9; border-radius: 5px; padding: 7px; selection-background-color: #075f62; selection-color: white; }
            QComboBox QAbstractItemView { background: white; color: #182c3b; selection-background-color: #075f62; selection-color: white; }
            QGroupBox { border: 1px solid #d3dfe5; border-radius: 6px; margin-top: 10px; padding-top: 18px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
            QScrollArea { border: none; background: #f4f7fa; }
            QProgressBar { background: #e0e9ed; border: none; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background: #40a7a0; }
        """)

    def page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        widget.setObjectName("page")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        scroll.setWidget(widget)
        return scroll, layout

    def with_footer(self, page, action):
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page, 1)
        footer = QHBoxLayout()
        footer.setContentsMargins(22, 8, 22, 16)
        footer.addWidget(action)
        layout.addLayout(footer)
        return wrapper

    def subtitle_page(self):
        page, layout = self.page()
        layout.addWidget(label("Comece pela sua legenda", "heading"))
        layout.addWidget(label("Abra um SRT ou SUP, ou arraste arquivos para esta janela.", "muted"))
        row = QHBoxLayout()
        row.addWidget(button("Escolher legendas…", self.pick_files))
        row.addWidget(button("Verificar uma pasta…", self.pick_folder))
        row.addStretch()
        layout.addLayout(row)
        self.selection = label("Nenhum arquivo selecionado", "muted")
        self.selection.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.selection)
        self.action = QComboBox()
        self.action.setAccessibleName("O que fazer com a legenda")
        for text, value in [("Verificar se está pronta", "check"), ("Corrigir legenda SRT", "fix"),
                            ("Criar PGS a partir de SRT", "pgs"), ("Aplicar sincronia do player", "sync")]:
            self.action.addItem(text, value)
        self.action.currentIndexChanged.connect(self.change_action)
        layout.addWidget(self.action)
        self.explanation = label("", "muted")
        layout.addWidget(self.explanation)
        self.pgs_box = QGroupBox("Aparência da legenda")
        form = QFormLayout(self.pgs_box)
        self.font_choice = QComboBox()
        self.font_choice.setAccessibleName("Fonte da legenda PGS")
        for name, key in pgs.FONTS:
            self.font_choice.addItem(name, key)
        self.color = QComboBox()
        self.color.setAccessibleName("Cor da legenda PGS")
        for en, pt, _ in pgs.COLORS:
            self.color.addItem(pt.replace("-", " ").capitalize(), en)
        self.color.setCurrentIndex(1)
        self.size_input = QSpinBox(); self.size_input.setRange(*pgs.SIZES); self.size_input.setValue(48)
        self.size_input.setAccessibleName("Tamanho da letra em pixels")
        self.outline = QDoubleSpinBox(); self.outline.setRange(*pgs.OUTLINES); self.outline.setValue(2); self.outline.setSingleStep(.5)
        self.outline.setAccessibleName("Contorno da letra em pixels")
        self.bold = QCheckBox("Negrito")
        form.addRow("Fonte", self.font_choice); form.addRow("Cor", self.color)
        form.addRow("Tamanho (px)", self.size_input); form.addRow("Contorno (px)", self.outline); form.addRow(self.bold)
        layout.addWidget(self.pgs_box)
        self.advanced_toggle = QCheckBox("Mostrar opções avançadas")
        layout.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        form = QFormLayout(self.advanced)
        form.setContentsMargins(0, 0, 0, 0)
        self.output = QLineEdit(); self.output.setPlaceholderText("Automático: novo arquivo ao lado do original")
        self.output.setAccessibleName("Nome do novo arquivo")
        self.output_label = label("Novo nome")
        form.addRow(self.output_label, self.output)
        self.details = QCheckBox("Mostrar cada problema ou alteração")
        self.credits = QCheckBox("Remover falas que parecem créditos ou propaganda")
        self.points = PathField("Arquivo de pontos", file_filter="Pontos de sincronia (*.txt)")
        self.points_label = label("Pontos de sincronia")
        form.addRow(self.details); form.addRow(self.credits); form.addRow(self.points_label, self.points)
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        layout.addWidget(self.advanced)
        self.run_button = button("Verificar legenda", self.run_subtitle, True)
        layout.addStretch()
        self.change_action()
        return self.with_footer(page, self.run_button)

    def change_action(self):
        action = self.action.currentData()
        descriptions = {"check": "Confira compatibilidade, formato e falas com problemas antes de usar no player.",
            "fix": "Corrige os problemas compatíveis com reparo automático. O original é preservado.",
            "pgs": "Cria uma legenda de imagem em 1080p. O SRT precisa passar na verificação; o original é preservado.",
            "sync": "Aplica os ajustes salvos pelo player na pasta sincronia/ do pendrive. Gera um novo arquivo."}
        self.explanation.setText(descriptions[action])
        self.pgs_box.setVisible(action == "pgs")
        self.details.setVisible(action in ("check", "fix"))
        self.credits.setVisible(action == "fix")
        self.points.setVisible(action == "sync"); self.points_label.setVisible(action == "sync")
        self.output.setVisible(action != "check"); self.output_label.setVisible(action != "check")
        self.run_button.setText({"check": "Verificar legendas", "fix": "Criar legenda corrigida", "pgs": "Criar PGS", "sync": "Criar legenda sincronizada"}[action])
        valid = bool(self.paths)
        if action != "check":
            valid = len(self.paths) == 1 and self.paths[0].is_file()
        if action in ("fix", "pgs"):
            valid = valid and self.paths[0].suffix.lower() == ".srt"
        self.run_button.setEnabled(valid)
        if self.paths and not valid:
            self.explanation.setText("Escolha um único arquivo " + ("SRT" if action in ("fix", "pgs") else "SRT ou SUP") + " para esta ação.")

    def set_paths(self, paths):
        self.paths = [Path(p) for p in paths]
        self.open_folder_button.setEnabled(bool(self.paths))
        self.selection.setText("\n".join(str(p) for p in self.paths[:3]) + (f"\nE mais {len(self.paths)-3} arquivos" if len(self.paths) > 3 else ""))
        self.selection.setToolTip("\n".join(map(str, self.paths)))
        self.output.clear()
        self.points.edit.clear()
        self.change_action()
        self.tabs.setCurrentIndex(0)

    def pick_files(self):
        if self.worker:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Escolher legendas", "", "Legendas (*.srt *.sup *.SRT *.SUP)")
        if files:
            self.set_paths(files)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pasta de legendas")
        if folder:
            self.action.setCurrentIndex(0)
            self.set_paths([folder])

    def run_subtitle(self):
        options = dict(show=self.details.isChecked(), output=self.output.text().strip() or None,
            remove_credits=self.credits.isChecked(), points=self.points.path(),
            font=self.font_choice.currentData(), color=self.color.currentData(), size=self.size_input.value(),
            outline=self.outline.value(), bold=self.bold.isChecked())
        paths, action = list(self.paths), self.action.currentData()
        self.start(lambda out: service.subtitle_action(action, paths, options, out))

    def drive_page(self):
        page, layout = self.page()
        layout.addWidget(label("Prepare o pendrive", "heading"))
        layout.addWidget(label("Para Panasonic DP-UB450, DP-UB150 e DP-UB154 dos EUA, firmware 1.13. O pendrive deve usar FAT32 e MBR.", "muted"))
        row = QHBoxLayout()
        self.drive = QComboBox(); self.drive.setAccessibleName("Pendrive de destino")
        self.drive.addItem("Conecte o pendrive e clique em Procurar", None)
        row.addWidget(self.drive, 1)
        row.addWidget(button("Procurar pendrives", self.scan_drives))
        layout.addLayout(row)
        self.drive.currentIndexChanged.connect(self.drive_changed)
        self.drive_info = label("Nenhum pendrive selecionado.", "muted")
        layout.addWidget(self.drive_info)
        self.package = PathField("Pasta do pacote do player", "folder", "Pasta extraída do download do SubDrive")
        found = package.find_package(service.program_dir())
        if found:
            self.package.edit.setText(str(found))
        layout.addWidget(label("Pacote do player")); layout.addWidget(self.package)
        layout.addWidget(button("Obter pacote no site do projeto", lambda: QDesktopServices.openUrl(QUrl("https://github.com/michaelfdias/subdrive/releases"))))
        self.usb_advanced_toggle = QCheckBox("Mostrar opções avançadas")
        layout.addWidget(self.usb_advanced_toggle)
        advanced = QWidget(); form = QFormLayout(advanced); form.setContentsMargins(0, 0, 0, 0)
        self.firmware = PathField("Firmware oficial (ZIP)", file_filter="Firmware (*.zip)", placeholder="Baixar automaticamente se necessário")
        self.replace = QCheckBox("Substituir legendas com o mesmo nome pelas do pacote")
        form.addRow("Firmware local", self.firmware); form.addRow(self.replace)
        advanced.hide(); self.usb_advanced_toggle.toggled.connect(advanced.setVisible)
        layout.addWidget(advanced)
        self.eject = QCheckBox("Ejetar com segurança ao terminar"); self.eject.setChecked(True)
        layout.addWidget(self.eject)
        layout.addWidget(label("Primeiro você verá o resumo das alterações. O firmware oficial será baixado se necessário. Este aplicativo não formata o pendrive.", "muted"))
        layout.addWidget(button("Ejetar pendrive selecionado", self.eject_drive))
        layout.addStretch()
        return self.with_footer(page, button("Revisar preparação…", self.preview_prepare, True))

    def scan_drives(self):
        def scan(out):
            found = drives.find()
            if not found:
                out.line("Nenhum pendrive encontrado. Conecte um pendrive montado pelo sistema e procure novamente.")
            for d in found:
                ui.render_drive(out, d, package.installed(d.path))
                if not d.ok:
                    ui.format_help(out, d)
            return found
        def received(found):
            self.drive.clear()
            for d in found:
                self.drive.addItem(f"{d.label or 'Pendrive'} — {d.path}", d)
            if not found:
                self.drive.addItem("Nenhum pendrive encontrado", None)
        self.start(scan, received)

    def drive_changed(self):
        d = self.drive.currentData()
        if not d:
            self.drive_info.setText("Nenhum pendrive selecionado.")
            return
        self.drive_info.setText(f"{d.filesystem or 'Formato desconhecido'} · {d.scheme or 'Partição desconhecida'} · {ui._size(d.free)} livres de {ui._size(d.size)}\n" + ("Compatível com o player." if d.ok else "Precisa de ajuste. Veja as orientações no resultado."))

    def preview_prepare(self):
        d, folder = self.drive.currentData(), self.package.path()
        if not d or not folder:
            self.show_error("Escolha um pendrive e a pasta do pacote do player primeiro.")
            return
        replace, eject, firmware = self.replace.isChecked(), self.eject.isChecked(), self.firmware.path()
        def reviewed(preview):
            drive, pkg, plan = preview
            message = (f"Destino: {drive.label or 'Pendrive'}\n{drive.path}\n\n"
                f"SubDrive {pkg.version} · {pkg.platform}\n"
                f"Copiar: {len(plan.write)} arquivos ({ui._size(plan.needed)})\n"
                f"Manter: {len(plan.kept)} legendas existentes\n"
                f"Remover: {len(plan.stale)} fontes antigas\n\n"
                + ("Legendas com o mesmo nome serão substituídas.\n" if replace else "Suas legendas serão preservadas.\n")
                + "Preferências, sincronia e relatórios serão preservados.")
            if QMessageBox.question(self, "Confirmar preparação", message, QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes:
                self.start(lambda out: service.prepare_apply(preview, replace, eject, out))
        self.start(lambda out: service.prepare_preview(folder, d.path, replace, firmware, out), reviewed)

    def eject_drive(self):
        d = self.drive.currentData()
        if not d:
            self.show_error("Selecione um pendrive primeiro.")
            return
        def action(out):
            if not drives.eject(d):
                raise ValueError("Não foi possível ejetar. Feche arquivos abertos nesse pendrive e tente novamente pelo sistema.")
            out.line("Pendrive ejetado. Pode retirar com segurança.")
            return 0
        self.start(action)

    def help_page(self):
        page, layout = self.page()
        layout.addWidget(label("Tudo pronto para a próxima sessão", "heading"))
        layout.addWidget(label("Consulte as regras de compatibilidade ou procure atualizações quando quiser.", "muted"))
        layout.addWidget(button("O que é verificado e por quê", lambda: self.start(lambda out: ui.render_rules(out))))
        layout.addWidget(button("Abrir guia do SubDrive", lambda: QDesktopServices.openUrl(QUrl("https://michaelfdias.github.io/subdrive/guia.html"))))
        group = QGroupBox("Atualizações verificadas por assinatura")
        inner = QVBoxLayout(group)
        self.beta = QCheckBox("Incluir versões de teste (beta)")
        self.beta.setChecked(update.wants_beta(self.settings))
        inner.addWidget(self.beta)
        inner.addWidget(label("O pacote selecionado na aba Pendrive pode ser atualizado aqui. A edição gráfica só aceita executáveis desktop assinados.", "muted"))
        inner.addWidget(button("Procurar atualização", self.check_update))
        self.install = button("Instalar atualização…", self.install_update, True)
        self.install.setEnabled(False)
        inner.addWidget(self.install)
        layout.addWidget(group)
        layout.addWidget(label("SubDrive original © Michael Dias · MIT\nInterface desktop baseada no mesmo motor de legendas. Qt/PySide6: LGPLv3; licenças das fontes incluídas no pacote.", "muted"))
        layout.addStretch()
        return page

    def check_update(self):
        folder, beta = self.package.path(), self.beta.isChecked()
        self.release = None; self.install.setEnabled(False)
        def found(rel):
            self.release = rel
            self.release_folder = folder
            self.install.setEnabled(rel is not None)
        self.start(lambda out: service.find_update(folder, beta, self.settings, out), found)

    def install_update(self):
        if not self.release:
            return
        if QMessageBox.question(self, "Instalar atualização", f"Instalar a versão {self.release.version}?\nOs downloads serão verificados antes de substituir arquivos.", QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        rel, folder = self.release, self.release_folder
        self.start(lambda out: service.install_update(rel, folder, out))

    def start(self, action, handler=None):
        if self.worker:
            return
        self.result_handler = handler
        self.failed = False
        self.pending_result = None
        self.log.clear()
        self.log.show()
        self.status.setText("Em andamento… Aguarde antes de fechar ou retirar o pendrive.")
        self.progress.setRange(0, 0); self.progress.show()
        self.tabs.setEnabled(False)
        self.worker = Worker(action, self)
        self.worker.line.connect(self.log.appendPlainText)
        self.worker.progress.connect(self.on_progress)
        self.worker.failure.connect(self.on_failure)
        self.worker.result.connect(self.on_result)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def on_result(self, value):
        self.pending_result = value

    def on_failure(self, text):
        self.failed = True
        self.log.appendPlainText(text)
        self.status.setText("Não foi possível concluir. Veja a orientação abaixo.")

    def on_progress(self, done, total, text):
        self.progress.setRange(0, 100 if total else 0)
        if total:
            self.progress.setValue(int(100 * done / total))
        self.status.setText(text)

    def finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.tabs.setEnabled(True)
        self.progress.hide()
        value, handler = self.pending_result, self.result_handler
        if not self.failed:
            self.status.setText("Concluído. Confira o resultado abaixo." if not isinstance(value, int) or value == 0 else "Há itens que precisam de atenção. Confira o resultado abaixo.")
            if handler:
                handler(value)

    def show_error(self, message):
        QMessageBox.warning(self, "Confira antes de continuar", message)

    def save_report(self):
        name, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", "SubDrive-relatorio.txt", "Texto (*.txt)")
        if name:
            try:
                Path(name).write_text(self.log.toPlainText(), encoding="utf-8")
            except OSError as e:
                self.show_error(str(e))

    def open_folder(self):
        if self.paths:
            p = self.paths[0]
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p if p.is_dir() else p.parent)))

    def dragEnterEvent(self, event):
        if not self.worker and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.worker:
            return
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        if any(not p.is_dir() and p.suffix.lower() not in (".srt", ".sup") for p in paths):
            self.show_error("Arraste legendas SRT, SUP ou pastas de legendas.")
            return
        self.set_paths(paths)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker:
            self.show_error("Uma operação está em andamento. Aguarde a conclusão antes de fechar.")
            event.ignore()
        else:
            event.accept()


class DesktopApplication(QApplication):
    opened = Signal(str)

    def event(self, event):
        if event.type() == QEvent.FileOpen:
            self.opened.emit(event.file())
            return True
        return super().event(event)


def main():
    app = DesktopApplication(sys.argv)
    app.setApplicationName("SubDrive Desktop")
    app.setOrganizationName("SubDrive")
    app.setFont(QFont("", 11))
    icon = Path(__file__).parent / "assets" / "icone.svg"
    if not icon.exists():
        icon = Path(__file__).parent.parent / "docs" / "img" / "icone.svg"
    app.setWindowIcon(QIcon(str(icon)))
    window = Window()
    app.opened.connect(lambda path: window.set_paths([path]) if not window.worker else None)
    window.show()
    if len(sys.argv) > 1 and sys.argv[1] != "--smoke-test":
        window.set_paths([Path(p) for p in sys.argv[1:]])
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
