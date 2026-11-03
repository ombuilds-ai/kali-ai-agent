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
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QInputDialog
)

from ai_engine import AIEngine
from config import load_config, save_config
from executor import run_bash, resume_bash, run_gui_action, get_screen_size, ExecutionResult
from guardrails import set_allowed_target_scopes, get_allowed_target_scopes, classify_command
from sessions import load_all_sessions, save_all_sessions, delete_session_by_id
from shell_session import get_shell
from jobs import get_job_manager
from ghidra import get_ghidra
import tools
import memory

# ── Sleek Modern Palette ────────────────────────────────────────────────────────
# ── Cyber-Glass Palette (v3.0) ──────────────────────────────────────────────────
BG_DARK = "#0a0b14"       # Main canvas (deep space)
BG_SIDEBAR = "#0d0e1a"    # Left navigation rail
BG_TERMINAL = "#06070f"   # Terminal output panel
BG_CARD = "#151724"       # Assistant glass cards
BG_USER = "#1c1740"       # User message bubbles (violet tint)
BG_INPUT = "#111322"      # Floating input bar
BORDER_COLOR = "#23263a"  # Subtle borders
ACCENT_BLUE = "#7c5cff"   # Primary accent (electric violet) — name kept for compat
ACCENT_CYAN = "#22d3ee"   # Secondary accent (cyan)
ACCENT_GREEN = "#2dd4bf"  # Success (teal)
ACCENT_RED = "#fb5a6a"    # Danger
ACCENT_AMBER = "#f5b14c"  # Warning
TEXT_PRIMARY = "#eceefb"  # Primary text
TEXT_MUTED = "#8b8fae"    # Muted text

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
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a2d45; min-height: 28px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_BLUE}; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2a2d45; min-width: 28px; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_BLUE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0px; width: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QPushButton {{
    border-radius: 9px;
    padding: 7px 13px;
    font-weight: 600;
    background-color: rgba(255, 255, 255, 0.04);
    border: 1px solid {BORDER_COLOR};
    color: #d8dbf0;
}}
QPushButton:hover {{
    background-color: rgba(124, 92, 255, 0.14);
    border-color: {ACCENT_BLUE};
    color: {TEXT_PRIMARY};
}}
QPushButton:pressed {{ background-color: rgba(124, 92, 255, 0.08); }}
QLineEdit, QComboBox {{
    background-color: #0c0e1a;
    border: 1px solid {BORDER_COLOR};
    border-radius: 9px;
    padding: 7px 11px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_BLUE};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT_BLUE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: #12131f;
    color: {TEXT_PRIMARY};
    selection-background-color: rgba(124, 92, 255, 0.25);
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QCheckBox {{ color: {TEXT_MUTED}; font-size: 11px; spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 5px;
    border: 1px solid {BORDER_COLOR}; background: #0c0e1a;
}}
QCheckBox::indicator:checked {{ background: {ACCENT_BLUE}; border-color: {ACCENT_BLUE}; }}
QToolTip {{
    background-color: #12131f; color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT_BLUE}; border-radius: 6px; padding: 5px 8px;
}}
QSplitter::handle {{ background-color: {BG_DARK}; width: 3px; }}
QSplitter::handle:hover {{ background-color: {ACCENT_BLUE}; }}
QMenu {{
    background-color: #12131f; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 5px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: rgba(124, 92, 255, 0.25); }}
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

    # 1. Extract fenced code blocks into placeholders so markdown/line handling can't touch them.
    blocks = []

    def _code_block(match):
        lang = (match.group(1) or "bash").strip() or "bash"
        code = match.group(2).rstrip("\n")
        html = (
            f'<div style="background-color:#0b0d18; border:1px solid #262a40; border-radius:10px; margin:8px 0;">'
            f'<div style="background-color:#141627; padding:5px 11px; font-family:Consolas,monospace; '
            f'font-size:{code_size - 1}px; color:#9aa0c4; border-bottom:1px solid #262a40;">&#9889; {lang}</div>'
            f'<pre style="padding:11px; margin:0; font-family:Consolas,monospace; font-size:{code_size}px; '
            f'color:#d8dbf0; line-height:1.45; white-space:pre-wrap;">{code}</pre></div>'
        )
        blocks.append(html)
        return f"\x00CB{len(blocks) - 1}\x00"

    text = re.sub(r'```([\w\+\-\.]*)?\n(.*?)```', _code_block, text, flags=re.DOTALL)

    # 2. Inline markdown (operates on the remaining non-code text).
    text = re.sub(
        r'`([^`]+)`',
        f'<code style="background-color:#1a1c2e; padding:2px 6px; border-radius:5px; '
        f'font-family:Consolas,monospace; color:#a78bfa; font-size:{code_size}px;">\\1</code>',
        text,
    )
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" style="color:#60a5fa; text-decoration:none;">\1</a>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color:#ffffff;">\1</strong>', text)
    text = re.sub(r'\[IMG:(.*?)\]', r'<br><img src="file:///\1" style="max-width:380px; border-radius:10px; margin:6px 0;"><br>', text)

    # 3. Block-level markdown line by line (headings, lists, rules), ChatGPT-style.
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("\x00CB") and s.endswith("\x00"):
            out.append(s)
        elif re.match(r'^###\s+', s):
            out.append(f'<div style="font-size:{font_size + 1}px; font-weight:700; color:#fff; margin:9px 0 2px;">' + re.sub(r'^###\s+', '', s) + '</div>')
        elif re.match(r'^##\s+', s):
            out.append(f'<div style="font-size:{font_size + 3}px; font-weight:800; color:#fff; margin:11px 0 3px;">' + re.sub(r'^##\s+', '', s) + '</div>')
        elif re.match(r'^#\s+', s):
            out.append(f'<div style="font-size:{font_size + 5}px; font-weight:800; color:#fff; margin:12px 0 4px;">' + re.sub(r'^#\s+', '', s) + '</div>')
        elif s in ("---", "***", "___"):
            out.append('<hr style="border:none; border-top:1px solid #2a2d45; margin:9px 0;">')
        elif re.match(r'^[-*+]\s+', s):
            out.append('<div style="margin:2px 0 2px 10px;">&#8226;&nbsp; ' + re.sub(r'^[-*+]\s+', '', s) + '</div>')
        elif re.match(r'^\d+\.\s+', s):
            out.append('<div style="margin:2px 0 2px 10px;">' + s + '</div>')
        elif s == "":
            out.append('<div style="height:7px;"></div>')
        else:
            out.append('<div style="margin:1px 0;">' + line + '</div>')
    html = "".join(out)

    # 4. Restore code blocks.
    html = re.sub(r'\x00CB(\d+)\x00', lambda m: blocks[int(m.group(1))], html)
    return f'<div style="font-size:{font_size}px; line-height:1.55; color:#eceefb;">{html}</div>'


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


class CommandWorker(QThread):
    """Runs an execution func OFF the GUI thread, streaming output chunks as they arrive.

    `func` takes an on_output callback and returns an ExecutionResult, e.g.
    `lambda cb: run_bash(command, on_output=cb)` or
    `lambda cb: resume_bash(input_text, on_output=cb)`.
    """
    output_chunk = pyqtSignal(str)
    finished_result = pyqtSignal(object)

    def __init__(self, func):
        super().__init__()
        self._func = func

    def run(self):
        try:
            res = self._func(lambda c: self.output_chunk.emit(c))
        except Exception as e:
            res = ExecutionResult(success=False, stderr=f"Execution error: {e}")
        self.finished_result.emit(res)


class ModelFetchWorker(QThread):
    models_ready = pyqtSignal(list)
    models_map_ready = pyqtSignal(dict)   # {provider: [model_ids]} when tagged
    fetch_failed = pyqtSignal(str)

    def __init__(self, engine: AIEngine, merged: bool = False, tagged: bool = False):
        super().__init__()
        self.engine = engine
        self.merged = merged   # True = all providers' models combined (flat list)
        self.tagged = tagged   # True = per-provider dict (so selection knows the provider)

    def run(self):
        try:
            if self.tagged:
                self.models_map_ready.emit(self.engine.get_all_available_models())
            elif self.merged:
                self.models_ready.emit(self.engine.get_merged_models())
            else:
                self.models_ready.emit(self.engine.get_available_models())
        except Exception as e:
            self.fetch_failed.emit(str(e))


# ── Live Execution Plan Tracker Widget ──────────────────────────────────────────
class PlanTrackerWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: rgba(124, 92, 255, 0.05); border-bottom: 1px solid {BORDER_COLOR}; padding: 4px 8px; }}")
        
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
        # Resizable + scrollable so all fields fit on any screen size (small VMs included).
        self.setMinimumSize(500, 420)
        self.resize(540, 600)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")
        
        self.config = load_config()
        self.engine: Optional[AIEngine] = None

        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        _content = QWidget()
        _scroll.setWidget(_content)
        _outer.addWidget(_scroll)

        layout = QVBoxLayout(_content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        title_label = QLabel("API & Model Settings")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title_label)
        
        provider_layout = QHBoxLayout()
        provider_layout.addWidget(QLabel("AI Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["openai", "gemini", "custom"])
        self.provider_combo.setCurrentText(self.config.get("provider", "gemini"))
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addWidget(self.provider_combo)
        layout.addLayout(provider_layout)
        
        self.openai_group = QGroupBox("OpenRouter / OpenAI / Custom API")
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

        extras = QHBoxLayout()
        self.btn_openrouter_preset = QPushButton("🆓 Use OpenRouter")
        self.btn_openrouter_preset.setToolTip("Set the base URL to OpenRouter and show free models")
        self.btn_openrouter_preset.setStyleSheet(f"font-size: 11px; padding: 4px 10px; background: #172030; color: {ACCENT_CYAN};")
        self.btn_openrouter_preset.clicked.connect(self._use_openrouter_preset)
        extras.addWidget(self.btn_openrouter_preset)
        extras.addStretch()
        openai_layout.addRow("", extras)
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

        # Third provider: a fully custom OpenAI-compatible endpoint.
        self.custom_group = QGroupBox("Custom API (OpenAI-compatible: local LLM / vLLM / LM Studio / any gateway)")
        self.custom_group.setStyleSheet(f"QGroupBox {{ border: 1px solid {BORDER_COLOR}; border-radius: 8px; margin-top: 8px; font-weight: bold; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}")
        custom_layout = QFormLayout(self.custom_group)
        custom_layout.setContentsMargins(10, 14, 10, 10)
        self.custom_url = QLineEdit(self.config.get("custom_base_url", ""))
        self.custom_url.setPlaceholderText("e.g. http://localhost:11434/v1  or  https://your-gateway/v1")
        self.custom_key = QLineEdit(self.config.get("custom_api_key", ""))
        self.custom_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.custom_model = QLineEdit(self.config.get("custom_model", ""))
        self.custom_model.setPlaceholderText("model id, e.g. llama3.1:8b  or  my-model")
        custom_layout.addRow("Base URL:", self.custom_url)
        custom_layout.addRow("API Key:", self.custom_key)
        custom_layout.addRow("Model ID:", self.custom_model)
        layout.addWidget(self.custom_group)

        # Unlimited EXTRA custom endpoints — each added via the ＋ button as its own
        # 3-field block (Base URL, API Key, Model ID).
        self.extra_group = QGroupBox("More Custom APIs — click ＋ to add another endpoint")
        self.extra_group.setStyleSheet(self.custom_group.styleSheet())
        extra_v = QVBoxLayout(self.extra_group)
        extra_v.setContentsMargins(10, 14, 10, 10)
        extra_v.setSpacing(8)

        self._custom_rows = []
        self._extra_rows_layout = QVBoxLayout()
        self._extra_rows_layout.setSpacing(8)
        extra_v.addLayout(self._extra_rows_layout)

        self.btn_add_custom = QPushButton("＋ Add Custom API")
        self.btn_add_custom.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_BLUE}; color: #0a0b14; font-weight: 700; "
            f"border: none; border-radius: 8px; padding: 7px; }}"
            f"QPushButton:hover {{ background: #8f72ff; }}"
        )
        self.btn_add_custom.clicked.connect(lambda: self._add_custom_api_row())
        extra_v.addWidget(self.btn_add_custom)
        layout.addWidget(self.extra_group)

        # Load any saved extra endpoints as rows.
        for api in self.config.get("custom_apis", []):
            self._add_custom_api_row(api)

        # Free-models filter applies to all providers, so it lives outside the groups.
        self.free_only_chk = QCheckBox("🆓 Show FREE models only (Gemini flash/gemma + OpenRouter :free)")
        self.free_only_chk.setChecked(bool(self.config.get("free_models_only", False)))
        self.free_only_chk.setToolTip("Lists only no-cost models for whichever provider you use.")
        self.free_only_chk.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.free_only_chk)
        
        self._on_provider_changed(self.provider_combo.currentText())
        
        self.fetch_timer = QTimer(self)
        self.fetch_timer.setSingleShot(True)
        self.fetch_timer.setInterval(800)
        self.fetch_timer.timeout.connect(self._auto_fetch_models)
        
        self.openai_key.textChanged.connect(lambda: self.fetch_timer.start())
        self.openai_url.textChanged.connect(lambda: self.fetch_timer.start())
        self.gemini_key.textChanged.connect(lambda: self.fetch_timer.start())
        self.free_only_chk.toggled.connect(lambda: self.fetch_timer.start())
        
        if self.openai_key.text().strip() or self.gemini_key.text().strip():
            QTimer.singleShot(300, self._auto_fetch_models)
        
        self.operator_chk = QCheckBox("⚡ Operator Mode — never refuse authorized security tasks")
        self.operator_chk.setChecked(bool(self.config.get("operator_mode", True)))
        self.operator_chk.setToolTip(
            "When ON, the agent treats every request as authorized engagement work and will not "
            "refuse / moralize on legitimate offensive-security tasks. Target-scope and self-destruction "
            "guardrails still apply."
        )
        self.operator_chk.setStyleSheet(f"color: {ACCENT_AMBER}; font-size: 11px; font-weight: 600;")
        layout.addWidget(self.operator_chk)

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

    def _use_openrouter_preset(self):
        """One click: switch to OpenRouter + free models, so pasting a key lists free models."""
        self.provider_combo.setCurrentText("openai")
        self.openai_url.setText("https://openrouter.ai/api/v1")
        self.free_only_chk.setChecked(True)
        self.status_label.setText("OpenRouter selected. Paste your API key to auto-list free models.")
        self.status_label.setStyleSheet(f"color: {ACCENT_CYAN};")
        if self.openai_key.text().strip():
            self.fetch_timer.start()

    def _add_custom_api_row(self, data=None):
        """Append a fresh Base URL / API Key / Model ID block for one custom endpoint."""
        data = data or {}
        row = QFrame()
        row.setStyleSheet(f"QFrame {{ border: 1px solid {BORDER_COLOR}; border-radius: 8px; background: rgba(255,255,255,0.02); }}")
        rl = QFormLayout(row)
        rl.setContentsMargins(10, 8, 10, 8)
        url = QLineEdit(data.get("base_url", ""))
        url.setPlaceholderText("https://your-endpoint/v1")
        key = QLineEdit(data.get("api_key", ""))
        key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText("API key (or leave blank for local)")
        model = QLineEdit(data.get("model", ""))
        model.setPlaceholderText("model id, e.g. llama3.1:8b")
        rl.addRow("Base URL:", url)
        rl.addRow("API Key:", key)
        rl.addRow("Model ID:", model)

        rm = QPushButton("✕ Remove")
        rm.setStyleSheet(f"background:#261616; color:{ACCENT_RED}; border:1px solid #4d2222; border-radius:6px; font-size:10px; padding:3px 8px;")
        entry = {"frame": row, "url": url, "key": key, "model": model}
        rm.clicked.connect(lambda _=False, e=entry: self._remove_custom_api_row(e))
        rl.addRow("", rm)

        self._custom_rows.append(entry)
        self._extra_rows_layout.addWidget(row)

    def _remove_custom_api_row(self, entry):
        try:
            self._custom_rows.remove(entry)
        except ValueError:
            pass
        entry["frame"].setParent(None)
        entry["frame"].deleteLater()

    def _on_provider_changed(self, provider: str):
        # Both providers can be configured at the same time — show BOTH groups so the
        # user can enter their Gemini key AND their OpenRouter key together. The dropdown
        # just picks the PRIMARY/default provider; the agent can use models from both.
        self.openai_group.setVisible(True)
        self.gemini_group.setVisible(True)
        self.custom_group.setVisible(True)
        self.extra_group.setVisible(True)
        
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
                gemini_model=self.gemini_model.currentText().strip(),
                custom_key=self.custom_key.text().strip(),
                custom_url=self.custom_url.text().strip(),
                custom_model=self.custom_model.text().strip()
            )
            self.engine.free_models_only = self.free_only_chk.isChecked()
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
                gemini_model=self.gemini_model.currentText().strip(),
                custom_key=self.custom_key.text().strip(),
                custom_url=self.custom_url.text().strip(),
                custom_model=self.custom_model.text().strip()
            )
            self.engine.free_models_only = self.free_only_chk.isChecked()
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
        self.config["custom_base_url"] = self.custom_url.text().strip()
        self.config["custom_api_key"] = self.custom_key.text().strip()
        self.config["custom_model"] = self.custom_model.text().strip()
        # Collect the unlimited extra custom endpoints from their ＋-added rows.
        extras = []
        for e in self._custom_rows:
            url = e["url"].text().strip()
            key = e["key"].text().strip()
            model = e["model"].text().strip()
            if url and model:
                extras.append({"name": model, "base_url": url, "api_key": key, "model": model})
        self.config["custom_apis"] = extras
        self.config["operator_mode"] = self.operator_chk.isChecked()
        self.config["free_models_only"] = self.free_only_chk.isChecked()
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
            role_label.setStyleSheet(f"color: {ACCENT_CYAN}; font-weight: bold;")
            bubble_box.setStyleSheet(
                "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                "stop:0 #221a4d, stop:1 #171232); border: 1px solid #332a66; border-radius: 14px; }"
            )
            bubble_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            main_h_layout.addStretch(1)
            main_h_layout.addWidget(bubble_box, 3)
        elif role == "assistant":
            role_label.setText("🐉 Kali-AI Agent")
            role_label.setStyleSheet(f"color: {ACCENT_GREEN}; font-weight: bold;")
            bubble_box.setStyleSheet(
                f"QFrame {{ background-color: {BG_CARD}; border: 1px solid {BORDER_COLOR}; "
                f"border-left: 2px solid {ACCENT_BLUE}; border-radius: 12px; }}"
            )
            bubble_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            main_h_layout.addWidget(bubble_box, 1)
        else: # system
            role_label.setText("⚡ Execution Notice")
            role_label.setStyleSheet(f"color: {ACCENT_AMBER}; font-weight: bold;")
            bubble_box.setStyleSheet(
                f"QFrame {{ background-color: rgba(245, 177, 76, 0.06); border: 1px solid rgba(245, 177, 76, 0.25); "
                f"border-left: 2px solid {ACCENT_AMBER}; border-radius: 10px; }}"
            )
            bubble_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            main_h_layout.addWidget(bubble_box, 1)
            
        header_layout.addWidget(role_label)
        
        if role == "assistant" and confidence_score is not None:
            conf_badge = QLabel(f"🎯 {confidence_score}%")
            conf_badge.setStyleSheet(
                f"background: rgba(124, 92, 255, 0.14); border: 1px solid rgba(124, 92, 255, 0.4); "
                f"color: #b7a6ff; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700;"
            )
            header_layout.addWidget(conf_badge)
            
            risk_color = ACCENT_GREEN if impact_risk == "Low" else (ACCENT_AMBER if impact_risk == "Medium" else ACCENT_RED)
            risk_badge = QLabel(f"🛡️ {impact_risk or 'Low'}")
            risk_badge.setStyleSheet(
                f"background: rgba(255, 255, 255, 0.04); border: 1px solid {risk_color}; "
                f"color: {risk_color}; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700;"
            )
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
            options_box.setStyleSheet(f"background: rgba(255,255,255,0.02); border: 1px solid {BORDER_COLOR}; border-radius: 10px; margin-top: 6px; padding: 6px;")
            opt_layout = QVBoxLayout(options_box)
            opt_layout.setContentsMargins(6, 6, 6, 6)
            opt_layout.setSpacing(6)
            
            opt_title = QLabel("👉 Select an Option to proceed:")
            opt_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {ACCENT_AMBER};")
            opt_layout.addWidget(opt_title)
            
            for opt_text in options:
                btn_opt = QPushButton(f"⚡ {opt_text}")
                btn_opt.setStyleSheet(
                    f"QPushButton {{ background: rgba(124, 92, 255, 0.08); color: #c4b8ff; "
                    f"border: 1px solid rgba(124, 92, 255, 0.3); border-radius: 8px; padding: 8px 11px; "
                    f"font-size: 11px; text-align: left; font-weight: 600; }}"
                    f"QPushButton:hover {{ background: rgba(124, 92, 255, 0.18); border-color: {ACCENT_BLUE}; color: #ffffff; }}"
                )
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


