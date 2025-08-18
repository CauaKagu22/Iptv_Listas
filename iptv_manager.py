"""
IPTV M3U8 Manager - Aplicação Desktop em Python (v2.1 - CORRIGIDO)

Este script é uma conversão completa do projeto React 'iptv-m3u8-manager'
para uma aplicação de desktop usando PySide6.

Funcionalidades:
- Adicionar, Editar e Deletar canais de IPTV.
- Importar arquivos .m3u8.
- Salvar a lista de canais localmente em um arquivo 'channels.json'.
- Salvar a playlist .m3u8 diretamente na pasta do programa.
- Visualização em grade com logos carregados da web de forma assíncrona.
- Reordenar canais com Drag and Drop.

Para executar:
1. Instale as dependências: python -m pip install PySide6 requests
2. Execute o script: python iptv_manager.py
"""

import sys
import os
import json
import re
import uuid
import requests
from dataclasses import dataclass, asdict

from PySide6.QtCore import (
    Qt, QSize, QRunnable, QThreadPool, QObject, Signal,
    QByteArray, QBuffer, QIODevice
)
from PySide6.QtGui import QPixmap, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QDialogButtonBox, QListWidget, QListWidgetItem,
    QLabel, QListView, QFrame, QScrollArea, QGridLayout,
    QSizePolicy, QInputDialog
)

# --- Constantes e Estilo ---

DATA_FILE = "channels.json"
APP_STYLE = """
    QWidget {
        background-color: #1f2937;
        color: #f9fafb;
        font-family: Segoe UI, sans-serif;
    }
    QMainWindow, QDialog {
        background-color: #111827;
    }
    QLabel {
        background-color: transparent;
    }
    QPushButton {
        background-color: #2563eb;
        color: white;
        border: none;
        padding: 10px 15px;
        border-radius: 6px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #1e40af;
    }
    QPushButton#secondary {
        background-color: #4b5563;
    }
    QPushButton#secondary:hover {
        background-color: #6b7280;
    }
    QLineEdit {
        background-color: #374151;
        border: 1px solid #4b5563;
        padding: 8px;
        border-radius: 6px;
    }
    QListWidget {
        border: 1px solid #374151;
        border-radius: 6px;
    }
    QListWidget::item {
        border: none;
        padding: 5px;
    }
    QDialog, QMessageBox {
        border: 1px solid #374151;
    }
    QScrollBar:vertical {
        border: none;
        background: #374151;
        width: 10px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:vertical {
        background: #4b5563;
        min-height: 20px;
        border-radius: 5px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
"""

# --- Modelo de Dados ---

@dataclass
class Channel:
    id: str
    name: str
    url: str
    logo: str
    group: str
    tvgId: str

# --- Lógica de Gerenciamento de Dados (localStorage) ---

def save_channels(channels: list[Channel]):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([asdict(ch) for ch in channels], f, indent=4)
    except IOError as e:
        print(f"Erro ao salvar canais: {e}")

def load_channels() -> list[Channel]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [Channel(**item) for item in data]
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Erro ao carregar canais: {e}")
        return []

# --- Lógica de M3U8 (Parser e Gerador) ---

def generate_m3u8_content(channels: list[Channel]) -> str:
    content = "#EXTM3U\n"
    for channel in channels:
        name = channel.name.strip()
        logo = channel.logo.strip()
        group = channel.group.strip()
        tvg_id = channel.tvgId.strip()
        url = channel.url.strip()
        content += (
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" '
            f'tvg-logo="{logo}" group-title="{group}",{name}\n'
            f'{url}\n'
        )
    return content

def parse_m3u8_content(content: str) -> list[dict]:
    if not content.strip().startswith('#EXTM3U'):
        raise ValueError("Arquivo M3U8 inválido: Cabeçalho #EXTM3U não encontrado.")

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    parsed_channels = []
    
    for i in range(1, len(lines), 2):
        info_line = lines[i]
        url_line = lines[i+1] if (i + 1) < len(lines) else ''

        if info_line.startswith('#EXTINF:'):
            name = info_line.split(',')[-1]
            tvg_id = re.search(r'tvg-id="([^"]*)"', info_line)
            tvg_logo = re.search(r'tvg-logo="([^"]*)"', info_line)
            group_title = re.search(r'group-title="([^"]*)"', info_line)

            parsed_channels.append({
                "name": name,
                "url": url_line,
                "logo": tvg_logo.group(1) if tvg_logo else "",
                "group": group_title.group(1) if group_title else "",
                "tvgId": tvg_id.group(1) if tvg_id else "",
            })
    return parsed_channels

# --- Tarefas em Background (para carregar imagens sem travar) ---

