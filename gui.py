import sys
import os
import re
import time
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QTextCursor, QPixmap, QImage, QPainter, QBrush, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTextEdit,
    QTextBrowser, QVBoxLayout, QWidget, QFileDialog, QGraphicsDropShadowEffect,
    QFormLayout, QGroupBox, QSpacerItem, QGridLayout, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu
)

from ai_engine import AIEngine
from config import load_config, save_config
from executor import run_bash, run_gui_action
from guardrails import set_allowed_target_scopes, get_allowed_target_scopes
from sessions import load_all_sessions, save_all_sessions, delete_session_by_id

# ── Sleek Modern Palette ────────────────────────────────────────────────────────
BG_DARK = "#090d14"      # Main Canvas
BG_SIDEBAR = "#101622"   # Left Navigation Sidebar
BG_TERMINAL = "#070a10"  # Dedicated Terminal Output Panel
BG_CARD = "#161e2c"      # Assistant Response Cards
BG_USER = "#1b2738"      # User Message Bubbles
BG_INPUT = "#131b28"     # Compact Floating Input Bar
BORDER_COLOR = "#232d3f" # Subtle Borders
ACCENT_BLUE = "#3b82f6"  # Primary Action Blue
ACCENT_GREEN = "#10b981" # Emerald Success
ACCENT_RED = "#ef4444"   # Red Danger
ACCENT_AMBER = "#f59e0b" # Warning Gold
TEXT_PRIMARY = "#f8fafc" # Bright Primary Text
TEXT_MUTED = "#8b949e"   # Secondary Muted Text

STYLE = f"""
QMainWindow {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: 'Inter', 'Segoe UI', sans-serif;
}}
QWidget {{
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: #232d3f;
    min-height: 24px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3b4968;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QPushButton {{
    border-radius: 7px;
    padding: 5px 11px;
    font-weight: 600;
    background-color: #172030;
    border: 1px solid {BORDER_COLOR};
    color: {TEXT_PRIMARY};
}}
QPushButton:hover {{
    background-color: #232f45;
    border-color: #3b82f6;
}}
QPushButton:pressed {{
    background-color: #101724;
}}
QLineEdit, QComboBox {{
    background-color: #0d131f;
    border: 1px solid {BORDER_COLOR};
    border-radius: 7px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT_BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QSplitter::handle {{
    background-color: {BORDER_COLOR};
    width: 2px;
}}
"""

def apply_shadow(widget: QWidget, blur=16, offset_y=4, alpha=120):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(0, 0, 0, alpha))
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)


CURRENT_FONT_SIZE = 13

def _format_message_html(text: str, font_size: Optional[int] = None) -> str:
    if font_size is None:
        font_size = CURRENT_FONT_SIZE
    code_size = max(10, font_size - 1)
    
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    def code_block_replacer(match):
        lang = match.group(1) or "bash"
        code = match.group(2).strip()
        return f'''
        <div style="background-color: #070a10; border: 1px solid #1f2937; border-radius: 8px; margin: 8px 0; overflow: hidden;">
            <div style="background-color: #0f172a; padding: 4px 10px; font-family: Consolas, monospace; font-size: {code_size - 1}px; color: #64748b; border-bottom: 1px solid #1f2937;">
                ⚡ {lang}
            </div>
            <pre style="padding: 10px; margin: 0; font-family: Consolas, monospace; font-size: {code_size}px; color: #e2e8f0; line-height: 1.4;"><code>{code}</code></pre>
        </div>
        '''
    text = re.sub(r'```([\w\+\-\.]*)?\n(.*?)```', code_block_replacer, text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', f'<code style="background-color: #1e293b; padding: 2px 5px; border-radius: 4px; font-family: Consolas, monospace; color: #60a5fa; font-size: {code_size}px;">\\1</code>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #f8fafc;">\1</strong>', text)
    text = re.sub(r'\[IMG:(.*?)\]', r'<br><img src="file:///\1" style="max-width: 380px; border-radius: 8px; margin: 6px 0;"><br>', text)
    
    parts = text.split('<div style="background-color: #070a10;')
    for i in range(len(parts)):
        if i == 0:
            parts[i] = parts[i].replace('\n', '<br>')
        else:
            subparts = parts[i].split('</div>', 1)
            if len(subparts) == 2:
                subparts[1] = subparts[1].replace('\n', '<br>')
                parts[i] = '</div>'.join(subparts)
    text = '<div style="background-color: #070a10;'.join(parts)
    return f'<div style="font-size: {font_size}px; line-height: 1.5; color: #f8fafc;">{text}</div>'


# ── Background Workers ──────────────────────────────────────────────────────────
class AIWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, engine: AIEngine, user_text: str, attach_screenshot: bool = True, terminal_output: Optional[str] = None, image_paths: Optional[list[str]] = None):
        super().__init__()
        self.engine = engine
        self.user_text = user_text
        self.attach_screenshot = attach_screenshot
        self.terminal_output = terminal_output
        self.image_paths = image_paths

    def run(self):
        try:
            res = self.engine.send(
                user_text=self.user_text,
                attach_screenshot=self.attach_screenshot,
                terminal_output=self.terminal_output,
                image_paths=self.image_paths
            )
            self.result_ready.emit(res)
        except Exception as e:
            self.error_occurred.emit(str(e))


class ModelFetchWorker(QThread):
    models_ready = pyqtSignal(list)
    fetch_failed = pyqtSignal(str)

    def __init__(self, engine: AIEngine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            models = self.engine.get_available_models()
            self.models_ready.emit(models)
        except Exception as e:
            self.fetch_failed.emit(str(e))


# ── Live Execution Plan Tracker Widget ──────────────────────────────────────────
class PlanTrackerWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: #0c121e; border-bottom: 1px solid {BORDER_COLOR}; padding: 4px 8px; }}")
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 4, 10, 4)
        self.layout.setSpacing(8)
        
        title_lbl = QLabel("🎯 PLAN:")
        title_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {ACCENT_AMBER};")
        self.layout.addWidget(title_lbl)
        
        self.pills_layout = QHBoxLayout()
        self.pills_layout.setSpacing(6)
        self.layout.addLayout(self.pills_layout)
        self.layout.addStretch()
        
        self.hide()

    def update_plan(self, plan_steps: list):
        if not plan_steps:
            self.hide()
            return
            
        while self.pills_layout.count():
            item = self.pills_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
                
        for item in plan_steps:
            step_num = item.get("step", 1)
            title = item.get("title", f"Step {step_num}")
            status = item.get("status", "pending").lower()
            
            pill = QLabel()
            if status in ["completed", "done"]:
                pill.setText(f"✔ {step_num}. {title}")
                pill.setStyleSheet(f"background: rgba(16, 185, 129, 0.15); border: 1px solid {ACCENT_GREEN}; color: {ACCENT_GREEN}; border-radius: 10px; padding: 2px 8px; font-size: 10px; font-weight: 600;")
            elif status in ["in_progress", "active", "running"]:
                pill.setText(f"⚡ {step_num}. {title}")
                pill.setStyleSheet(f"background: rgba(59, 130, 246, 0.2); border: 1px solid {ACCENT_BLUE}; color: #60a5fa; border-radius: 10px; padding: 2px 8px; font-size: 10px; font-weight: 600;")
            else:
                pill.setText(f"⏳ {step_num}. {title}")
                pill.setStyleSheet(f"background: #131b28; border: 1px solid #232d3f; color: {TEXT_MUTED}; border-radius: 10px; padding: 2px 8px; font-size: 10px;")
                
            self.pills_layout.addWidget(pill)
            
        self.show()


# ── Feature 1: Target Scope & Rules of Engagement Guard Dialog ───────────────
class TargetScopeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Target Scope & Safety Guard")
        self.setFixedSize(480, 360)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel("🎯 Target Scope Guardrails")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title)
        
        sub = QLabel("Specify authorized IP addresses, IP ranges (CIDR), or domain names.\nAny command targeting IPs outside this list will be strictly blocked.")
        sub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        
        self.scope_edit = QPlainTextEdit()
        self.scope_edit.setPlaceholderText("e.g.\n192.168.1.0/24\n10.0.0.5\nexample.com")
        self.scope_edit.setStyleSheet(f"background-color: #0d131f; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 8px; font-family: Consolas, monospace; color: {ACCENT_GREEN};")
        
        current_scopes = get_allowed_target_scopes()
        if current_scopes:
            self.scope_edit.setPlainText("\n".join(current_scopes))
            
        layout.addWidget(self.scope_edit)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        
        clear_btn = QPushButton("Clear Scope")
        clear_btn.clicked.connect(self._clear_scope)
        btn_box.addWidget(clear_btn)
        
        save_btn = QPushButton("Save & Activate Scope")
        save_btn.setStyleSheet(f"background: {ACCENT_BLUE}; color: white; font-weight: bold;")
        save_btn.clicked.connect(self._save_scope)
        btn_box.addWidget(save_btn)
        
        layout.addLayout(btn_box)

    def _clear_scope(self):
        set_allowed_target_scopes([])
        self.accept()

    def _save_scope(self):
        raw = self.scope_edit.toPlainText().strip()
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        set_allowed_target_scopes(lines)
        self.accept()