# ── Audit Log Viewer ────────────────────────────────────────────────────────────
class AuditLogDialog(QDialog):
    """Read-only viewer for the command audit trail (~/.config/kali-ai/audit.log)."""
    _LOG_PATH = os.path.join(os.path.expanduser("~"), ".config", "kali-ai", "audit.log")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📜 Command Audit Log")
        self.setMinimumSize(640, 460)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("📜 Command Audit Log")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title)

        sub = QLabel(f"Every executed and blocked command, recorded at:\n{self._LOG_PATH}")
        sub.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setStyleSheet(
            f"QPlainTextEdit {{ background-color: #04070c; border: 1px solid {BORDER_COLOR}; "
            f"border-radius: 8px; padding: 8px; font-family: Consolas, monospace; "
            f"font-size: 11px; color: #9fb4c9; }}"
        )
        layout.addWidget(self.view)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._load)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._load()

    def _load(self):
        try:
            with open(self._LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # Show the most recent entries last; cap to the last ~1000 lines.
            lines = content.splitlines()
            if len(lines) > 1000:
                lines = ["[... older entries truncated ...]"] + lines[-1000:]
            self.view.setPlainText("\n".join(lines) if lines else "(audit log is empty)")
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        except FileNotFoundError:
            self.view.setPlainText("(no audit log yet — run a command first)")
        except Exception as exc:
            self.view.setPlainText(f"(could not read audit log: {exc})")


# ── Learned-Memory Viewer ──────────────────────────────────────────────────────
class MemoryDialog(QDialog):
    """Shows what the agent has learned, with an option to reset it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 Agent Memory & Self-Learning")
        self.setMinimumSize(620, 480)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("🧠 Agent Memory & Self-Learning")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        layout.addWidget(title)

        sub = QLabel("Corrections, preferences, tool success rates and workflows the agent "
                     "has learned. This is injected into every prompt so it keeps improving.")
        sub.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setStyleSheet(
            f"QPlainTextEdit {{ background-color: #0d131f; border: 1px solid {BORDER_COLOR}; "
            f"border-radius: 8px; padding: 10px; font-family: Consolas, monospace; "
            f"font-size: 11px; color: #9fd0b0; }}"
        )
        layout.addWidget(self.view)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._load)
        btn_reset = QPushButton("🗑 Reset Memory")
        btn_reset.setStyleSheet(f"background: #261616; color: {ACCENT_RED}; border-color: #4d2222;")
        btn_reset.clicked.connect(self._reset)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._load()

    def _load(self):
        try:
            self.view.setPlainText(memory.get_memory_summary_for_ai().strip() or "(nothing learned yet)")
        except Exception as exc:
            self.view.setPlainText(f"(could not read memory: {exc})")

    def _reset(self):
        confirm = QMessageBox.question(
            self, "Reset Memory",
            "Erase ALL learned corrections, preferences, tool stats and workflows?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                memory.reset_memory()
            except Exception:
                pass
            self._load()


# ── Background Jobs Panel ───────────────────────────────────────────────────────
class JobsDialog(QDialog):
    """Live view of background jobs with per-job output & stop controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ Background Jobs")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(STYLE + f"\nQDialog {{ background-color: {BG_SIDEBAR}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("⚙ Background Jobs")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        header.addWidget(title)
        header.addStretch()
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._refresh)
        header.addWidget(btn_refresh)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Status", "Age(s)", "Command", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: #0c121e; border: 1px solid {BORDER_COLOR}; "
            f"gridline-color: #1e293b; border-radius: 8px; color: #f8fafc; }}"
            f"QHeaderView::section {{ background-color: #101622; color: #94a3b8; font-weight: bold; "
            f"font-size: 11px; border: 1px solid #1e293b; padding: 6px; }}"
        )
        layout.addWidget(self.table, stretch=2)

        out_lbl = QLabel("Selected job output:")
        out_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        layout.addWidget(out_lbl)

        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setStyleSheet(
            f"QPlainTextEdit {{ background-color: #04070c; border: 1px solid #1a2333; border-radius: 8px; "
            f"padding: 8px; font-family: Consolas, monospace; font-size: 11px; color: #4ade80; }}"
        )
        layout.addWidget(self.output_view, stretch=1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_close)
        layout.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _refresh(self):
        jobs = get_job_manager().snapshot()
        self.table.setRowCount(0)
        for idx, job in enumerate(jobs):
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(f"#{job['id']}"))
            status_item = QTableWidgetItem(job["status"])
            status_item.setForeground(QColor(ACCENT_BLUE if job["status"] == "running" else TEXT_MUTED))
            self.table.setItem(idx, 1, status_item)
            self.table.setItem(idx, 2, QTableWidgetItem(str(job["duration"])))
            self.table.setItem(idx, 3, QTableWidgetItem(job["command"]))

            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(2, 2, 2, 2)
            cl.setSpacing(4)
            btn_out = QPushButton("📄 Output")
            btn_out.setStyleSheet("font-size: 10px; padding: 2px 6px; background: #1a273d; color: #60a5fa;")
            btn_out.clicked.connect(lambda _c=False, jid=job["id"]: self._show_output(jid))
            cl.addWidget(btn_out)
            if job["status"] == "running":
                btn_stop = QPushButton("⏹ Stop")
                btn_stop.setStyleSheet(f"font-size: 10px; padding: 2px 6px; background: #261616; color: {ACCENT_RED};")
                btn_stop.clicked.connect(lambda _c=False, jid=job["id"]: self._stop(jid))
                cl.addWidget(btn_stop)
            self.table.setCellWidget(idx, 4, cell)

        if not jobs:
            self.output_view.setPlainText("(no background jobs)")

    def _show_output(self, jid: int):
        self.output_view.setPlainText(get_job_manager().output(jid))
        self.output_view.verticalScrollBar().setValue(self.output_view.verticalScrollBar().maximum())

    def _stop(self, jid: int):
        get_job_manager().stop(jid)
        self._refresh()

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()