class WorkerSignals(QObject):
    finished = Signal(bytes)
    error = Signal()

class ImageDownloader(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()

    def run(self):
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            self.signals.finished.emit(response.content)
        except (requests.RequestException, IOError):
            self.signals.error.emit()

# --- Componentes da Interface Gráfica (Widgets) ---

class ChannelForm(QDialog):
    def __init__(self, parent=None, channel: Channel = None):
        super().__init__(parent)
        self.setWindowTitle("Editar Canal" if channel else "Adicionar Novo Canal")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.url_input = QLineEdit()
        self.group_input = QLineEdit()
        self.logo_input = QLineEdit()
        self.tvgid_input = QLineEdit()
        
        form_layout.addRow("Nome*:", self.name_input)
        form_layout.addRow("URL do Stream*:", self.url_input)
        form_layout.addRow("Grupo*:", self.group_input)
        form_layout.addRow("URL do Logo:", self.logo_input)
        form_layout.addRow("TVG ID:", self.tvgid_input)
        layout.addLayout(form_layout)

        if channel:
            self.name_input.setText(channel.name)
            self.url_input.setText(channel.url)
            self.group_input.setText(channel.group)
            self.logo_input.setText(channel.logo)
            self.tvgid_input.setText(channel.tvgId)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_data(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "url": self.url_input.text().strip(),
            "group": self.group_input.text().strip(),
            "logo": self.logo_input.text().strip(),
            "tvgId": self.tvgid_input.text().strip()
        }
        
    def accept(self):
        if not self.get_data()['name'] or not self.get_data()['url'] or not self.get_data()['group']:
            QMessageBox.warning(self, "Campos Obrigatórios", "Os campos Nome, URL e Grupo são obrigatórios.")
            return
        super().accept()

class ChannelItemWidget(QWidget):
    def __init__(self, channel: Channel, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.threadpool = QThreadPool.globalInstance()
        self.setFixedSize(220, 280)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setObjectName("container")
        container.setStyleSheet("#container { background-color: #374151; border-radius: 8px; }")
        container_layout = QVBoxLayout(container)
        
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(200, 140)
        self.logo_label.setStyleSheet("background-color: #1f2937; border-radius: 6px;")
        
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.addWidget(self.logo_label)
        container_layout.addWidget(logo_container)
        
        self.placeholder_pixmap = self.create_placeholder_pixmap("TV")
        self.logo_label.setPixmap(self.placeholder_pixmap)
        
        if channel.logo:
            self.download_logo(channel.logo)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(2)
        
        self.group_label = QLabel(channel.group.upper())
        self.group_label.setStyleSheet("color: #9ca3af; font-size: 10px; font-weight: bold;")
        
        self.name_label = QLabel(channel.name)
        self.name_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.name_label.setWordWrap(True)
        
        info_layout.addWidget(self.group_label)
        info_layout.addWidget(self.name_label)
        info_layout.addStretch()
        container_layout.addWidget(info_widget)

        self.edit_button = QPushButton("Editar")
        self.delete_button = QPushButton("Excluir")
        self.delete_button.setObjectName("secondary")

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.edit_button)
        btn_layout.addWidget(self.delete_button)
        container_layout.addLayout(btn_layout)
        
        main_layout.addWidget(container)
    
    def create_placeholder_pixmap(self, text):
        pixmap = QPixmap(200, 140)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(Qt.gray)
        painter.setFont(self.font())
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        return pixmap

    def download_logo(self, url):
        downloader = ImageDownloader(url)
        downloader.signals.finished.connect(self.set_logo_from_data)
        downloader.signals.error.connect(self.on_logo_error)
        self.threadpool.start(downloader)

    def set_logo_from_data(self, data):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled_pixmap = pixmap.scaled(self.logo_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)

    def on_logo_error(self):
        pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPTV M3U8 Manager")
        self.setGeometry(100, 100, 1024, 768)

        self.channels = load_channels()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        title_label = QLabel("IPTV M3U8 Manager")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        self.add_btn = QPushButton("Adicionar Canal")
        self.import_btn = QPushButton("Importar .m3u8")
        self.save_btn = QPushButton("Salvar Lista .m3u8")
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.import_btn)
        header_layout.addWidget(self.add_btn)
        header_layout.addWidget(self.save_btn)
        main_layout.addLayout(header_layout)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListView.IconMode)
        self.list_widget.setResizeMode(QListView.Adjust)
        self.list_widget.setMovement(QListView.Static)
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setSpacing(15)
        self.list_widget.model().rowsMoved.connect(self.on_rows_moved)
        main_layout.addWidget(self.list_widget)

        self.add_btn.clicked.connect(self.add_channel)
        self.import_btn.clicked.connect(self.import_m3u8)
        self.save_btn.clicked.connect(self.save_m3u8_local)

        self.populate_channel_list()

    def populate_channel_list(self):
        self.list_widget.clear()
        if not self.channels:
            empty_label = QLabel("Sua lista de canais está vazia.\nAdicione um canal ou importe um arquivo .m3u8.")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: #9ca3af; font-size: 16px;")
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(self.list_widget.viewport().size())
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, empty_label)
            return
            
        for channel in self.channels:
            item_widget = ChannelItemWidget(channel)
            
            # --- CORREÇÃO 1: Botões de Editar/Excluir ---
            # A lambda agora aceita o argumento `checked` do sinal e o ignora,
            # usando `channel.id` que é capturado corretamente do loop.
            item_widget.edit_button.clicked.connect(
                lambda checked, ch_id=channel.id: self.edit_channel(ch_id)
            )
            item_widget.delete_button.clicked.connect(
                lambda checked, ch_id=channel.id: self.delete_channel(ch_id)
            )
            
            list_item = QListWidgetItem(self.list_widget)
            # --- CORREÇÃO 2: Habilitar Drag and Drop para cada item ---
            list_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, channel.id)
            
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)

    def find_channel_by_id(self, channel_id):
        return next((ch for ch in self.channels if ch.id == channel_id), None)
        
    def find_item_by_id(self, channel_id):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == channel_id:
                return item
        return None

    def add_channel(self):
        dialog = ChannelForm(self)
        if dialog.exec():
            data = dialog.get_data()
            new_channel = Channel(id=str(uuid.uuid4()), **data)
            self.channels.append(new_channel)
            self.save_and_refresh()

    def edit_channel(self, channel_id: str):
        channel_to_edit = self.find_channel_by_id(channel_id)
        if not channel_to_edit: return
        
        dialog = ChannelForm(self, channel_to_edit)
        if dialog.exec():
            updated_data = dialog.get_data()
            channel_to_edit.name = updated_data['name']
            channel_to_edit.url = updated_data['url']
            channel_to_edit.group = updated_data['group']
            channel_to_edit.logo = updated_data['logo']
            channel_to_edit.tvgId = updated_data['tvgId']
            self.save_and_refresh()

    def delete_channel(self, channel_id: str):
        channel_to_delete = self.find_channel_by_id(channel_id)
        if not channel_to_delete: return

        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Você tem certeza que deseja excluir o canal '{channel_to_delete.name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.channels = [ch for ch in self.channels if ch.id != channel_id]
            self.save_and_refresh()

    def import_m3u8(self):
        if self.channels:
            reply = QMessageBox.question(
                self, "Importar Lista",
                "Isso substituirá sua lista de canais atual. Deseja continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No: return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Importar Playlist M3U8", "", "M3U8 Files (*.m3u8 *.m3u)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                parsed_list = parse_m3u8_content(content)
                self.channels = [Channel(id=str(uuid.uuid4()), **ch_data) for ch_data in parsed_list]
                self.save_and_refresh()
                QMessageBox.information(self, "Sucesso", f"{len(self.channels)} canais importados com sucesso.")
            except Exception as e:
                QMessageBox.critical(self, "Erro de Importação", f"Não foi possível importar o arquivo:\n{e}")

    def save_m3u8_local(self):
        if not self.channels:
            QMessageBox.warning(self, "Lista Vazia", "Adicione pelo menos um canal antes de salvar.")
            return

        file_name, ok = QInputDialog.getText(self, "Salvar Playlist",
                                             "Digite o nome do arquivo (será salvo como .m3u8):",
                                             QLineEdit.Normal, "playlist")
        
        if ok and file_name:
            if not file_name.strip():
                QMessageBox.warning(self, "Nome Inválido", "O nome do arquivo não pode ser vazio.")
                return
            if not file_name.endswith('.m3u8'):
                file_name += '.m3u8'

            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                file_path = os.path.join(script_dir, file_name)
                content = generate_m3u8_content(self.channels)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                QMessageBox.information(self, "Sucesso", f"Playlist salva com sucesso em:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Erro ao Salvar", f"Não foi possível salvar o arquivo:\n{e}")

    # --- CORREÇÃO 3: Lógica de reordenação simplificada e corrigida ---
    def on_rows_moved(self, parent, start, end, destination, row):
        # A linha `end` não é necessária pois só movemos um item de cada vez.
        # `row` é o índice de destino para onde o item foi movido.
        moved_item = self.channels.pop(start)
        self.channels.insert(row, moved_item)
        save_channels(self.channels)

    def save_and_refresh(self):
        save_channels(self.channels)
        self.populate_channel_list()

# --- Ponto de Entrada da Aplicação ---

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())