# ── Feature 4: Interactive Target & Asset Inventory Dashboard ──────────────
class TargetInventoryWidget(QFrame):
    run_action_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: {BG_DARK}; border: none; }}")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        header = QHBoxLayout()
        title_lbl = QLabel("📊 Target & Asset Intelligence Inventory")
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY};")
        
        sub_lbl = QLabel("Discovered targets, open ports, services & security risks")
        sub_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        
        header_v = QVBoxLayout()
        header_v.addWidget(title_lbl)
        header_v.addWidget(sub_lbl)
        
        header.addLayout(header_v)
        header.addStretch()
        
        self.btn_refresh = QPushButton("🔄 Refresh Discovery")
        self.btn_refresh.setStyleSheet(f"background: #172030; color: {ACCENT_BLUE};")
        self.btn_refresh.clicked.connect(self.populate_demo_inventory)
        header.addWidget(self.btn_refresh)
        
        layout.addLayout(header)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Target Host IP", "Discovered Ports", "Detected Services", "OS / Banner", "Risk Level", "Quick Action"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: #0c121e;
                border: 1px solid {BORDER_COLOR};
                gridline-color: #1e293b;
                border-radius: 8px;
                color: #f8fafc;
            }}
            QHeaderView::section {{
                background-color: #101622;
                color: #94a3b8;
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #1e293b;
                padding: 6px;
            }}
        """)
        
        layout.addWidget(self.table)
        self.populate_demo_inventory()

    def populate_demo_inventory(self):
        self.table.setRowCount(0)
        targets = [
            ("192.168.1.1", "80/HTTP, 443/HTTPS, 22/SSH", "Apache 2.4.41, OpenSSH 8.2p1", "Linux 5.4 (Ubuntu)", "🟡 Medium", "Nmap Deep Audit"),
            ("192.168.1.105", "21/FTP, 22/SSH, 80/HTTP", "vsftpd 2.3.4, Apache 2.2.22", "Linux (Metasploitable)", "🔴 High (Exploitable)", "Quick Vuln Check"),
            ("192.168.1.200", "445/SMB, 139/NetBIOS", "Samba 3.x", "Windows Server / Samba", "🟢 Low", "SMB Enum")
        ]
        
        for idx, (ip, ports, svcs, os_info, risk, act_name) in enumerate(targets):
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(ip))
            self.table.setItem(idx, 1, QTableWidgetItem(ports))
            self.table.setItem(idx, 2, QTableWidgetItem(svcs))
            self.table.setItem(idx, 3, QTableWidgetItem(os_info))
            
            risk_item = QTableWidgetItem(risk)
            if "High" in risk:
                risk_item.setForeground(QColor(ACCENT_RED))
            elif "Medium" in risk:
                risk_item.setForeground(QColor(ACCENT_AMBER))
            else:
                risk_item.setForeground(QColor(ACCENT_GREEN))
                
            self.table.setItem(idx, 4, risk_item)
            
            btn_act = QPushButton(f"⚡ {act_name}")
            btn_act.setStyleSheet("font-size: 10px; padding: 3px 6px; background: #1a273d; color: #60a5fa;")
            btn_act.clicked.connect(lambda checked=False, target=ip, act=act_name: self.run_action_requested.emit(f"Run {act} on target {target}"))
            
            self.table.setCellWidget(idx, 5, btn_act)


# ── Settings Dialog ─────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ API Configuration")
        self.setFixedSize(500, 460)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")
        
        self.config = load_config()
        self.engine: Optional[AIEngine] = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        title_label = QLabel("API & Model Settings")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title_label)
        
        provider_layout = QHBoxLayout()
        provider_layout.addWidget(QLabel("AI Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "gemini"])
        self.provider_combo.setCurrentText(self.config.get("provider", "gemini"))
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addWidget(self.provider_combo)
        layout.addLayout(provider_layout)
        
        self.openai_group = QGroupBox("OpenAI / Custom Base API")
        self.openai_group.setStyleSheet(f"QGroupBox {{ border: 1px solid {BORDER_COLOR}; border-radius: 8px; margin-top: 8px; font-weight: bold; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}")
        openai_layout = QFormLayout(self.openai_group)
        openai_layout.setContentsMargins(10, 14, 10, 10)
        
        self.openai_url = QLineEdit(self.config.get("openai_base_url", "https://openrouter.ai/api/v1"))
        self.openai_key = QLineEdit(self.config.get("openai_api_key", ""))
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_model = QComboBox()
        self.openai_model.setEditable(True)
        self.openai_model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.openai_model.view().setMinimumWidth(340)
        self.openai_model.setCurrentText(self.config.get("openai_model", "openai/gpt-4o"))
        
        openai_layout.addRow("Base URL:", self.openai_url)
        openai_layout.addRow("API Key:", self.openai_key)
        openai_layout.addRow("Model:", self.openai_model)
        layout.addWidget(self.openai_group)
        
        self.gemini_group = QGroupBox("Google Gemini Settings")
        self.gemini_group.setStyleSheet(f"QGroupBox {{ border: 1px solid {BORDER_COLOR}; border-radius: 8px; margin-top: 8px; font-weight: bold; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}")
        gemini_layout = QFormLayout(self.gemini_group)
        gemini_layout.setContentsMargins(10, 14, 10, 10)
        
        self.gemini_key = QLineEdit(self.config.get("gemini_api_key", ""))
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_model = QComboBox()
        self.gemini_model.setEditable(True)
        self.gemini_model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.gemini_model.view().setMinimumWidth(340)
        self.gemini_model.setCurrentText(self.config.get("gemini_model", "gemini-2.0-flash"))
        
        gemini_layout.addRow("API Key:", self.gemini_key)
        gemini_layout.addRow("Model:", self.gemini_model)
        layout.addWidget(self.gemini_group)
        
        self._on_provider_changed(self.provider_combo.currentText())
        
        self.fetch_timer = QTimer(self)
        self.fetch_timer.setSingleShot(True)
        self.fetch_timer.setInterval(800)
        self.fetch_timer.timeout.connect(self._auto_fetch_models)
        
        self.openai_key.textChanged.connect(lambda: self.fetch_timer.start())
        self.openai_url.textChanged.connect(lambda: self.fetch_timer.start())
        self.gemini_key.textChanged.connect(lambda: self.fetch_timer.start())
        
        if self.openai_key.text().strip() or self.gemini_key.text().strip():
            QTimer.singleShot(300, self._auto_fetch_models)
        
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("⚡ Test Connection")
        self.test_btn.clicked.connect(self._test_and_fetch)
        self.test_btn.setStyleSheet(f"background: #172030; color: {ACCENT_BLUE}; border-color: #2b3952;")
        
        self.save_btn = QPushButton("Save Config")
        self.save_btn.setStyleSheet(f"background: {ACCENT_BLUE}; color: white; border: none; font-weight: bold;")
        self.save_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)

    def _on_provider_changed(self, provider: str):
        self.openai_group.setVisible(provider == "openai")
        self.gemini_group.setVisible(provider == "gemini")
        
    def _auto_fetch_models(self):
        provider = self.provider_combo.currentText()
        key = self.openai_key.text().strip() if provider == "openai" else self.gemini_key.text().strip()
        if not key:
            return
            
        self.status_label.setText("🔍 Auto-detecting models...")
        self.status_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        
        try:
            self.engine = AIEngine(
                provider=provider,
                openai_key=self.openai_key.text().strip(),
                openai_url=self.openai_url.text().strip(),
                openai_model=self.openai_model.currentText().strip(),
                gemini_key=self.gemini_key.text().strip(),
                gemini_model=self.gemini_model.currentText().strip()
            )
            self.worker = ModelFetchWorker(self.engine)
            self.worker.models_ready.connect(self._on_models_fetched)
            self.worker.fetch_failed.connect(self._on_models_failed)
            self.worker.start()
        except Exception:
            pass

    def _test_and_fetch(self):
        self.status_label.setText("🔍 Auto-detecting models & testing connection...")
        self.status_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        self.test_btn.setEnabled(False)
        
        provider = self.provider_combo.currentText()
        try:
            self.engine = AIEngine(
                provider=provider,
                openai_key=self.openai_key.text().strip(),
                openai_url=self.openai_url.text().strip(),
                openai_model=self.openai_model.currentText().strip(),
                gemini_key=self.gemini_key.text().strip(),
                gemini_model=self.gemini_model.currentText().strip()
            )
            self.worker = ModelFetchWorker(self.engine)
            self.worker.models_ready.connect(self._on_models_fetched)
            self.worker.fetch_failed.connect(self._on_models_failed)
            self.worker.start()
        except Exception as e:
            self._on_models_failed(str(e))

    def _on_models_fetched(self, models: list):
        self.test_btn.setEnabled(True)
        provider = self.provider_combo.currentText()
        combo = self.openai_model if provider == "openai" else self.gemini_model
        
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        if models:
            combo.addItems(models)
            if current in models:
                combo.setCurrentText(current)
            else:
                combo.setCurrentIndex(0)
        combo.blockSignals(False)

        # Test connection with selected model
        if self.engine:
            if provider == "openai":
                self.engine.openai_model = combo.currentText().strip()
            else:
                self.engine.gemini_model = combo.currentText().strip()
            success, msg = self.engine.test_connection()
            if success:
                self.status_label.setText(f"✅ Connection verified! {len(models)} models auto-detected.")
                self.status_label.setStyleSheet(f"color: {ACCENT_GREEN};")
            else:
                self.status_label.setText(f"⚠️ {len(models)} models detected, but test failed: {msg[:100]}")
                self.status_label.setStyleSheet(f"color: {ACCENT_AMBER};")
        else:
            self.status_label.setText(f"✅ Auto-detected {len(models)} models.")
            self.status_label.setStyleSheet(f"color: {ACCENT_GREEN};")
            
    def _on_models_failed(self, error: str):
        self.test_btn.setEnabled(True)
        self.status_label.setText(f"❌ {error}")
        self.status_label.setStyleSheet(f"color: {ACCENT_RED};")

    def accept(self):
        self.config["provider"] = self.provider_combo.currentText()
        self.config["openai_base_url"] = self.openai_url.text().strip()
        self.config["openai_api_key"] = self.openai_key.text().strip()
        self.config["openai_model"] = self.openai_model.currentText().strip()
        self.config["gemini_api_key"] = self.gemini_key.text().strip()
        self.config["gemini_model"] = self.gemini_model.currentText().strip()
        save_config(self.config)
        super().accept()


# ── Plugins & MCP Manager Dialog ───────────────────────────────────────────────
class PluginManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔌 Plugins & MCP Server Extensions")
        self.setFixedSize(540, 480)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")
        
        from plugins import load_installed_plugins, import_plugin_file, PLUGIN_DIR
        self.load_installed_plugins = load_installed_plugins
        self.import_plugin_file = import_plugin_file
        self.PLUGIN_DIR = PLUGIN_DIR
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel("🔌 Custom Plugins & MCP Extensions")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title)
        
        sub = QLabel("Add custom Python scripts or MCP tools to extend Kali-AI's capabilities.")
        sub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        layout.addWidget(sub)
        
        self.plugin_list = QPlainTextEdit()
        self.plugin_list.setReadOnly(True)
        self.plugin_list.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0d131f;
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 10px;
                font-family: Consolas, monospace;
                font-size: 11px;
                color: #60a5fa;
            }}
        """)
        layout.addWidget(self.plugin_list)
        
        btn_box = QHBoxLayout()
        
        self.btn_add_plugin = QPushButton("＋ Add Custom Plugin (.py)")
        self.btn_add_plugin.setStyleSheet(f"background: {ACCENT_BLUE}; color: white; font-weight: bold;")
        self.btn_add_plugin.clicked.connect(self._add_plugin)
        
        self.btn_open_dir = QPushButton("📂 Open Plugins Folder")
        self.btn_open_dir.clicked.connect(self._open_folder)
        
        btn_box.addWidget(self.btn_add_plugin)
        btn_box.addWidget(self.btn_open_dir)
        btn_box.addStretch()
        
        layout.addLayout(btn_box)
        
        mcp_card = QFrame()
        mcp_card.setStyleSheet(f"background: #0d1522; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 8px;")
        mc_layout = QVBoxLayout(mcp_card)
        mcp_lbl = QLabel("⚡ MCP (Model Context Protocol) Support")
        mcp_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {ACCENT_GREEN};")
        mcp_sub = QLabel(f"Place any MCP server executable or Python plugin script inside:\n{PLUGIN_DIR}\nKali-AI will automatically load its tools into prompt memory.")
        mcp_sub.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        mc_layout.addWidget(mcp_lbl)
        mc_layout.addWidget(mcp_sub)
        layout.addWidget(mcp_card)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self._refresh_list()

    def _refresh_list(self):
        plugins = self.load_installed_plugins()
        self.plugin_list.clear()
        self.plugin_list.appendPlainText(f"=== INSTALLED PLUGINS ({len(plugins)}) ===\n")
        if not plugins:
            self.plugin_list.appendPlainText("(No custom plugins installed. Click 'Add Custom Plugin' to install one.)")
        else:
            for name, info in plugins.items():
                kw = info.get("command_keyword", name)
                desc = info.get("description", "No description")
                fpath = info.get("filepath", "")
                self.plugin_list.appendPlainText(f"• {name} [Keyword: {kw}]\n  Desc: {desc}\n  File: {fpath}\n")

    def _add_plugin(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Plugin Script", "", "Python Files (*.py)")
        if path:
            ok, msg = self.import_plugin_file(path)
            if ok:
                QMessageBox.information(self, "Plugin Installed", msg)
                self._refresh_list()
            else:
                QMessageBox.warning(self, "Import Failed", msg)

    def _open_folder(self):
        import subprocess
        if not os.path.exists(self.PLUGIN_DIR):
            os.makedirs(self.PLUGIN_DIR, exist_ok=True)
            
        if sys.platform == "win32":
            os.startfile(self.PLUGIN_DIR)
        else:
            subprocess.run(["xdg-open", self.PLUGIN_DIR])


# ── Chat History Item Button with Right-Click Context Menu ─────────────────────
class SessionHistoryButton(QPushButton):
    delete_requested = pyqtSignal(int)

    def __init__(self, session_id: int, title: str, parent=None):
        super().__init__(title, parent)
        self.session_id = session_id
        self.setStyleSheet("""
            QPushButton {
                background: #0d131f;
                font-size: 11px;
                text-align: left;
                padding: 6px;
                border-radius: 6px;
                border: 1px solid #1e293b;
                color: #cbd5e1;
            }
            QPushButton:hover {
                background: #162032;
                border-color: #3b82f6;
                color: #f8fafc;
            }
        """)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #101622;
                color: #f8fafc;
                border: 1px solid #232d3f;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #ef4444;
                color: white;
                border-radius: 4px;
            }
        """)
        del_action = menu.addAction("🗑 Delete Session")
        action = menu.exec(event.globalPos())
        if action == del_action:
            self.delete_requested.emit(self.session_id)


# ── Conversational Chat Bubble Widget ──────────────────────────────────────────
class ChatBubble(QFrame):
    option_selected = pyqtSignal(str)

    def __init__(self, role: str, text: str, confidence_score: Optional[int] = None, impact_risk: Optional[str] = None, options: Optional[list] = None, parent=None):
        super().__init__(parent)
        self.role = role
        self.raw_text = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        
        main_h_layout = QHBoxLayout(self)
        main_h_layout.setContentsMargins(6, 4, 6, 4)
        
        bubble_box = QFrame()
        box_layout = QVBoxLayout(bubble_box)
        box_layout.setContentsMargins(12, 8, 12, 8)
        box_layout.setSpacing(4)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        role_label = QLabel()
        role_label.setFont(QFont("Inter", 10, QFont.Weight.Bold))
        
        if role == "user":
            role_label.setText("👤 You")
            role_label.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold;")
            bubble_box.setStyleSheet(f"QFrame {{ background-color: {BG_USER}; border: 1px solid #28374d; border-radius: 12px; }}")
            bubble_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            main_h_layout.addStretch(1)
            main_h_layout.addWidget(bubble_box, 3)
        elif role == "assistant":
            role_label.setText("🐉 Kali-AI Agent")
            role_label.setStyleSheet(f"color: {ACCENT_GREEN}; font-weight: bold;")
            bubble_box.setStyleSheet("QFrame { background: transparent; border: none; padding: 0; }")
            bubble_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            main_h_layout.addWidget(bubble_box, 1)
        else: # system
            role_label.setText("⚡ Execution Notice")
            role_label.setStyleSheet(f"color: {ACCENT_AMBER}; font-weight: bold;")
            bubble_box.setStyleSheet("QFrame { background: transparent; border: none; padding: 0; }")
            bubble_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            main_h_layout.addWidget(bubble_box, 1)
            
        header_layout.addWidget(role_label)
        
        if role == "assistant" and confidence_score is not None:
            conf_badge = QLabel(f"🎯 {confidence_score}%")
            conf_badge.setStyleSheet("background: #0d1522; border: 1px solid #1e2d45; color: #60a5fa; border-radius: 8px; padding: 1px 6px; font-size: 10px; font-weight: 600;")
            header_layout.addWidget(conf_badge)
            
            risk_color = ACCENT_GREEN if impact_risk == "Low" else (ACCENT_AMBER if impact_risk == "Medium" else ACCENT_RED)
            risk_badge = QLabel(f"🛡️ Risk: {impact_risk or 'Low'}")
            risk_badge.setStyleSheet(f"background: #0d1522; border: 1px solid #1e2d45; color: {risk_color}; border-radius: 8px; padding: 1px 6px; font-size: 10px; font-weight: 600;")
            header_layout.addWidget(risk_badge)

        header_layout.addStretch()
        box_layout.addLayout(header_layout)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.text_browser.setStyleSheet("background: transparent; border: none; color: #f8fafc; selection-background-color: #3b82f6; selection-color: white;")
        
        html = _format_message_html(text)
        self.text_browser.setHtml(html)
        
        self.text_browser.document().adjustSize()
        doc_height = int(self.text_browser.document().size().height())
        self.text_browser.setFixedHeight(max(30, doc_height + 12))
        
        box_layout.addWidget(self.text_browser)
        
        # Interactive Decision Option Buttons (if AI provided options)
        if options and isinstance(options, list):
            options_box = QFrame()
            options_box.setStyleSheet(f"background: #0c1320; border: 1px solid {BORDER_COLOR}; border-radius: 8px; margin-top: 6px; padding: 6px;")
            opt_layout = QVBoxLayout(options_box)
            opt_layout.setContentsMargins(6, 6, 6, 6)
            opt_layout.setSpacing(6)
            
            opt_title = QLabel("👉 Select an Option to proceed:")
            opt_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {ACCENT_AMBER};")
            opt_layout.addWidget(opt_title)
            
            for opt_text in options:
                btn_opt = QPushButton(f"⚡ {opt_text}")
                btn_opt.setStyleSheet(f"background: #172236; color: #60a5fa; border: 1px solid #283a59; border-radius: 6px; padding: 6px 10px; font-size: 11px; text-align: left; font-weight: 600;")
                btn_opt.clicked.connect(lambda checked=False, t=opt_text: self.option_selected.emit(t))
                opt_layout.addWidget(btn_opt)
                
            box_layout.addWidget(options_box)

    def update_font_size(self, font_size: int):
        html = _format_message_html(self.raw_text, font_size=font_size)
        self.text_browser.setHtml(html)
        self.text_browser.document().adjustSize()
        doc_height = int(self.text_browser.document().size().height())
        self.text_browser.setFixedHeight(max(30, doc_height + 12))


# ── Command Intercept Banner ───────────────────────────────────────────────────
class InterceptBanner(QFrame):
    approved = pyqtSignal(str)
    cancelled = pyqtSignal()
    
    def __init__(self, command: str, parent=None):
        super().__init__(parent)
        self.command = command
        self.setStyleSheet(f"QFrame {{ background: rgba(245, 158, 11, 0.08); border: 1px solid {ACCENT_AMBER}; border-radius: 10px; }}")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        
        title = QLabel("⚠️ Security Guardrail: Human Approval Required")
        title.setStyleSheet(f"color: {ACCENT_AMBER}; font-size: 12px; font-weight: bold;")
        layout.addWidget(title)
        
        cmd_browser = QTextBrowser()
        cmd_browser.setStyleSheet(f"background: #090d14; border: 1px solid #232d3f; border-radius: 6px; padding: 6px; font-family: Consolas, monospace; color: #60a5fa; font-size: 12px;")
        cmd_browser.setPlainText(command)
        cmd_browser.setMaximumHeight(60)
        layout.addWidget(cmd_browser)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("✖ Reject")
        cancel_btn.setStyleSheet(f"background: #261616; color: {ACCENT_RED}; border-color: #4d2222; font-size: 11px;")
        cancel_btn.clicked.connect(self.cancelled.emit)
        btn_layout.addWidget(cancel_btn)
        
        approve_btn = QPushButton("✔ Approve & Run")
        approve_btn.setStyleSheet(f"background: {ACCENT_AMBER}; color: black; font-weight: bold; font-size: 11px;")
        approve_btn.clicked.connect(lambda: self.approved.emit(self.command))
        btn_layout.addWidget(approve_btn)
        
        layout.addLayout(btn_layout)
        apply_shadow(self, blur=15, offset_y=4, alpha=100)


# ── Animated Loading Widget ─────────────────────────────────────────────────────
class LoadingWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.label = QLabel("🐉 Kali-AI is reasoning & planning")
        self.label.setStyleSheet(f"color: {ACCENT_GREEN}; font-weight: 600; font-size: 12px;")
        
        self.dots_label = QLabel("")
        self.dots_label.setStyleSheet(f"color: {ACCENT_GREEN}; font-weight: bold; font-size: 14px;")
        
        layout.addWidget(self.label)
        layout.addWidget(self.dots_label)
        layout.addStretch()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.dots = 0
        
    def start(self):
        self.dots = 0
        self.timer.start(350)
        self.show()
        
    def stop(self):
        self.timer.stop()
        self.hide()
        
    def _animate(self):
        self.dots = (self.dots + 1) % 4
        self.dots_label.setText("." * self.dots)


# ── Circular Spinning Activity Indicator ────────────────────────────────────────
class CircularSpinnerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.hide()

    def start(self):
        self.angle = 0
        self.timer.start(30)
        self.show()

    def stop(self):
        self.timer.stop()
        self.hide()

    def _rotate(self):
        self.angle = (self.angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect().adjusted(2, 2, -2, -2)
        
        # Track Background
        pen_bg = QPen(QColor("#1e293b"), 3)
        painter.setPen(pen_bg)
        painter.drawEllipse(rect)
        
        # Spinning Neon Arc
        pen_arc = QPen(QColor("#10b981"), 3)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        
        start_angle = int(-self.angle * 16)
        span_angle = int(100 * 16)
        painter.drawArc(rect, start_angle, span_angle)


# ── Dynamic Auto-Expanding Input Edit ──────────────────────────────────────────
class CompactInputTextEdit(QTextEdit):
    returnPressed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document().contentsChanged.connect(self._adjust_height)
        self.setFixedHeight(30)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.returnPressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
            
    def _adjust_height(self):
        doc_h = int(self.document().size().height())
        new_h = max(30, min(doc_h + 4, 90))
        self.setFixedHeight(new_h)


# ── Main Application Window ─────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kali-AI Agent by Om | Autonomous Security Controller v2.0")
        self.resize(1320, 820)
        self.setStyleSheet(STYLE)
        
        self.engine: Optional[AIEngine] = None
        self._attached_images = []
        self._terminal_output = None
        self._is_autonomous = True
        self._current_session_id = 1
        self._saved_sessions = {}  # {session_id: {"title": str, "messages": list[dict], "history": list}}
        self._session_widgets = {} # {session_id: SessionHistoryButton}
        self._pending_steering_notes = [] # Mid-execution concurrent notes
        self._is_busy = False
        
        config = load_config()
        self.font_size = config.get("font_size", 13)
        global CURRENT_FONT_SIZE
        CURRENT_FONT_SIZE = self.font_size
        
        self._setup_ui()
        self._load_history_from_disk()
        self._try_init_engine()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ── LEFT SIDEBAR ────────────────────────────────────────────────────────
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet(f"background-color: {BG_SIDEBAR}; border-right: 1px solid {BORDER_COLOR};")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 14)
        sidebar_layout.setSpacing(8)
        
        header_box = QHBoxLayout()
        logo_icon = QLabel("🐉")
        logo_icon.setStyleSheet("font-size: 22px;")
        
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title_lbl = QLabel("KALI-AI")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 900; color: #f8fafc; letter-spacing: 1px;")
        subtitle_lbl = QLabel("Agent by Om")
        subtitle_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-weight: bold;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        
        header_box.addWidget(logo_icon)
        header_box.addLayout(title_box)
        header_box.addStretch()
        
        self.btn_hide_sidebar_inner = QPushButton("◀")
        self.btn_hide_sidebar_inner.setFixedSize(26, 26)
        self.btn_hide_sidebar_inner.setToolTip("Hide Sidebar")
        self.btn_hide_sidebar_inner.setStyleSheet("background: transparent; border: none; font-size: 12px; color: #94a3b8;")
        self.btn_hide_sidebar_inner.clicked.connect(self._toggle_sidebar)
        header_box.addWidget(self.btn_hide_sidebar_inner)
        
        sidebar_layout.addLayout(header_box)
        
        self.btn_new_chat = QPushButton("＋ New Conversation")
        self.btn_new_chat.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT_BLUE};
                color: white;
                font-weight: 700;
                font-size: 12px;
                padding: 7px;
                border: none;
                border-radius: 7px;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
        """)
        self.btn_new_chat.clicked.connect(self._save_and_start_new_chat)
        sidebar_layout.addWidget(self.btn_new_chat)
        
        history_lbl = QLabel("CHAT HISTORY")
        history_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-weight: bold; letter-spacing: 1px; margin-top: 6px;")
        sidebar_layout.addWidget(history_lbl)
        
        self.history_scroll = QScrollArea()
        self.history_scroll.setFixedHeight(120)
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(4)
        self.history_layout.addStretch()
        
        self.history_scroll.setWidget(self.history_container)
        sidebar_layout.addWidget(self.history_scroll)
        
        controls_lbl = QLabel("CONTROLS")
        controls_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-weight: bold; letter-spacing: 1px; margin-top: 4px;")
        sidebar_layout.addWidget(controls_lbl)
        
        self.btn_settings = QPushButton("⚙ API & Model Settings")
        self.btn_settings.clicked.connect(self._open_settings)
        
        self.btn_plugins = QPushButton("🔌 Plugins & MCP")
        self.btn_plugins.clicked.connect(self._open_plugins_dialog)
        
        # Feature 1 Button: Target Scope & Safety Guard
        self.btn_target_scope = QPushButton("🎯 Target Scope Guard")
        self.btn_target_scope.clicked.connect(self._open_scope_dialog)
        
        self.btn_clear = QPushButton("🗑 Clear Current Session")
        self.btn_clear.clicked.connect(self._clear_chat)
        
        self.btn_export = QPushButton("📤 Export Log (.txt)")
        self.btn_export.clicked.connect(self._export_chat)
        
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addWidget(self.btn_plugins)
        sidebar_layout.addWidget(self.btn_target_scope)
        sidebar_layout.addWidget(self.btn_clear)
        sidebar_layout.addWidget(self.btn_export)
        
        options_lbl = QLabel("OPTIONS")
        options_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-weight: bold; letter-spacing: 1px; margin-top: 4px;")
        sidebar_layout.addWidget(options_lbl)
        
        self.chk_screenshot = QCheckBox("Auto Vision Screenshot")
        self.chk_screenshot.setChecked(False)
        self.chk_screenshot.setStyleSheet(f"QCheckBox {{ color: {TEXT_MUTED}; font-size: 11px; }} QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px; border: 1px solid {BORDER_COLOR}; background: #0d131f; }} QCheckBox::indicator:checked {{ background: {ACCENT_BLUE}; border-color: {ACCENT_BLUE}; }}")
        sidebar_layout.addWidget(self.chk_screenshot)
        
        sidebar_layout.addStretch()
        
        status_box = QFrame()
        status_box.setStyleSheet(f"background: #0a0f18; border: 1px solid {BORDER_COLOR}; border-radius: 7px; padding: 6px;")
        sb_layout = QVBoxLayout(status_box)
        sb_layout.setContentsMargins(6, 6, 6, 6)
        
        self.status_lbl = QLabel("● Disconnected")
        self.status_lbl.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px; font-weight: 600;")
        sb_layout.addWidget(self.status_lbl)
        
        version_lbl = QLabel("v2.0 Autonomous Engine")
        version_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        sb_layout.addWidget(version_lbl)
        
        sidebar_layout.addWidget(status_box)
        main_layout.addWidget(self.sidebar)
        
        # ── MAIN SPLITTER (Chat vs Terminal) ────────────────────────────────────
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("QSplitter::handle { background-color: #1e293b; width: 2px; }")
        
        # ── CENTER CHAT & INVENTORY PANEL ───────────────────────────────────────
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)
        
        top_bar = QFrame()
        top_bar.setFixedHeight(38)
        top_bar.setStyleSheet(f"background-color: {BG_SIDEBAR}; border-bottom: 1px solid {BORDER_COLOR};")
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        
        self.btn_toggle_sidebar = QPushButton("☰ Sidebar")
        self.btn_toggle_sidebar.setStyleSheet("font-size: 11px; padding: 3px 8px; background: #172030;")
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        tb_layout.addWidget(self.btn_toggle_sidebar)
        
        top_title = QLabel("🐉 Kali-AI Agent by Om")
        top_title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TEXT_PRIMARY};")
        
        self.corner_spinner = CircularSpinnerWidget()
        self.corner_spinner.setToolTip("AI Processing / Executing...")
        
        tb_layout.addStretch()
        tb_layout.addWidget(top_title)
        tb_layout.addWidget(self.corner_spinner)
        tb_layout.addStretch()
        
        # Feature 4 Header Toggle Button: Inventory Dashboard
        self.btn_toggle_inventory = QPushButton("📊 Target Inventory")
        self.btn_toggle_inventory.setStyleSheet(f"font-size: 11px; padding: 3px 8px; background: #172030; color: {ACCENT_AMBER};")
        self.btn_toggle_inventory.clicked.connect(self._toggle_inventory_view)
        tb_layout.addWidget(self.btn_toggle_inventory)
        
        self.btn_toggle_terminal = QPushButton("💻 Terminal Log")
        self.btn_toggle_terminal.setToolTip("Toggle Right Terminal Window")
        self.btn_toggle_terminal.setStyleSheet(f"font-size: 11px; padding: 3px 10px; background: #172030; color: {ACCENT_GREEN}; border-color: #1e293b;")
        self.btn_toggle_terminal.clicked.connect(self._toggle_terminal_panel)
        tb_layout.addWidget(self.btn_toggle_terminal)
        
        # Text Size Controller Widget (A- / 13px / A+)
        font_ctrl_box = QFrame()
        font_ctrl_box.setStyleSheet("background: #0d131f; border: 1px solid #1e293b; border-radius: 6px; padding: 1px 3px;")
        fc_layout = QHBoxLayout(font_ctrl_box)
        fc_layout.setContentsMargins(3, 1, 3, 1)
        fc_layout.setSpacing(2)

        self.btn_font_dec = QPushButton("A-")
        self.btn_font_dec.setToolTip("Decrease Text Size (Ctrl -)")
        self.btn_font_dec.setFixedSize(24, 20)
        self.btn_font_dec.setStyleSheet("font-size: 10px; font-weight: bold; background: transparent; border: none; color: #94a3b8; padding: 0;")
        self.btn_font_dec.clicked.connect(lambda: self._change_font_size(-1))

        self.font_size_lbl = QLabel(f"{self.font_size}px")
        self.font_size_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #3b82f6; padding: 0 2px;")

        self.btn_font_inc = QPushButton("A+")
        self.btn_font_inc.setToolTip("Increase Text Size (Ctrl +)")
        self.btn_font_inc.setFixedSize(24, 20)
        self.btn_font_inc.setStyleSheet("font-size: 10px; font-weight: bold; background: transparent; border: none; color: #94a3b8; padding: 0;")
        self.btn_font_inc.clicked.connect(lambda: self._change_font_size(1))

        fc_layout.addWidget(self.btn_font_dec)
        fc_layout.addWidget(self.font_size_lbl)
        fc_layout.addWidget(self.btn_font_inc)

        tb_layout.addWidget(font_ctrl_box)
        
        chat_layout.addWidget(top_bar)
        
        self.plan_tracker = PlanTrackerWidget()
        chat_layout.addWidget(self.plan_tracker)
        
        # Feature 4 Panel: Target & Asset Inventory Dashboard (Hidden by default)
        self.inventory_panel = TargetInventoryWidget()
        self.inventory_panel.run_action_requested.connect(self._on_inventory_action_requested)
        self.inventory_panel.hide()
        chat_layout.addWidget(self.inventory_panel, stretch=1)
        
        # Chat Messages Container
        self.chat_view_container = QWidget()
        cv_layout = QVBoxLayout(self.chat_view_container)
        cv_layout.setContentsMargins(0, 0, 0, 0)
        cv_layout.setSpacing(0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._smooth_scroll_to_bottom)
        
        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(20, 14, 20, 14)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()
        
        self.scroll_area.setWidget(self.messages_widget)
        cv_layout.addWidget(self.scroll_area, stretch=1)
        
        loading_container = QWidget()
        lc_layout = QHBoxLayout(loading_container)
        lc_layout.setContentsMargins(20, 0, 20, 2)
        self.loading_widget = LoadingWidget()
        self.loading_widget.hide()
        lc_layout.addWidget(self.loading_widget)
        cv_layout.addWidget(loading_container, stretch=0)
        
        input_wrapper = QWidget()
        input_wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        iw_layout = QVBoxLayout(input_wrapper)
        iw_layout.setContentsMargins(16, 4, 16, 12)
        
        self.input_card = QFrame()
        self.input_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.input_card.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_INPUT};
                border: 1px solid #232f45;
                border-radius: 18px;
                padding: 2px 4px;
            }}
            QFrame:focus-within {{
                border-color: {ACCENT_BLUE};
            }}
        """)
        
        ic_layout = QVBoxLayout(self.input_card)
        ic_layout.setContentsMargins(6, 3, 6, 3)
        ic_layout.setSpacing(2)
        
        self.preview_widget = QWidget()
        self.preview_layout = QHBoxLayout(self.preview_widget)
        self.preview_layout.setContentsMargins(0, 0, 0, 2)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.preview_widget.hide()
        ic_layout.addWidget(self.preview_widget)
        
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        
        self.btn_attach = QPushButton("📎")
        self.btn_attach.setFixedSize(30, 30)
        self.btn_attach.setToolTip("Attach Image")
        self.btn_attach.setStyleSheet("background: transparent; border: none; font-size: 15px; color: #94a3b8;")
        self.btn_attach.clicked.connect(self._attach_image)
        
        self.input_field = CompactInputTextEdit()
        self.input_field.setPlaceholderText("Ask Kali-AI, discuss plan, or give command... (Enter to send)")
        self.input_field.setStyleSheet("background: transparent; border: none; font-size: 12px; color: #f8fafc; padding: 2px 0;")
        self.input_field.returnPressed.connect(self._on_send)
        
        self.model_selector = QComboBox()
        self.model_selector.setToolTip("Select Active AI Model")
        self.model_selector.setMinimumWidth(210)
        self.model_selector.setMaxVisibleItems(15)
        self.model_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_selector.view().setMinimumWidth(340)
        self.model_selector.setStyleSheet(f"""
            QComboBox {{
                background: #0b111c;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 3px 10px;
                font-size: 11px;
                color: {ACCENT_BLUE};
                font-weight: 600;
            }}
            QComboBox::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: #0d1522;
                color: #f8fafc;
                selection-background-color: #1e293b;
                border: 1px solid {BORDER_COLOR};
                padding: 4px;
                min-width: 340px;
            }}
        """)
        self.model_selector.currentTextChanged.connect(self._on_dashboard_model_changed)
        
        self.btn_send = QPushButton("▶")
        self.btn_send.setFixedSize(30, 30)
        self.btn_send.setToolTip("Send Message")
        self.btn_send.setStyleSheet(f"background: {ACCENT_BLUE}; color: white; font-weight: bold; border-radius: 15px; font-size: 11px; border: none;")
        self.btn_send.clicked.connect(self._on_send)
        
        self.btn_stop = QPushButton("🟥")
        self.btn_stop.setFixedSize(30, 30)
        self.btn_stop.setToolTip("Stop Active AI Action / Cancel Task")
        self.btn_stop.setStyleSheet(f"background: #2b1717; color: {ACCENT_RED}; font-weight: bold; border-radius: 15px; font-size: 11px; border: 1px solid #4a2020;")
        self.btn_stop.clicked.connect(self._stop_ai_execution)
        self.btn_stop.hide()
        
        row_layout.addWidget(self.btn_attach)
        row_layout.addWidget(self.input_field, stretch=1)
        row_layout.addWidget(self.model_selector)
        row_layout.addWidget(self.btn_send)
        row_layout.addWidget(self.btn_stop)
        
        ic_layout.addLayout(row_layout)
        apply_shadow(self.input_card, blur=14, offset_y=3, alpha=110)
        
        iw_layout.addWidget(self.input_card)
        cv_layout.addWidget(input_wrapper, stretch=0)
        
        chat_layout.addWidget(self.chat_view_container, stretch=1)
        
        self.main_splitter.addWidget(chat_container)
        
        # ── DEDICATED RIGHT TERMINAL PANEL ─────────────────────────────────────
        self.terminal_panel = QFrame()
        self.terminal_panel.setStyleSheet(f"background-color: {BG_TERMINAL}; border-left: 1px solid {BORDER_COLOR};")
        term_layout = QVBoxLayout(self.terminal_panel)
        term_layout.setContentsMargins(10, 10, 10, 10)
        term_layout.setSpacing(6)
        
        term_header = QHBoxLayout()
        term_title = QLabel("💻 DEDICATED TERMINAL LOG")
        term_title.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {ACCENT_GREEN}; letter-spacing: 1px;")
        
        self.btn_clear_term = QPushButton("Clear")
        self.btn_clear_term.setStyleSheet("font-size: 10px; padding: 2px 6px; background: #121927;")
        self.btn_clear_term.clicked.connect(self._clear_terminal_output)
        
        term_header.addWidget(term_title)
        term_header.addStretch()
        term_header.addWidget(self.btn_clear_term)
        term_layout.addLayout(term_header)
        
        self.terminal_log = QPlainTextEdit()
        self.terminal_log.setReadOnly(True)
        self.terminal_log.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #04070c;
                border: 1px solid #1a2333;
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 11px;
                color: #4ade80;
                line-height: 1.4;
            }}
        """)
        self.terminal_log.appendPlainText("[*] Kali-AI Terminal Window Active.\n[*] Output logs will stream here in real-time...\n")
        term_layout.addWidget(self.terminal_log)
        
        self.main_splitter.addWidget(self.terminal_panel)
        self.main_splitter.setSizes([760, 420])
        
        main_layout.addWidget(self.main_splitter)

    def _open_scope_dialog(self):
        dlg = TargetScopeDialog(self)
        dlg.exec()

    def _toggle_inventory_view(self):
        is_inv_vis = self.inventory_panel.isVisible()
        if is_inv_vis:
            self.inventory_panel.hide()
            self.chat_view_container.show()
            self.btn_toggle_inventory.setStyleSheet(f"font-size: 11px; padding: 3px 8px; background: #172030; color: {ACCENT_AMBER};")
        else:
            self.chat_view_container.hide()
            self.inventory_panel.show()
            self.btn_toggle_inventory.setStyleSheet(f"font-size: 11px; padding: 3px 8px; background: {ACCENT_AMBER}; color: black; font-weight: bold;")

    def _on_inventory_action_requested(self, command_prompt: str):
        self._toggle_inventory_view()
        self.input_field.setPlainText(command_prompt)
        self._on_send()

    def _set_busy_state(self, is_busy: bool):
        self._is_busy = is_busy
        self.input_field.setReadOnly(False) # Always keep input unlocked for mid-execution steering notes!
        
        if is_busy:
            self.input_field.setPlaceholderText("🐉 Process running... Type mid-execution notes or questions anytime!")
            self.btn_stop.show()
            self.loading_widget.start()
            self.corner_spinner.start()
        else:
            self.input_field.setPlaceholderText("Ask Kali-AI, discuss plan, or give command... (Enter to send)")
            self.btn_stop.hide()
            self.btn_send.show()
            self.loading_widget.stop()
            self.corner_spinner.stop()

    def _stop_ai_execution(self):
        """Immediately abort active AI thread, cancel background commands, and unlock UI."""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            try:
                self.worker.terminate()
                self.worker.wait(500)
            except Exception:
                pass
                
        self.terminal_log.appendPlainText("\n[ABORTED] Active AI action/execution stopped by user.\n")
        self._add_bubble("system", "⏹ **AI Action Aborted**: Execution stopped by user.")
        self._terminal_output = None
        self._set_busy_state(False)

    def _change_font_size(self, delta: int):
        """Increase or decrease text/font size across the chat UI."""
        new_size = max(10, min(24, self.font_size + delta))
        if new_size == self.font_size:
            return
        self.font_size = new_size
        global CURRENT_FONT_SIZE
        CURRENT_FONT_SIZE = new_size
        
        self.font_size_lbl.setText(f"{self.font_size}px")
        
        # Save font_size preference to config
        cfg = load_config()
        cfg["font_size"] = self.font_size
        save_config(cfg)
        
        # Update all active chat bubbles in current layout
        count = self.messages_layout.count()
        for i in range(count):
            item = self.messages_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, ChatBubble):
                    widget.update_font_size(self.font_size)

    def keyPressEvent(self, event):
        """Global keyboard shortcuts: Ctrl+ or Ctrl= (Zoom in), Ctrl- (Zoom out)."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self._change_font_size(1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Minus:
                self._change_font_size(-1)
                event.accept()
                return
        super().keyPressEvent(event)

    def _toggle_sidebar(self):
        self.sidebar.setVisible(not self.sidebar.isVisible())

    def _toggle_terminal_panel(self):
        is_vis = self.terminal_panel.isVisible()
        self.terminal_panel.setVisible(not is_vis)
        if not is_vis:
            self.main_splitter.setSizes([700, 420])

    def _clear_terminal_output(self):
        self.terminal_log.clear()
        self.terminal_log.appendPlainText("[*] Terminal log cleared.\n")

    def _try_init_engine(self):
        config = load_config()
        provider = config.get("provider", "gemini")
        
        has_key = False
        if provider == "openai" and config.get("openai_api_key"):
            has_key = True
        elif provider == "gemini" and config.get("gemini_api_key"):
            has_key = True
        
        if has_key:
            try:
                self.engine = AIEngine(
                    provider=provider,
                    openai_key=config.get("openai_api_key", ""),
                    openai_url=config.get("openai_base_url", "https://openrouter.ai/api/v1"),
                    openai_model=config.get("openai_model", "openai/gpt-4o"),
                    gemini_key=config.get("gemini_api_key", ""),
                    gemini_model=config.get("gemini_model", "gemini-2.0-flash")
                )
                model_name = config.get(f"{provider}_model", "unknown")
                self.status_lbl.setText(f"● {provider.upper()} | Active")
                self.status_lbl.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: 600;")
                
                self.model_selector.blockSignals(True)
                if self.model_selector.findText(model_name) == -1:
                    self.model_selector.addItem(model_name)
                self.model_selector.setCurrentText(model_name)
                self.model_selector.blockSignals(False)
                
                self.fetch_worker = ModelFetchWorker(self.engine)
                self.fetch_worker.models_ready.connect(self._on_dashboard_models_ready)
                self.fetch_worker.start()
                
            except Exception:
                self.status_lbl.setText("● Init Failed")
                self.status_lbl.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px;")

    def _on_dashboard_models_ready(self, models: list):
        if not models:
            return
        config = load_config()
        provider = config.get("provider", "gemini")
        cur_model = config.get(f"{provider}_model", "")
        
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        self.model_selector.addItems(models)
        if cur_model in models:
            self.model_selector.setCurrentText(cur_model)
        else:
            self.model_selector.setCurrentIndex(0)
        self.model_selector.blockSignals(False)

    def _on_dashboard_model_changed(self, new_model: str):
        if not new_model or not self.engine:
            return
        config = load_config()
        provider = config.get("provider", "gemini")
        config[f"{provider}_model"] = new_model
        save_config(config)
        self.engine.reconfigure(
            provider=provider,
            openai_key=config.get("openai_api_key", ""),
            openai_url=config.get("openai_base_url", "https://openrouter.ai/api/v1"),
            openai_model=config.get("openai_model", ""),
            gemini_key=config.get("gemini_api_key", ""),
            gemini_model=config.get("gemini_model", "")
        )

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._try_init_engine()

    def _open_plugins_dialog(self):
        dlg = PluginManagerDialog(self)
        dlg.exec()

    def _attach_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        if file_path:
            self._attached_images.append(file_path)
            self._rebuild_preview_strip()
            
    def _rebuild_preview_strip(self):
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        if not self._attached_images:
            self.preview_widget.hide()
            return
            
        self.preview_widget.show()
        
        for path in self._attached_images:
            container = QFrame()
            container.setStyleSheet(f"background: {BG_CARD}; border-radius: 5px; padding: 2px;")
            c_layout = QHBoxLayout(container)
            c_layout.setContentsMargins(3, 3, 3, 3)
            
            img_lbl = QLabel()
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                img_lbl.setPixmap(pixmap.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            
            close_btn = QPushButton("✕")
            close_btn.setFixedSize(16, 16)
            close_btn.setStyleSheet(f"background: {ACCENT_RED}; color: white; border-radius: 8px; font-size: 8px; padding: 0;")
            close_btn.clicked.connect(lambda checked=False, p=path: self._remove_attached_image(p))
            
            c_layout.addWidget(img_lbl)
            c_layout.addWidget(close_btn)
            self.preview_layout.addWidget(container)

    def _remove_attached_image(self, path: str):
        if path in self._attached_images:
            self._attached_images.remove(path)
            self._rebuild_preview_strip()

    def _on_send(self):
        if not self.engine:
            QMessageBox.warning(self, "API Config Missing", "Please configure your API Key in Settings first.")
            self._open_settings()
            return
            
        text = self.input_field.toPlainText().strip()
        has_images = len(self._attached_images) > 0
        
        if not text and not has_images:
            return
            
        self.input_field.clear()
        
        # Check if AI is currently executing a process
        if self._is_busy:
            self._add_bubble("user", f"💬 **Mid-Execution Note**: {text}")
            self._pending_steering_notes.append(text)
            self.terminal_log.appendPlainText(f"\n[MID-EXECUTION STEERING QUEUED]: {text}\n")
            return
        
        display_text = text
        if has_images:
            for path in self._attached_images:
                display_text += f"\n[IMG:{path}]"
                
        self._add_bubble("user", display_text)
        self._set_busy_state(True)
        
        images_to_send = self._attached_images.copy() if has_images else None
        
        self.worker = AIWorker(
            engine=self.engine,
            user_text=text,
            attach_screenshot=self.chk_screenshot.isChecked(),
            terminal_output=self._terminal_output,
            image_paths=images_to_send
        )
        self.worker.result_ready.connect(self._on_ai_result)
        self.worker.error_occurred.connect(self._on_ai_error)
        self.worker.start()
        
        self._terminal_output = None
        self._attached_images.clear()
        self._rebuild_preview_strip()

    def _on_ai_result(self, res: dict):
        action_type = res.get("action_type", "chat").lower()
        command = res.get("command", "").strip()
        gui_action = res.get("gui_action")
        thought = res.get("thought", "")
        plan = res.get("plan", [])
        options = res.get("options", [])
        confidence = res.get("confidence_score", 90)
        risk = res.get("impact_risk", "Low")
        response_text = res.get("response_message", "") or res.get("response", "")
        
        if plan:
            self.plan_tracker.update_plan(plan)
            
        display = response_text or thought or "(No response message provided)"
        self._add_bubble("assistant", display, confidence_score=confidence, impact_risk=risk, options=options)
            
        if action_type == "bash" and command:
            self._add_intercept(command)
            self._set_busy_state(False)
        elif action_type == "gui" and gui_action:
            self.terminal_log.appendPlainText(f"\n[GUI ACTION] Executing: {gui_action}")
            exec_res = run_gui_action(gui_action)
            self._handle_execution_result(exec_res, command_text=f"GUI:{gui_action}")
        else:
            self._set_busy_state(False)

    def _on_ai_error(self, error: str):
        self._set_busy_state(False)
        self._add_bubble("system", f"**Error**: {error}")

    def _add_bubble(self, role: str, text: str, confidence_score: Optional[int] = None, impact_risk: Optional[str] = None, options: Optional[list] = None):
        bubble = ChatBubble(role, text, confidence_score=confidence_score, impact_risk=impact_risk, options=options)
        bubble.option_selected.connect(self._on_user_option_clicked)
        count = self.messages_layout.count()
        self.messages_layout.insertWidget(count - 1, bubble)
        self._smooth_scroll_to_bottom()
        QTimer.singleShot(100, self._auto_save_active_session)

    def _on_user_option_clicked(self, selected_option: str):
        """User clicked an interactive decision option button."""
        self.input_field.setPlainText(selected_option)
        self._on_send()

    def _add_intercept(self, command: str):
        banner = InterceptBanner(command)
        banner.approved.connect(self._on_command_approved)
        banner.cancelled.connect(self._on_command_cancelled)
        
        count = self.messages_layout.count()
        self.messages_layout.insertWidget(count - 1, banner)
        self._smooth_scroll_to_bottom()

    def _on_command_approved(self, command: str):
        count = self.messages_layout.count()
        for i in range(count - 2, -1, -1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, InterceptBanner):
                widget.setParent(None)
                widget.deleteLater()
                break
                
        self.terminal_log.appendPlainText(f"\n$ {command}")
        QApplication.processEvents()
        
        self._set_busy_state(True)
        exec_res = run_bash(command)
        self._handle_execution_result(exec_res, command_text=command)

    def _on_command_cancelled(self):
        count = self.messages_layout.count()
        for i in range(count - 2, -1, -1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, InterceptBanner):
                widget.setParent(None)
                widget.deleteLater()
                break
        self._add_bubble("system", "Execution paused / command cancelled by user.")
        self.terminal_log.appendPlainText("\n[CANCELLED] Command execution rejected by user.\n")
        self._terminal_output = "User cancelled command execution."
        self._set_busy_state(False)

    def _handle_execution_result(self, exec_res, command_text: str = ""):
        out = exec_res.combined_output()
        if not out:
            out = "(Command completed with no stdout/stderr)"
        
        status_str = "SUCCESS" if exec_res.success else "FAILED"
        if exec_res.blocked:
            status_str = "BLOCKED BY GUARDRAILS"
            
        self.terminal_log.appendPlainText(f"[{status_str}]\n{out}\n" + "─"*50)
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())
        
        self._terminal_output = out
        
        if self._is_autonomous and not exec_res.blocked:
            QTimer.singleShot(500, self._trigger_autonomous_next_turn)
        else:
            self._set_busy_state(False)

    def _trigger_autonomous_next_turn(self):
        if not self.engine:
            self._set_busy_state(False)
            return
            
        self._set_busy_state(True)
        
        user_prompt = ""
        if self._pending_steering_notes:
            notes_str = "\n".join(self._pending_steering_notes)
            user_prompt = f"[USER MID-EXECUTION STEERING NOTE]: {notes_str}"
            self._pending_steering_notes.clear()
        
        self.worker = AIWorker(
            engine=self.engine,
            user_text=user_prompt,
            attach_screenshot=self.chk_screenshot.isChecked(),
            terminal_output=self._terminal_output,
            image_paths=None
        )
        self.worker.result_ready.connect(self._on_ai_result)
        self.worker.error_occurred.connect(self._on_ai_error)
        self.worker.start()
        
        self._terminal_output = None

    def _smooth_scroll_to_bottom(self):
        QTimer.singleShot(80, self._do_scroll)

    def _do_scroll(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _load_history_from_disk(self):
        """Load persistent chat history sessions from ~/.config/kali-ai/sessions.json on application startup."""
        saved_list = load_all_sessions()
        for session_item in saved_list:
            sid = session_item.get("id", self._current_session_id)
            title = session_item.get("title", f"💬 Session {sid}")
            messages = session_item.get("messages", [])
            
            self._saved_sessions[sid] = {
                "title": title,
                "messages": messages
            }
            
            btn_session = SessionHistoryButton(sid, title)
            btn_session.clicked.connect(lambda checked=False, s_id=sid: self._load_saved_session(s_id))
            btn_session.delete_requested.connect(self._delete_session)
            
            self._session_widgets[sid] = btn_session
            self.history_layout.insertWidget(0, btn_session)
            if sid >= self._current_session_id:
                self._current_session_id = sid + 1

    def _persist_sessions_to_disk(self):
        """Save all session data to disk."""
        disk_data = []
        for sid, sdata in self._saved_sessions.items():
            disk_data.append({
                "id": sid,
                "title": sdata.get("title", ""),
                "messages": sdata.get("messages", [])
            })
        save_all_sessions(disk_data)

    def _save_and_start_new_chat(self):
        """Save active chat session messages, persist to disk, and add a SessionHistoryButton with right-click delete."""
        count = self.messages_layout.count()
        saved_messages = []
        session_title = f"💬 Session {self._current_session_id}"
        
        for i in range(count - 1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, ChatBubble):
                text_content = widget.text_browser.toPlainText().strip()
                if widget.role == "user" and session_title.startswith("💬 Session"):
                    if text_content:
                        session_title = f"💬 {text_content[:22]}..."
                saved_messages.append({
                    "role": widget.role,
                    "text": text_content
                })
                
        if saved_messages:
            sid = self._current_session_id
            self._saved_sessions[sid] = {
                "title": session_title,
                "messages": saved_messages
            }
            
            btn_session = SessionHistoryButton(sid, session_title)
            btn_session.clicked.connect(lambda checked=False, s_id=sid: self._load_saved_session(s_id))
            btn_session.delete_requested.connect(self._delete_session)
            
            self._session_widgets[sid] = btn_session
            self.history_layout.insertWidget(0, btn_session)
            self._current_session_id += 1
            
            self._persist_sessions_to_disk()
            
        self._clear_chat()

    def _load_saved_session(self, sid: int):
        """Reload all bubbles and context from a saved chat session."""
        session_data = self._saved_sessions.get(sid)
        if not session_data:
            return
            
        # 1. Clear current UI view
        count = self.messages_layout.count()
        for i in range(count - 2, -1, -1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
                
        # 2. Reset AI engine history
        if self.engine:
            self.engine.reset_history()
            
        # 3. Re-populate bubbles from saved session
        for msg in session_data.get("messages", []):
            self._add_bubble(msg.get("role", "system"), msg.get("text", ""))
            
        self._add_bubble("system", f"⚡ **Session Restored**: Switched to {session_data.get('title', 'Session')}")

    def _delete_session(self, sid: int):
        """Right-click delete session handler with disk removal."""
        if sid in self._saved_sessions:
            del self._saved_sessions[sid]
        if sid in self._session_widgets:
            btn = self._session_widgets.pop(sid)
            btn.setParent(None)
            btn.deleteLater()
        delete_session_by_id(sid)

    def _clear_chat(self):
        count = self.messages_layout.count()
        for i in range(count - 2, -1, -1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
                
        if self.engine:
            self.engine.reset_history()
            
        self.plan_tracker.hide()
        self._clear_terminal_output()
        self._set_busy_state(False)

    def _export_chat(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt)")
        if not path:
            return
            
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("=== KALI-AI CONVERSATION LOG ===\n\n")
                count = self.messages_layout.count()
                for i in range(count - 1):
                    item = self.messages_layout.itemAt(i)
                    widget = item.widget()
                    if isinstance(widget, ChatBubble):
                        f.write(f"--- {widget.role.upper()} ---\n")
                        f.write(widget.text_browser.toPlainText() + "\n\n")
                
            QMessageBox.information(self, "Export Successful", f"Logs exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not save file: {str(e)}")

    def _auto_save_active_session(self):
        """Real-time auto save current active conversation to disk after every message & on app close."""
        count = self.messages_layout.count()
        saved_messages = []
        session_title = f"💬 Session {self._current_session_id}"
        
        for i in range(count - 1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, ChatBubble):
                text_content = widget.text_browser.toPlainText().strip()
                if widget.role == "user" and session_title.startswith("💬 Session"):
                    if text_content:
                        session_title = f"💬 {text_content[:22]}..."
                saved_messages.append({
                    "role": widget.role,
                    "text": text_content
                })
                
        if saved_messages:
            sid = self._current_session_id
            self._saved_sessions[sid] = {
                "title": session_title,
                "messages": saved_messages
            }
            
            if sid not in self._session_widgets:
                btn_session = SessionHistoryButton(sid, session_title)
                btn_session.clicked.connect(lambda checked=False, s_id=sid: self._load_saved_session(s_id))
                btn_session.delete_requested.connect(self._delete_session)
                self._session_widgets[sid] = btn_session
                self.history_layout.insertWidget(0, btn_session)
            else:
                self._session_widgets[sid].setText(session_title)
                
            self._persist_sessions_to_disk()

    def closeEvent(self, event):
        """Save active session to disk on application exit."""
        try:
            self._auto_save_active_session()
        except Exception:
            pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