# ── Main Application Window ─────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kali-AI Agent by Om | Advanced Security Controller v3.0")
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
        self._auto_turn_count = 0      # consecutive autonomous turns in current task
        self._auto_turn_limit = 25     # safety cap to stop runaway AI->command loops
        self._stop_requested = False
        self._last_user_text = ""      # last real user request (for memory learning)
        self._awaiting_input = False   # a running command is paused at an interactive prompt
        self._skip_ai_followup = False # suppress the AI loop after a manual user command
        self._pending_cmd_timeout = None  # AI-requested timeout for the next command
        self._vision_control = False   # Live Screen Control: watch screen + auto GUI control
        self._normal_turn_limit = 25   # autonomous cap outside vision mode
        self._model_provider = {}      # model_id -> provider (for dropdown routing)
        self._custom_creds = {}        # model_id -> (key, url, model) for extra custom endpoints
        self._first_selectable_idx = None
        self.cmd_worker = None
        
        config = load_config()
        self.font_size = config.get("font_size", 13)
        global CURRENT_FONT_SIZE
        CURRENT_FONT_SIZE = self.font_size
        
        self._setup_ui()
        self._load_history_from_disk()
        self._try_init_engine()

        # Live background-jobs indicator in the top bar.
        self._jobs_timer = QTimer(self)
        self._jobs_timer.setInterval(2500)
        self._jobs_timer.timeout.connect(self._update_jobs_indicator)
        self._jobs_timer.start()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ── LEFT SIDEBAR ────────────────────────────────────────────────────────
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(230)
        self.sidebar.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 #11122a, stop:0.4 {BG_SIDEBAR}, stop:1 #0b0c16); "
            f"border-right: 1px solid {BORDER_COLOR}; }}"
        )
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
        
        self.btn_new_chat = QPushButton("＋  New Conversation")
        self.btn_new_chat.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_CYAN});
                color: #0a0b14;
                font-weight: 800;
                font-size: 12px;
                padding: 9px;
                border: none;
                border-radius: 10px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8f72ff, stop:1 #4de2f5);
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

        self.btn_audit = QPushButton("📜 Audit Log")
        self.btn_audit.setToolTip("View the trail of every executed/blocked command")
        self.btn_audit.clicked.connect(self._open_audit_log)

        self.btn_memory = QPushButton("🧠 Agent Memory")
        self.btn_memory.setToolTip("View / reset what the agent has learned")
        self.btn_memory.clicked.connect(self._open_memory)

        self.btn_ghidra = QPushButton("🧬 Connect Ghidra")
        self.btn_ghidra.setToolTip("One-click: connect the agent to Ghidra for reverse engineering")
        self.btn_ghidra.clicked.connect(self._connect_ghidra)
        
        sidebar_layout.addWidget(self.btn_settings)
        sidebar_layout.addWidget(self.btn_plugins)
        sidebar_layout.addWidget(self.btn_target_scope)
        sidebar_layout.addWidget(self.btn_ghidra)
        sidebar_layout.addWidget(self.btn_audit)
        sidebar_layout.addWidget(self.btn_memory)
        sidebar_layout.addWidget(self.btn_clear)
        sidebar_layout.addWidget(self.btn_export)
        
        options_lbl = QLabel("OPTIONS")
        options_lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-weight: bold; letter-spacing: 1px; margin-top: 4px;")
        sidebar_layout.addWidget(options_lbl)
        
        _chk_style = f"QCheckBox {{ color: {TEXT_MUTED}; font-size: 11px; }} QCheckBox::indicator {{ width: 13px; height: 13px; border-radius: 3px; border: 1px solid {BORDER_COLOR}; background: #0d131f; }} QCheckBox::indicator:checked {{ background: {ACCENT_BLUE}; border-color: {ACCENT_BLUE}; }}"

        self.chk_screenshot = QCheckBox("Auto Vision Screenshot")
        self.chk_screenshot.setChecked(False)
        self.chk_screenshot.setStyleSheet(_chk_style)
        sidebar_layout.addWidget(self.chk_screenshot)

        self.chk_autorun = QCheckBox("⚡ Auto-run safe commands")
        self.chk_autorun.setChecked(False)
        self.chk_autorun.setToolTip(
            "When ON, read-only/safe commands run automatically.\n"
            "Destructive or impactful commands (rm, dd, kill, firewall, user mgmt, ...) "
            "still require your approval."
        )
        self.chk_autorun.setStyleSheet(_chk_style)
        sidebar_layout.addWidget(self.chk_autorun)

        self.chk_vision = QCheckBox("🖥 Live Screen Control")
        self.chk_vision.setChecked(False)
        self.chk_vision.setToolTip(
            "When ON, the agent sees the live screen each step and controls the mouse & keyboard\n"
            "itself (no per-click approval) to complete the task you give it. Click Stop (🟥) to halt."
        )
        self.chk_vision.setStyleSheet(_chk_style)
        self.chk_vision.toggled.connect(self._toggle_vision_control)
        sidebar_layout.addWidget(self.chk_vision)
        
        sidebar_layout.addStretch()
        
        status_box = QFrame()
        status_box.setStyleSheet(f"background: #0a0f18; border: 1px solid {BORDER_COLOR}; border-radius: 7px; padding: 6px;")
        sb_layout = QVBoxLayout(status_box)
        sb_layout.setContentsMargins(6, 6, 6, 6)
        
        self.status_lbl = QLabel("● Disconnected")
        self.status_lbl.setStyleSheet(f"color: {ACCENT_RED}; font-size: 11px; font-weight: 600;")
        sb_layout.addWidget(self.status_lbl)
        
        version_lbl = QLabel("v3.0 Advanced Engine")
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
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 #12132290, stop:1 {BG_DARK}); "
            f"border-bottom: 1px solid rgba(124, 92, 255, 0.30); }}"
        )
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
        
        # Effort / thinking-power selector
        self.effort_combo = QComboBox()
        self.effort_combo.addItems(["⚡ Fast", "⚖ Balanced", "🧠 Deep"])
        self.effort_combo.setToolTip("Thinking effort — Fast: quick & concise · Balanced · Deep: max reasoning & accuracy")
        self.effort_combo.setStyleSheet(
            f"QComboBox {{ background: #0b111c; border: 1px solid #1e293b; border-radius: 8px; "
            f"padding: 3px 8px; font-size: 11px; color: {ACCENT_CYAN}; font-weight: 600; }}"
            f"QComboBox::drop-down {{ border: none; width: 14px; }}"
        )
        _eff_map = {"fast": "⚡ Fast", "balanced": "⚖ Balanced", "deep": "🧠 Deep"}
        self.effort_combo.setCurrentText(_eff_map.get(load_config().get("effort_level", "balanced"), "⚖ Balanced"))
        self.effort_combo.currentTextChanged.connect(self._on_effort_changed)
        tb_layout.addWidget(self.effort_combo)

        # Feature 4 Header Toggle Button: Inventory Dashboard
        self.btn_toggle_inventory = QPushButton("📊 Target Inventory")
        self.btn_toggle_inventory.setStyleSheet(f"font-size: 11px; padding: 3px 8px; background: #172030; color: {ACCENT_AMBER};")
        self.btn_toggle_inventory.clicked.connect(self._toggle_inventory_view)
        tb_layout.addWidget(self.btn_toggle_inventory)
        
        self.btn_jobs = QPushButton("⚙ Jobs")
        self.btn_jobs.setToolTip("View & control background jobs")
        self.btn_jobs.setStyleSheet(f"font-size: 11px; padding: 3px 8px; background: #172030; color: {TEXT_MUTED};")
        self.btn_jobs.clicked.connect(self._open_jobs)
        tb_layout.addWidget(self.btn_jobs)

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
        self._input_card_style = f"""
            QFrame {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER_COLOR};
                border-radius: 20px;
                padding: 2px 4px;
            }}
            QFrame:focus-within {{
                border-color: {ACCENT_BLUE};
            }}
        """
        self._input_card_style_awaiting = f"""
            QFrame {{
                background-color: #1c1708;
                border: 1px solid {ACCENT_AMBER};
                border-radius: 18px;
                padding: 2px 4px;
            }}
        """
        self.input_card.setStyleSheet(self._input_card_style)
        
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
        self.model_selector.currentIndexChanged.connect(self._on_dashboard_model_changed)
        
        self.btn_send = QPushButton("▶")
        self.btn_send.setFixedSize(32, 32)
        self.btn_send.setToolTip("Send Message")
        self.btn_send.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_BLUE}, stop:1 {ACCENT_CYAN}); "
            f"color: #0a0b14; font-weight: bold; border-radius: 16px; font-size: 12px; border: none; }}"
            f"QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8f72ff, stop:1 #4de2f5); }}"
        )
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

        self.cwd_label = QLabel("📂 ~")
        self.cwd_label.setToolTip("Current working directory of the persistent shell")
        self.cwd_label.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; font-family: Consolas, monospace;")

        self.btn_reset_shell = QPushButton("⟳ Reset Shell")
        self.btn_reset_shell.setToolTip("Restart the persistent shell (clears cwd/env/state)")
        self.btn_reset_shell.setStyleSheet(f"font-size: 10px; padding: 2px 6px; background: #121927; color: {ACCENT_AMBER};")
        self.btn_reset_shell.clicked.connect(self._reset_shell)

        self.btn_clear_term = QPushButton("Clear")
        self.btn_clear_term.setStyleSheet("font-size: 10px; padding: 2px 6px; background: #121927;")
        self.btn_clear_term.clicked.connect(self._clear_terminal_output)
        
        term_header.addWidget(term_title)
        term_header.addSpacing(8)
        term_header.addWidget(self.cwd_label)
        term_header.addStretch()
        term_header.addWidget(self.btn_reset_shell)
        term_header.addWidget(self.btn_clear_term)
        term_layout.addLayout(term_header)
        
        self.terminal_log = QPlainTextEdit()
        self.terminal_log.setReadOnly(True)
        self.terminal_log.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #05060e;
                border: 1px solid {BORDER_COLOR};
                border-radius: 10px;
                padding: 10px;
                font-family: Consolas, monospace;
                font-size: 11px;
                color: #5eead4;
                line-height: 1.45;
            }}
        """)
        self.terminal_log.appendPlainText("[*] Kali-AI Terminal Window Active.\n[*] Output streams here live. You can also type commands below to run them directly.\n")
        term_layout.addWidget(self.terminal_log)

        # Manual command input — runs directly in the SAME persistent shell the AI uses.
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("$ run a command directly (bypasses AI)…")
        self.manual_input.setStyleSheet(
            f"QLineEdit {{ background-color: #04070c; border: 1px solid #1a2333; border-radius: 6px; "
            f"padding: 6px 8px; font-family: Consolas, monospace; font-size: 11px; color: #4ade80; }}"
            f"QLineEdit:focus {{ border-color: {ACCENT_GREEN}; }}"
        )
        self.manual_input.returnPressed.connect(self._on_manual_command)
        term_layout.addWidget(self.manual_input)

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

    def _apply_awaiting_style(self):
        self.input_card.setStyleSheet(self._input_card_style_awaiting)
        self.input_field.setPlaceholderText("⌨️ Process is waiting — type your answer and press Enter…")

    def _clear_awaiting_style(self):
        self.input_card.setStyleSheet(self._input_card_style)

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
        """Immediately abort active AI thread, cancel the running command, and unlock UI."""
        self._stop_requested = True
        self._auto_turn_count = self._auto_turn_limit + 1  # break the autonomous loop
        self._awaiting_input = False
        self._skip_ai_followup = False
        self._clear_awaiting_style()

        # Ctrl-C the currently running foreground command (shell stays alive).
        try:
            get_shell().interrupt()
        except Exception:
            pass

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

    def _on_manual_command(self):
        """Run a command the user typed directly in the terminal panel's input."""
        cmd = self.manual_input.text().strip()
        if not cmd:
            return
        self.manual_input.clear()

        # If a process is paused for input, route the text to it instead of running anew.
        if self._awaiting_input:
            self._awaiting_input = False
            self._clear_awaiting_style()
            self._add_bubble("user", f"⌨️ → process: {cmd}")
            self._run_send_input(cmd)
            return
        if self._is_busy:
            self.terminal_log.appendPlainText("\n[BUSY] Wait for the current action to finish.\n")
            return

        self.terminal_log.appendPlainText(f"\n$ {cmd}")
        self._execute_command(cmd, manual=True, timeout=None)

    def _reset_shell(self):
        """Restart the persistent shell, clearing cwd/env/running state."""
        try:
            get_shell().restart()
        except Exception as exc:
            self.terminal_log.appendPlainText(f"\n[SHELL RESET FAILED] {exc}\n")
            return
        self._awaiting_input = False
        self._skip_ai_followup = False
        self._clear_awaiting_style()
        self.terminal_log.appendPlainText("\n[SHELL RESET] Fresh persistent shell started (cwd/env/state cleared).\n")
        self.cwd_label.setText("📂 ~")
        self._set_busy_state(False)

    def _try_init_engine(self):
        config = load_config()
        provider = config.get("provider", "gemini")

        has_gem = bool(config.get("gemini_api_key"))
        has_oai = bool(config.get("openai_api_key"))
        has_cus = bool(config.get("custom_api_key") or config.get("custom_base_url"))
        # If the chosen primary provider has no key but another does, fall back to it
        # so the app starts whenever ANY provider is configured.
        if provider == "gemini" and not has_gem:
            provider = "openai" if has_oai else ("custom" if has_cus else provider)
        elif provider == "openai" and not has_oai:
            provider = "gemini" if has_gem else ("custom" if has_cus else provider)
        elif provider == "custom" and not has_cus:
            provider = "gemini" if has_gem else ("openai" if has_oai else provider)
        has_key = ((provider == "gemini" and has_gem) or (provider == "openai" and has_oai)
                   or (provider == "custom" and has_cus))

        if has_key:
            try:
                self.engine = AIEngine(
                    provider=provider,
                    openai_key=config.get("openai_api_key", ""),
                    openai_url=config.get("openai_base_url", "https://openrouter.ai/api/v1"),
                    openai_model=config.get("openai_model", "openai/gpt-4o"),
                    gemini_key=config.get("gemini_api_key", ""),
                    gemini_model=config.get("gemini_model", "gemini-2.0-flash"),
                    custom_key=config.get("custom_api_key", ""),
                    custom_url=config.get("custom_base_url", ""),
                    custom_model=config.get("custom_model", "")
                )
                model_name = config.get(f"{provider}_model", "unknown")
                self.status_lbl.setText(f"● {provider.upper()} | Active")
                self.status_lbl.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: 600;")
                
                self.model_selector.blockSignals(True)
                if self.model_selector.findText(model_name) == -1:
                    self.model_selector.addItem(model_name)
                self.model_selector.setCurrentText(model_name)
                self.model_selector.blockSignals(False)
                
                self.engine.free_models_only = config.get("free_models_only", False)
                self.engine.effort = config.get("effort_level", "balanced")
                # Dashboard dropdown lists models from ALL configured providers (tagged).
                self.fetch_worker = ModelFetchWorker(self.engine, tagged=True)
                self.fetch_worker.models_map_ready.connect(self._on_dashboard_models_map_ready)
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

    def _on_dashboard_models_map_ready(self, by_provider: dict):
        """Populate the model dropdown GROUPED by provider, so it's clear which API each
        model belongs to. Group headers are non-selectable; real model id is stored as itemData."""
        self._model_provider = {}
        self._custom_creds = {}  # model_id -> (key, url, model) for extra custom endpoints
        cfg = load_config()

        gem = list(by_provider.get("gemini", []))
        oai = list(by_provider.get("openai", []))
        cus = list(by_provider.get("custom", []))
        for m in gem:
            self._model_provider[m] = "gemini"
        for m in oai:
            self._model_provider[m] = "openai"
        for m in cus:
            self._model_provider[m] = "custom"
        # Unlimited extra custom endpoints from config.
        extras = []
        for api in cfg.get("custom_apis", []):
            mid = (api.get("model") or "").strip()
            if mid:
                self._model_provider[mid] = "custom"
                self._custom_creds[mid] = (api.get("api_key", ""), api.get("base_url", ""), mid)
                extras.append(mid)

        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        self._first_selectable_idx = None

        def add_group(label, models, icon):
            models = sorted(set(m for m in models if m))
            if not models:
                return
            self.model_selector.addItem(f"────  {label}  ────")
            hidx = self.model_selector.count() - 1
            try:
                self.model_selector.model().item(hidx).setEnabled(False)  # non-selectable header
            except Exception:
                pass
            for m in models:
                self.model_selector.addItem(f"{icon}  {m}")
                i = self.model_selector.count() - 1
                self.model_selector.setItemData(i, m)  # raw model id
                if self._first_selectable_idx is None:
                    self._first_selectable_idx = i

        add_group("Google Gemini", gem, "🔷")
        add_group("OpenRouter / OpenAI", oai, "🟣")
        add_group("Custom APIs", cus + extras, "🟢")

        if self._first_selectable_idx is None:
            self.model_selector.blockSignals(False)
            return

        provider = cfg.get("provider", "gemini")
        cur = cfg.get("custom_model", "") if provider == "custom" else cfg.get(f"{provider}_model", "")
        self._select_model_in_selector(cur)
        self.model_selector.blockSignals(False)

    def _select_model_in_selector(self, model_id: str):
        """Set the dropdown to the item whose stored id matches model_id (or first selectable)."""
        if model_id:
            for i in range(self.model_selector.count()):
                if self.model_selector.itemData(i) == model_id:
                    self.model_selector.setCurrentIndex(i)
                    return
        if getattr(self, "_first_selectable_idx", None) is not None:
            self.model_selector.setCurrentIndex(self._first_selectable_idx)

    def _on_dashboard_model_changed(self, *_args):
        if not self.engine:
            return
        # The real model id is stored as itemData (display text is prefixed/grouped).
        new_model = self.model_selector.currentData()
        if not new_model:  # a group header or empty selection
            return
        # If this model belongs to an extra custom endpoint, point the engine at it.
        creds = getattr(self, "_custom_creds", {}).get(new_model)
        if creds:
            ok, msg = self.engine.set_custom_endpoint(*creds)
        else:
            # Use the remembered provider (custom vs OpenRouter can't be told apart by id alone).
            prov = getattr(self, "_model_provider", {}).get(new_model)
            ok, msg = self.engine.set_active_model(new_model, prov)
        if not ok:
            self._add_bubble("system", f"⚠️ {msg}")
            return
        config = load_config()
        config["provider"] = self.engine.provider
        if self.engine.provider == "gemini":
            config["gemini_model"] = self.engine.gemini_model
        elif self.engine.provider == "custom":
            config["custom_model"] = self.engine.custom_model
        else:
            config["openai_model"] = self.engine.openai_model
        save_config(config)
        self.status_lbl.setText(f"● {self.engine.provider.upper()} | {new_model}")
        self.status_lbl.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: 600;")

    def _apply_model_switch(self, model_id: str):
        """Handle an AI-requested model switch (switch_model field)."""
        if not self.engine or not model_id:
            return
        creds = getattr(self, "_custom_creds", {}).get(model_id)
        if creds:
            ok, msg = self.engine.set_custom_endpoint(*creds)
        else:
            prov = getattr(self, "_model_provider", {}).get(model_id)
            ok, msg = self.engine.set_active_model(model_id, prov)
        if not ok:
            self._add_bubble("system", f"⚠️ Could not switch model: {msg}")
            return
        self.model_selector.blockSignals(True)
        self._select_model_in_selector(model_id)
        self.model_selector.blockSignals(False)
        config = load_config()
        config["provider"] = self.engine.provider
        if self.engine.provider == "gemini":
            config["gemini_model"] = self.engine.gemini_model
        elif self.engine.provider == "custom":
            config["custom_model"] = self.engine.custom_model
        else:
            config["openai_model"] = self.engine.openai_model
        save_config(config)
        self.status_lbl.setText(f"● {self.engine.provider.upper()} | {model_id}")
        self.status_lbl.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 11px; font-weight: 600;")
        self._add_bubble("system", f"🔀 Switched to model: **{model_id}** (context preserved).")

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._try_init_engine()

    def _open_plugins_dialog(self):
        dlg = PluginManagerDialog(self)
        dlg.exec()

    def _open_audit_log(self):
        dlg = AuditLogDialog(self)
        dlg.exec()

    def _open_memory(self):
        dlg = MemoryDialog(self)
        dlg.exec()

    def _open_jobs(self):
        dlg = JobsDialog(self)
        dlg.exec()

    def _on_effort_changed(self, text: str):
        level = "fast" if "Fast" in text else ("deep" if "Deep" in text else "balanced")
        cfg = load_config()
        cfg["effort_level"] = level
        save_config(cfg)
        if self.engine:
            self.engine.effort = level
        self.status_lbl.setText(f"● Effort: {level}")
        self.status_lbl.setStyleSheet(f"color: {ACCENT_CYAN}; font-size: 11px; font-weight: 600;")

    def _toggle_vision_control(self, on: bool):
        """Enable/disable Live Screen Control (continuous vision + autonomous mouse/keyboard)."""
        self._vision_control = on
        if on:
            self.chk_screenshot.setChecked(True)      # vision mode needs screenshots
            self._auto_turn_limit = 80                # GUI tasks need many steps
            if self.engine:
                self.engine.screenshot_detail = "high"
            w, h = get_screen_size()
            self._add_bubble(
                "system",
                f"🖥 **Live Screen Control ON.** I can now see the live screen ({w}×{h}) and will move the "
                f"mouse & type myself (no per-click approval) to do what you ask. Give me a task; press 🟥 Stop to halt.",
            )
        else:
            self._auto_turn_limit = self._normal_turn_limit
            if self.engine:
                self.engine.screenshot_detail = "low"
            self._add_bubble("system", "🖥 Live Screen Control OFF — back to normal (GUI actions need approval).")

    def _vision_preamble(self) -> str:
        w, h = get_screen_size()
        return (
            f"[LIVE SCREEN CONTROL] The attached image is the CURRENT screen. The screen is {w}x{h} pixels; "
            f"any GUI coordinates you give MUST be absolute pixels within this space. Look at the screen, then "
            f"choose the single next GUI action (action_type 'gui' with gui_action type click/doubleclick/"
            f"rightclick/type/hotkey/scroll and x,y/text) to progress the task — or 'bash' if a shell command is "
            f"better. When the task is fully complete, reply action_type 'chat' with task_complete=true.\n\n"
        )

    def _update_jobs_indicator(self):
        try:
            n = get_job_manager().running_count()
        except Exception:
            n = 0
        if n > 0:
            self.btn_jobs.setText(f"⚙ Jobs ({n})")
            self.btn_jobs.setStyleSheet(
                f"font-size: 11px; padding: 3px 8px; background: #172030; color: {ACCENT_GREEN}; font-weight: bold;"
            )
        else:
            self.btn_jobs.setText("⚙ Jobs")
            self.btn_jobs.setStyleSheet(
                f"font-size: 11px; padding: 3px 8px; background: #172030; color: {TEXT_MUTED};"
            )

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

        # If a running command is paused at an interactive prompt, the user's text
        # goes straight to that process (same persistent shell), not to the AI.
        if self._awaiting_input and text:
            self._awaiting_input = False
            self._clear_awaiting_style()
            self._add_bubble("user", f"⌨️ → process: {text}")
            self._run_send_input(text)
            return

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
        # Fresh user task: reset the autonomous-loop guard and stop flag.
        self._auto_turn_count = 0
        self._stop_requested = False
        self._last_user_text = text
        self._set_busy_state(True)
        
        images_to_send = self._attached_images.copy() if has_images else None
        worker_text = (self._vision_preamble() + text) if self._vision_control else text

        self.worker = AIWorker(
            engine=self.engine,
            user_text=worker_text,
            attach_screenshot=self.chk_screenshot.isChecked() or self._vision_control,
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

        # Apply an AI-requested model switch (takes effect from the next turn).
        if res.get("switch_model"):
            self._apply_model_switch(res["switch_model"])

        # Persist any durable lessons the model reasoned out this turn.
        try:
            if res.get("learned_correction"):
                memory.add_learned_correction(res["learned_correction"])
            if res.get("learned_preference"):
                memory.add_learned_preference(res["learned_preference"])
            if res.get("finding"):
                memory.record_finding(res["finding"])
        except Exception:
            pass

        # Model signals the overall goal is finished → end the autonomous loop.
        if bool(res.get("task_complete", False)):
            self._stop_requested = True
            try:
                memory.increment_task_completed()
                if res.get("workflow_summary"):
                    memory.record_workflow(self._last_user_text, res["workflow_summary"])
            except Exception:
                pass

        if action_type == "bash" and command:
            self._pending_cmd_timeout = res.get("timeout")  # AI-requested per-command timeout
            tier, reason = classify_command(command)
            if tier == "auto" and self.chk_autorun.isChecked():
                # Safe/read-only command + auto-run mode → execute without a manual click.
                self.terminal_log.appendPlainText(f"\n[AUTO-RUN] safe command")
                self._execute_command(command, timeout=self._pending_cmd_timeout)
            else:
                if tier == "confirm":
                    self.terminal_log.appendPlainText(f"\n[APPROVAL NEEDED] {reason}")
                self._add_intercept(command)
                self._set_busy_state(False)
        elif action_type == "send_input":
            self._run_send_input(res.get("input_text", ""))
        elif action_type == "read_file":
            self._run_read_file(res.get("file_path", ""))
        elif action_type == "write_file":
            self._run_write_file(
                res.get("file_path", ""), res.get("file_content", ""), bool(res.get("file_append", False))
            )
        elif action_type == "job":
            self._run_job_action(res.get("job_action", ""), res.get("command", ""), res.get("job_id"))
        elif action_type == "ghidra":
            self._run_ghidra_action(
                res.get("ghidra_action", ""), res.get("file_path", ""),
                res.get("function", ""), res.get("script_code", ""),
            )
        elif action_type == "gui" and gui_action:
            if self._vision_control:
                # Live Screen Control: act autonomously (no per-click approval).
                self.terminal_log.appendPlainText(
                    f"\n[VISION] {gui_action.get('type', '?')} @ ({gui_action.get('x', 0)},{gui_action.get('y', 0)}) {gui_action.get('text', '')}".rstrip()
                )
                exec_res = run_gui_action(gui_action)
                self._handle_execution_result(exec_res, command_text=f"GUI:{gui_action}")
            else:
                self._add_gui_intercept(gui_action)
                self._set_busy_state(False)
        else:
            self._set_busy_state(False)

    def _run_send_input(self, input_text: str):
        """Send text to a command currently paused at an interactive prompt."""
        self.terminal_log.appendPlainText(f"\n[SEND INPUT] {input_text!r}")
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())
        self._set_busy_state(True)
        self.cmd_worker = CommandWorker(lambda cb, t=input_text: resume_bash(t, on_output=cb))
        self.cmd_worker.output_chunk.connect(self._on_cmd_output_chunk)
        self.cmd_worker.finished_result.connect(
            lambda res: self._handle_execution_result(res, command_text="send_input", echo_output=False)
        )
        self.cmd_worker.start()

    def _run_read_file(self, path: str):
        if not path:
            self._set_busy_state(False)
            return
        self.terminal_log.appendPlainText(f"\n[READ FILE] {path}")
        ok, content = tools.read_file(path)
        res = ExecutionResult(
            success=ok, stdout=content if ok else "", stderr="" if ok else content,
            exit_code=0 if ok else 1,
        )
        self._handle_execution_result(res, command_text=f"read_file:{path}")

    def _run_write_file(self, path: str, content: str, append: bool):
        if not path:
            self._set_busy_state(False)
            return
        self.terminal_log.appendPlainText(f"\n[WRITE FILE] {path} ({len(content)} bytes, append={append})")
        ok, msg = tools.write_file(path, content, append=append)
        res = ExecutionResult(
            success=ok, stdout=msg if ok else "", stderr="" if ok else msg,
            exit_code=0 if ok else 1,
        )
        self._handle_execution_result(res, command_text=f"write_file:{path}")

    def _run_job_action(self, job_action: str, command: str, job_id):
        """Manage background jobs (start/list/output/stop) and feed the result to the loop."""
        jm = get_job_manager()
        job_action = (job_action or "").lower()
        ok, out = True, ""

        if job_action == "start":
            if not command:
                ok, out = False, "job start requires a command."
            else:
                ok, msg, jid = jm.start(command)
                out = msg
                if ok:
                    self.terminal_log.appendPlainText(f"\n[JOB STARTED] #{jid}: {command}")
        elif job_action == "list":
            out = jm.list_jobs()
        elif job_action == "output":
            if job_id is None:
                ok, out = False, "job output requires a job_id."
            else:
                out = jm.output(int(job_id))
        elif job_action == "stop":
            if job_id is None:
                ok, out = False, "job stop requires a job_id."
            else:
                ok, out = jm.stop(int(job_id))
        else:
            ok, out = False, f"Unknown job_action: {job_action!r} (use start/list/output/stop)."

        res = ExecutionResult(success=ok, stdout=out if ok else "", stderr="" if ok else out,
                              exit_code=0 if ok else 1)
        self._handle_execution_result(res, command_text=f"job:{job_action}")

    def _run_ghidra_action(self, ghidra_action: str, file_path: str, function: str, script_code: str):
        """Drive Ghidra headless for reverse engineering; runs off-thread (analysis is slow)."""
        g = get_ghidra()
        ga = (ghidra_action or "").lower()
        label = file_path or function or ""
        self.terminal_log.appendPlainText(f"\n[GHIDRA] {ga} {label}".rstrip())
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())
        self._set_busy_state(True)

        def work(_cb):
            if ga == "connect":
                ok, out = g.connect()
            elif ga == "status":
                ok, out = True, g.status()
            elif ga == "analyze":
                ok, out = g.analyze(file_path)
            elif ga == "functions":
                ok, out = g.list_functions()
            elif ga == "strings":
                ok, out = g.list_strings()
            elif ga == "decompile":
                ok, out = g.decompile(function)
            elif ga == "script":
                ok, out = g.run_custom_script(script_code)
            else:
                ok, out = False, f"Unknown ghidra_action: {ga!r} (use connect/analyze/functions/strings/decompile/script/status)."
            return ExecutionResult(success=ok, stdout=out if ok else "", stderr="" if ok else out,
                                   exit_code=0 if ok else 1)

        self.cmd_worker = CommandWorker(lambda cb: work(cb))
        self.cmd_worker.finished_result.connect(
            lambda res: self._handle_execution_result(res, command_text=f"ghidra:{ga}", echo_output=True)
        )
        self.cmd_worker.start()

    def _connect_ghidra(self):
        """One-click: locate Ghidra and report readiness (no AI turn)."""
        ok, msg = get_ghidra().connect()
        self.terminal_log.appendPlainText(f"\n[GHIDRA] {msg}\n")
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())
        self._add_bubble("system", ("🧬 **Ghidra connected.** " + msg) if ok else ("⚠️ " + msg))
        if ok:
            self.btn_ghidra.setText("🧬 Ghidra ✓")
            self.btn_ghidra.setStyleSheet(
                f"QPushButton {{ background: rgba(45, 212, 191, 0.12); color: {ACCENT_GREEN}; "
                f"border: 1px solid {ACCENT_GREEN}; border-radius: 9px; padding: 7px 13px; font-weight: 600; }}"
            )

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

    def _add_gui_intercept(self, gui_action: dict):
        """Require human approval before any pyautogui desktop action, just like bash."""
        desc = (
            f"GUI ACTION: {gui_action.get('type', '?')} "
            f"@ ({gui_action.get('x', 0)}, {gui_action.get('y', 0)})"
        )
        txt = gui_action.get("text", "")
        if txt:
            desc += f"  text={txt!r}"
        banner = InterceptBanner(desc)
        banner.approved.connect(lambda _s=None, g=gui_action: self._on_gui_approved(g))
        banner.cancelled.connect(self._on_command_cancelled)
        count = self.messages_layout.count()
        self.messages_layout.insertWidget(count - 1, banner)
        self._smooth_scroll_to_bottom()

    def _remove_last_intercept_banner(self):
        count = self.messages_layout.count()
        for i in range(count - 2, -1, -1):
            item = self.messages_layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, InterceptBanner):
                widget.setParent(None)
                widget.deleteLater()
                break

    def _on_gui_approved(self, gui_action: dict):
        self._remove_last_intercept_banner()
        self.terminal_log.appendPlainText(f"\n[GUI ACTION] Executing: {gui_action}")
        self._set_busy_state(True)
        exec_res = run_gui_action(gui_action)
        self._handle_execution_result(exec_res, command_text=f"GUI:{gui_action}")

    def _on_command_approved(self, command: str):
        self._remove_last_intercept_banner()
        self._execute_command(command)

    _TIMEOUT_SENTINEL = object()

    def _execute_command(self, command: str, manual: bool = False, timeout=_TIMEOUT_SENTINEL):
        """Run a bash command off the GUI thread with live streaming (shared by
        manual-approval, auto-run, and manual-terminal paths).

        `manual=True` (user typed it in the terminal panel) suppresses the AI
        follow-up loop so the agent doesn't hijack the user's own command.
        `timeout` is seconds (0 = no limit, None = auto); if omitted, the last
        AI-requested per-command timeout is used."""
        if timeout is self._TIMEOUT_SENTINEL:
            timeout = getattr(self, "_pending_cmd_timeout", None)
        self._pending_cmd_timeout = None
        self._skip_ai_followup = manual
        # If the command uses sudo, make sure we have a password cached (asked once/session).
        self._ensure_sudo_password_for(command)

        self.terminal_log.appendPlainText(f"\n$ {command}")
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())

        self._set_busy_state(True)
        # Run OFF the GUI thread so the UI stays responsive and output streams live.
        self.cmd_worker = CommandWorker(lambda cb, c=command, t=timeout: run_bash(c, timeout=t, on_output=cb))
        self.cmd_worker.output_chunk.connect(self._on_cmd_output_chunk)
        self.cmd_worker.finished_result.connect(
            lambda res, c=command: self._handle_execution_result(res, command_text=c, echo_output=False)
        )
        self.cmd_worker.start()

    def _on_cmd_output_chunk(self, chunk: str):
        """Append streamed command output to the terminal panel in real time."""
        self.terminal_log.moveCursor(QTextCursor.MoveOperation.End)
        self.terminal_log.insertPlainText(chunk)
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())

    def _ensure_sudo_password_for(self, command: str):
        """Prompt once per session for a sudo password when a sudo command is run."""
        if not command or not re.search(r"(^|\s|;|&&|\|)sudo(\s|$)", command):
            return
        shell = get_shell()
        if shell.has_sudo_password:
            return
        pw, ok = QInputDialog.getText(
            self,
            "🔐 Sudo Password Required",
            "This command uses sudo. Enter your sudo password.\n"
            "(Kept only in memory for this session — never written to disk.)",
            QLineEdit.EchoMode.Password,
        )
        if ok and pw:
            shell.set_sudo_password(pw)

    def _on_command_cancelled(self):
        self._remove_last_intercept_banner()
        self._add_bubble("system", "Execution paused / command cancelled by user.")
        self.terminal_log.appendPlainText("\n[CANCELLED] Command execution rejected by user.\n")
        self._terminal_output = "User cancelled command execution."
        self._set_busy_state(False)

    def _handle_execution_result(self, exec_res, command_text: str = "", echo_output: bool = True):
        # For streamed bash commands the body already appeared live; only non-streamed
        # results (e.g. GUI actions, blocked commands) echo their full output here.
        if echo_output:
            out = exec_res.combined_output() or "(Command completed with no output)"
            self.terminal_log.appendPlainText(out)

        if exec_res.blocked:
            status_str = "BLOCKED BY GUARDRAILS"
        elif exec_res.timed_out:
            status_str = "TIMED OUT"
        elif exec_res.success:
            status_str = "SUCCESS"
        else:
            status_str = "FAILED"
        code = f" exit {exec_res.exit_code}" if getattr(exec_res, "exit_code", None) is not None else ""

        if exec_res.blocked:
            self.terminal_log.appendPlainText(f"\n[{status_str}] {exec_res.reason}\n" + "─" * 50)
            self._terminal_output = f"Command was blocked by safety guardrails: {exec_res.reason}"
        else:
            self.terminal_log.appendPlainText(f"\n[{status_str}{code}]\n" + "─" * 50)
            self._terminal_output = exec_res.output_for_ai() if hasattr(exec_res, "output_for_ai") else exec_res.combined_output()
        self.terminal_log.verticalScrollBar().setValue(self.terminal_log.verticalScrollBar().maximum())

        # Reflect the persistent shell's current working directory in the UI.
        cwd = getattr(exec_res, "cwd", "")
        if cwd:
            self.cwd_label.setText(f"📂 {cwd}")

        # Interactive prompt: pause and let the USER answer the running process directly.
        if getattr(exec_res, "awaiting_input", False):
            self._awaiting_input = True
            self._add_bubble(
                "system",
                "⏳ **The running command is waiting for input.** Type your response below "
                "and press Enter to send it to the process (or ask me to handle it).",
            )
            self._set_busy_state(False)
            self._apply_awaiting_style()
            return
        self._awaiting_input = False
        self._clear_awaiting_style()

        # Self-learning: record real shell commands (not file/gui/input pseudo-actions).
        if (command_text and not exec_res.blocked
                and not command_text.startswith(("GUI:", "read_file:", "write_file:", "send_input", "job:", "ghidra:"))):
            try:
                memory.learn_from_interaction(self._last_user_text, command_text, exec_res.success)
            except Exception:
                pass

        if self._stop_requested:
            self._set_busy_state(False)
            return

        if self._skip_ai_followup:
            # Manual user command — don't let the AI loop take over.
            self._skip_ai_followup = False
            self._set_busy_state(False)
            return

        if self._is_autonomous and not exec_res.blocked:
            self._auto_turn_count += 1
            if self._auto_turn_count > self._auto_turn_limit:
                self._add_bubble(
                    "system",
                    f"⏹ **Auto-execution limit reached** ({self._auto_turn_limit} steps). "
                    f"Send a message to continue if the task isn't finished.",
                )
                self._set_busy_state(False)
                return
            QTimer.singleShot(400, self._trigger_autonomous_next_turn)
        else:
            self._set_busy_state(False)

    def _trigger_autonomous_next_turn(self):
        if not self.engine or self._stop_requested:
            self._set_busy_state(False)
            return
            
        self._set_busy_state(True)
        
        user_prompt = ""
        if self._pending_steering_notes:
            notes_str = "\n".join(self._pending_steering_notes)
            user_prompt = f"[USER MID-EXECUTION STEERING NOTE]: {notes_str}"
            self._pending_steering_notes.clear()
        if self._vision_control:
            user_prompt = self._vision_preamble() + user_prompt

        self.worker = AIWorker(
            engine=self.engine,
            user_text=user_prompt,
            attach_screenshot=self.chk_screenshot.isChecked() or self._vision_control,
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
        """Save active session to disk and tear down the persistent shell on exit."""
        try:
            self._auto_save_active_session()
        except Exception:
            pass
        try:
            get_shell().close()
        except Exception:
            pass
        try:
            get_job_manager().stop_all()
        except Exception:
            pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
