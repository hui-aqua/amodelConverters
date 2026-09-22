"""Desktop model-to-Blender unified workflow with asynchronous inspection and execution.

Features a 3-column CAD/Simulation layout:
- Column 1: Project inputs, enclosing net selection, and pipeline stage checklist.
- Column 2: Dedicated Stage Configuration Column with comprehensive physical, biological, fluid, and optical parameters.
- Column 3: Build status, real-time log monitor, and execution controls.
"""
from __future__ import annotations

import codecs
import hashlib
from pathlib import Path
import re
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, Qt, QThread, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from sim2blender.core.paths import PROJECT_ROOT
from sim2blender.gui.model_job import PipelineJob, find_blender, inspect_model, executable_path
from sim2blender.io.aquasim.results import inspect_results
from sim2blender.core.timeline import wave_timing


from sim2blender.gui.theme import light_palette
from sim2blender.gui.inspectors import Inspector, ResultsInspector
from sim2blender.gui.config_tabs import ConfigTabsMixin


class MainWindow(QMainWindow, ConfigTabsMixin):
    def __init__(self, settings_path=None):
        super().__init__()
        app = QApplication.instance()
        palette = light_palette()
        if app is not None:
            app.setPalette(palette)
        self.setPalette(palette)
        self.setWindowTitle('Sim2Blender — AquaSim scene builder & physics pipeline')
        self.resize(1380, 890)
        self.setMinimumSize(1120, 720)
        self.settings = QSettings(str(settings_path or PROJECT_ROOT / 'output' / 'gui-settings.ini'), QSettings.Format.IniFormat)
        self.info = None
        self.workers = []
        self.token = 0
        self.results_token = 0
        self.results_info = None
        self.running = False
        self.cancelled = False
        self.last_output = None
        self.last_blender = None
        self.job = None
        self.suggested_output = None
        self.log_file = None
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.pending_line = ''
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.cancel_timer = QTimer(self)
        self.cancel_timer.setSingleShot(True)
        self.cancel_timer.timeout.connect(self.process.kill)
        self.load_timer = QTimer(self)
        self.load_timer.setSingleShot(True)
        self.load_timer.setInterval(400)
        self.load_timer.timeout.connect(self.load_model)
        self.results_timer = QTimer(self)
        self.results_timer.setSingleShot(True)
        self.results_timer.setInterval(400)
        self.results_timer.timeout.connect(self.load_results)

        self._build_ui()
        self._load_saved_settings()
        # Backward compatibility aliases for existing workflows and tests
        self.count = self.fish_count
        self.add_fish = self.opt_schooling
        self.form = self.centralWidget()
        self.workflow = QComboBox()
        self.workflow.addItems(['Model physics', 'Replay results'])
        self.workflow.currentIndexChanged.connect(lambda idx: self.opt_replay.setChecked(idx == 1))
        self.opt_replay.toggled.connect(lambda c: self.workflow.setCurrentIndex(1 if c else 0))

        previous = self.settings.value('model', '')
        if previous:
            self.model.setText(previous)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName('AppRoot')
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(12)

        header = QHBoxLayout()
        title_v = QVBoxLayout()
        title = QLabel('Sim2Blender')
        title.setObjectName('Title')
        title_v.addWidget(title)
        subtitle = QLabel('AquaSim model → animated Blender physics scene with modular simulation stages')
        subtitle.setObjectName('Subtitle')
        title_v.addWidget(subtitle)
        header.addLayout(title_v)
        header.addStretch()
        main_layout.addLayout(header)

        # Main 3-Column Splitter
        self.main_split = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_split, 1)

        # =============================================================
        # COLUMN 1: Project Setup & Pipeline Stages
        # =============================================================
        scroll_col1 = QScrollArea()
        scroll_col1.setWidgetResizable(True)
        scroll_col1.setMinimumWidth(320)
        col1_widget = QWidget()
        col1_layout = QVBoxLayout(col1_widget)
        col1_layout.setContentsMargins(0, 0, 8, 0)
        col1_layout.setSpacing(12)
        scroll_col1.setWidget(col1_widget)
        self.main_split.addWidget(scroll_col1)

        # 1.1 Inputs and Scene
        files = QGroupBox('1   Project Inputs & Output')
        f = QFormLayout(files)
        self.model = QLineEdit()
        self.model.setPlaceholderText('Choose an AquaSim .amodel file')
        f.addRow('Model (.amodel)', self.path_row(self.model, self.browse_model))
        self.output = QLineEdit()
        self.output.setPlaceholderText('Where to save Blender scene (.blend)')
        f.addRow('Save Scene (.blend)', self.path_row(self.output, self.browse_output))
        self.model_summary = QLabel('Select an .amodel to inspect components.')
        self.model_summary.setWordWrap(True)
        f.addRow(self.model_summary)
        col1_layout.addWidget(files)
        self.model.textChanged.connect(self.model_changed)

        # 1.2 Enclosure Net Choice
        self.enclosure = QGroupBox('2   Enclosing Net Selection')
        e = QVBoxLayout(self.enclosure)
        help_label = QLabel('Select cage walls and bottom. Exclude attached flaps & internal sheets.')
        help_label.setWordWrap(True)
        e.addWidget(help_label)
        self.components = QListWidget()
        self.components.setFixedHeight(105)
        self.components.itemChanged.connect(self.selection_changed)
        e.addWidget(self.components)
        self.warning = QLabel('')
        self.warning.setWordWrap(True)
        self.warning.setObjectName('Warning')
        e.addWidget(self.warning)

        # Advanced / Hidden options for Beam and Truss element selection
        self.beam_truss_toggle = QPushButton('Beam & truss elements (advanced) ▸')
        self.beam_truss_toggle.setCheckable(True)
        self.beam_truss_toggle.setStyleSheet('text-align: left; padding: 4px 8px; font-weight: 500; font-size: 11px;')
        e.addWidget(self.beam_truss_toggle)

        self.beam_truss_container = QWidget()
        btc_layout = QVBoxLayout(self.beam_truss_container)
        btc_layout.setContentsMargins(0, 4, 0, 4)
        btc_layout.setSpacing(6)

        # Beam element selection
        beam_header = QHBoxLayout()
        beam_lbl = QLabel('Beam elements:')
        beam_lbl.setStyleSheet('font-weight: 600; font-size: 11px; color: #123e50;')
        beam_header.addWidget(beam_lbl)
        beam_header.addStretch()
        btn_beam_all = QPushButton('All')
        btn_beam_all.setStyleSheet('padding: 1px 6px; font-size: 10px;')
        btn_beam_all.clicked.connect(self.select_all_beams)
        beam_header.addWidget(btn_beam_all)
        btn_beam_none = QPushButton('None')
        btn_beam_none.setStyleSheet('padding: 1px 6px; font-size: 10px;')
        btn_beam_none.clicked.connect(self.select_no_beams)
        beam_header.addWidget(btn_beam_none)
        btc_layout.addLayout(beam_header)

        self.beam_components = QListWidget()
        self.beam_components.setFixedHeight(85)
        self.beam_components.itemChanged.connect(self.selection_changed)
        btc_layout.addWidget(self.beam_components)

        # Truss element selection
        truss_header = QHBoxLayout()
        truss_lbl = QLabel('Truss elements:')
        truss_lbl.setStyleSheet('font-weight: 600; font-size: 11px; color: #123e50;')
        truss_header.addWidget(truss_lbl)
        truss_header.addStretch()
        btn_truss_all = QPushButton('All')
        btn_truss_all.setStyleSheet('padding: 1px 6px; font-size: 10px;')
        btn_truss_all.clicked.connect(self.select_all_trusses)
        truss_header.addWidget(btn_truss_all)
        btn_truss_none = QPushButton('None')
        btn_truss_none.setStyleSheet('padding: 1px 6px; font-size: 10px;')
        btn_truss_none.clicked.connect(self.select_no_trusses)
        truss_header.addWidget(btn_truss_none)
        btc_layout.addLayout(truss_header)

        self.truss_components = QListWidget()
        self.truss_components.setFixedHeight(85)
        self.truss_components.itemChanged.connect(self.selection_changed)
        btc_layout.addWidget(self.truss_components)

        self.beam_truss_container.setVisible(False)
        self.beam_truss_toggle.toggled.connect(self._toggle_beam_truss)
        e.addWidget(self.beam_truss_container)

        self.caps = QCheckBox('Close planar openings (virtual caps)')
        self.caps.setChecked(True)
        self.caps.setToolTip('Adds invisible containment caps; does not add physical net material.')
        self.pins = QCheckBox('Support top rim (cloth physics)')
        self.pins.setChecked(True)
        self.pins.setToolTip('Adds top-rim cloth pins in addition to source fixed supports.')
        e.addWidget(self.caps)
        e.addWidget(self.pins)

        frame_row = QHBoxLayout()
        frame_row.addWidget(QLabel('Base frames:'))
        self.frames = QSpinBox()
        self.frames.setRange(1, 100000)
        self.frames.setValue(120)
        self.frames.valueChanged.connect(self.update_duration)
        frame_row.addWidget(self.frames)
        self.duration = QLabel('5.0s @ 24fps')
        frame_row.addWidget(self.duration)
        frame_row.addStretch()
        e.addLayout(frame_row)
        col1_layout.addWidget(self.enclosure)

        # 1.3 Pipeline Stages Checklist
        stages_group = QGroupBox('3   Pipeline Stages')
        sg = QVBoxLayout(stages_group)
        sg.setSpacing(8)

        self.opt_env = QCheckBox('Ocean water, waves & current')
        self.opt_env.setChecked(True)
        self.opt_replay = QCheckBox('AquaSim results replay')
        self.opt_replay.toggled.connect(self.replay_toggled)
        self.opt_schooling = QCheckBox('Simple fish schooling')
        self.opt_schooling.setChecked(True)
        self.opt_schooling.toggled.connect(lambda _: self.selection_changed())
        self.opt_feed = QCheckBox('Feed animation')
        self.opt_feeding = QCheckBox('Fish feeding interaction')
        self.opt_camera = QCheckBox('Cinematic camera')

        stage_items = [
            (self.opt_env, 0, 'Water surface at Z=0 & calm sea wave/current hydrodynamics'),
            (self.opt_replay, 1, 'Replaces cloth baking with out.txt displacements'),
            (self.opt_schooling, 2, 'Boid fish schooling contained in cage'),
            (self.opt_feed, 3, 'Spreader rotor (30 RPM) & ballistic feed pellets'),
            (self.opt_feeding, 4, 'Coupled schooling & feed pellet consumption'),
            (self.opt_camera, 5, 'Multi-phase cinematic tracking camera'),
        ]

        for cb, tab_idx, hint in stage_items:
            row = QHBoxLayout()
            cb.setStyleSheet('font-weight: 600; color: #123e50;')
            cb.setToolTip(hint)
            row.addWidget(cb, 1)
            btn_cfg = QPushButton('Configure ⚙')
            btn_cfg.setFixedWidth(88)
            btn_cfg.setStyleSheet('padding: 3px 6px; font-size: 11px;')
            btn_cfg.clicked.connect(lambda _, idx=tab_idx: self.switch_to_config_tab(idx))
            row.addWidget(btn_cfg)
            sg.addLayout(row)

        col1_layout.addWidget(stages_group)

        # 1.4 Advanced Settings (Blender path)
        self.advanced_toggle = QPushButton('Advanced settings ▸')
        self.advanced_toggle.setCheckable(True)
        col1_layout.addWidget(self.advanced_toggle)
        self.advanced = QGroupBox('Blender Executable')
        a = QFormLayout(self.advanced)
        self.blender = QLineEdit()
        a.addRow('Path', self.path_row(self.blender, self.browse_blender))
        self.advanced.setVisible(False)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        col1_layout.addWidget(self.advanced)
        col1_layout.addStretch()

        # =============================================================
        # COLUMN 2: Dedicated Stage Configuration Column
        # =============================================================
        col2_widget = QWidget()
        col2_layout = QVBoxLayout(col2_widget)
        col2_layout.setContentsMargins(6, 0, 6, 0)
        col2_layout.setSpacing(8)

        col2_title_box = QHBoxLayout()
        col2_title = QLabel('Stage Configuration')
        col2_title.setObjectName('SectionTitle')
        col2_title_box.addWidget(col2_title)
        self.col2_stage_count = QLabel('')
        self.col2_stage_count.setStyleSheet('color: #536875; font-size: 11px; margin-left: 6px;')
        col2_title_box.addWidget(self.col2_stage_count)
        col2_title_box.addStretch()
        col2_layout.addLayout(col2_title_box)

        self.tab_config = QTabWidget()
        self.tab_config.setObjectName('ConfigTabs')
        col2_layout.addWidget(self.tab_config, 1)

        # Placeholder when no stages are selected
        self.no_stages_placeholder = QWidget()
        self.no_stages_placeholder.setObjectName('NoStagesPlaceholder')
        placeholder_layout = QVBoxLayout(self.no_stages_placeholder)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_card = QGroupBox()
        placeholder_card_layout = QVBoxLayout(placeholder_card)
        placeholder_card_layout.setContentsMargins(20, 24, 20, 24)
        placeholder_card_layout.setSpacing(10)
        placeholder_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_icon = QLabel('⚙')
        ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_icon.setStyleSheet('font-size: 28px; color: #8fa7b5;')
        placeholder_card_layout.addWidget(ph_icon)

        ph_title = QLabel('No Pipeline Stages Selected')
        ph_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_title.setStyleSheet('font-size: 14px; font-weight: 600; color: #123e50;')
        placeholder_card_layout.addWidget(ph_title)

        ph_msg = QLabel('Select one or more stages in "3   Pipeline Stages" on the left to configure their options here.')
        ph_msg.setWordWrap(True)
        ph_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_msg.setStyleSheet('font-size: 12px; color: #536875;')
        placeholder_card_layout.addWidget(ph_msg)

        placeholder_layout.addWidget(placeholder_card)
        self.no_stages_placeholder.setVisible(False)
        col2_layout.addWidget(self.no_stages_placeholder, 1)

        self.main_split.addWidget(col2_widget)

        # Build individual configuration tabs
        self._build_tab_environment()
        self._build_tab_replay()
        self._build_tab_schooling()
        self._build_tab_feed()
        self._build_tab_feeding()
        self._build_tab_camera()


        # =============================================================
        # COLUMN 3: Build Status, Logs & Execution
        # =============================================================
        right = QWidget()
        right.setObjectName('StatusPanel')
        r = QVBoxLayout(right)
        r.setContentsMargins(8, 0, 0, 0)
        r.setSpacing(10)

        status_title = QLabel('Build & Execution')
        status_title.setObjectName('SectionTitle')
        r.addWidget(status_title)
        self.status = QLabel('Ready to select an AquaSim model')
        self.status.setWordWrap(True)
        r.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        r.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setPlaceholderText('Blender pipeline output logs will stream here.')
        r.addWidget(self.log, 1)
        self.log_note = QLabel('Build log is saved beside the output scene.')
        self.log_note.setWordWrap(True)
        r.addWidget(self.log_note)

        actions_box = QVBoxLayout()
        actions_box.setSpacing(8)
        self.build_button = QPushButton('Build Blender scene')
        self.build_button.setObjectName('Primary')
        self.build_button.setEnabled(False)
        self.build_button.clicked.connect(self.start_build)
        actions_box.addWidget(self.build_button)

        row_ctrl = QHBoxLayout()
        self.cancel_button = QPushButton('Cancel build')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        row_ctrl.addWidget(self.cancel_button)
        self.open_button = QPushButton('Open in Blender')
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_scene)
        row_ctrl.addWidget(self.open_button)
        self.folder_button = QPushButton('Show Folder')
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.open_folder)
        row_ctrl.addWidget(self.folder_button)
        actions_box.addLayout(row_ctrl)
        r.addLayout(actions_box)

        self.main_split.addWidget(right)
        self.main_split.setSizes([350, 560, 390])

        # Hook up option change events
        self.opt_env.toggled.connect(self.update_tab_headers)
        self.opt_replay.toggled.connect(self.replay_toggled)
        self.opt_schooling.toggled.connect(self.update_tab_headers)
        self.opt_feed.toggled.connect(self.update_tab_headers)
        self.opt_feeding.toggled.connect(self.update_tab_headers)
        self.opt_camera.toggled.connect(self.update_tab_headers)

        self.setStyleSheet('''
            QMainWindow, QWidget#AppRoot, QWidget#FormPanel, QWidget#StatusPanel,
            QScrollArea, QScrollArea > QWidget > QWidget { background: #f1f5f7; }
            QWidget { color: #192d3b; font-family: "Segoe UI"; font-size: 12px; }
            QScrollArea { border: none; }
            QLabel#Title { font-size: 26px; font-weight: 700; color: #123e50; }
            QLabel#Subtitle { color: #536875; font-size: 13px; }
            QLabel#SectionTitle { font-size: 16px; font-weight: 600; color: #123e50; }
            QLabel#Warning { color: #9a5515; }
            QGroupBox { background: white; border: 1px solid #d5e0e5; border-radius: 6px;
                        margin-top: 10px; padding: 14px 10px 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget { background: white; color: #192d3b;
                        border: 1px solid #c6d5de; border-radius: 4px; padding: 4px; }
            QPlainTextEdit { background: #132733; color: #dce9ef; border-radius: 6px;
                            padding: 8px; font-family: Consolas; font-size: 11px; }
            QPushButton { background: #e3edf2; border: 1px solid #c9d9e2; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background: #d3e5ee; }
            QPushButton#Primary { background: #087e8b; color: white; font-weight: 600; padding: 10px 20px; font-size: 14px; }
            QPushButton:disabled { background: #e4e9ec; color: #8998a1; }
            QProgressBar { background: white; color: #192d3b; border: 1px solid #c6d5de;
                           border-radius: 4px; text-align: center; height: 18px; }
            QProgressBar::chunk { background: #42a5ad; }
            QTabWidget::pane { border: 1px solid #c6d5de; background: white; border-radius: 6px; }
            QTabBar::tab { background: #e3edf2; border: 1px solid #c6d5de; padding: 8px 14px;
                           margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: 600; color: #087e8b; }
        ''')

    def switch_to_config_tab(self, index: int):
        stages = [
            (self.opt_env, 0),
            (self.opt_replay, 1),
            (self.opt_schooling, 2),
            (self.opt_feed, 3),
            (self.opt_feeding, 4),
            (self.opt_camera, 5),
        ]
        for cb, idx in stages:
            if idx == index:
                if not cb.isChecked():
                    cb.setChecked(True)
                break
        self.update_tab_headers()
        self.tab_config.setCurrentIndex(index)

    def update_tab_headers(self):
        stage_items = [
            (self.opt_env, 0, '🌊 Environment'),
            (self.opt_replay, 1, '🌊 Replay'),
            (self.opt_schooling, 2, '🐟 Schooling'),
            (self.opt_feed, 3, '🌀 Feed'),
            (self.opt_feeding, 4, '🍴 Feeding'),
            (self.opt_camera, 5, '🎥 Camera'),
        ]
        active_count = 0
        first_visible_idx = -1
        for cb, idx, name in stage_items:
            is_active = cb.isChecked()
            self.tab_config.setTabText(idx, name)
            self.tab_config.setTabVisible(idx, is_active)
            if is_active:
                active_count += 1
                if first_visible_idx == -1:
                    first_visible_idx = idx

        if hasattr(self, 'col2_stage_count'):
            self.col2_stage_count.setText(f'({active_count} active)' if active_count > 0 else '(none selected)')

        if hasattr(self, 'no_stages_placeholder'):
            self.no_stages_placeholder.setVisible(active_count == 0)
            self.tab_config.setVisible(active_count > 0)

        current_idx = self.tab_config.currentIndex()
        if current_idx >= 0 and not self.tab_config.isTabVisible(current_idx):
            if first_visible_idx >= 0:
                self.tab_config.setCurrentIndex(first_visible_idx)

    def path_row(self, edit, callback):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(edit, 1)
        button = QPushButton('Browse…')
        button.clicked.connect(callback)
        row.addWidget(button)
        return widget

    def update_duration(self):
        step = self.wave_period.value() / self.frames_per_wave.value()
        if self.results_info:
            timing = wave_timing(self.results_info['samples'], self.wave_period.value(), self.frames_per_wave.value(), self.fps.value())
            self.timing_summary.setText(
                f"Structural motion time: {timing['duration_seconds']:.6g} s\n"
                f"Source frames: {timing['samples']:,} · {self.results_info['nodes_per_sample']:,} nodes/frame\n"
                f"Sample interval: {step:.6g} s\n"
                f"Video / fish frames: {timing['video_frame_end']:,}\n"
                f"AquaSim time: {timing['duration_seconds']:.6g} s\n"
                f"Total video frames: {timing['video_frame_end']:,} ({timing['video_duration_seconds']:.4g} s at {self.fps.value()} fps)"
            )
        if self.opt_replay.isChecked():
            self.duration.setText(f'AquaSim replay ({self.fps.value()} fps)')
        else:
            self.duration.setText(f'{self.frames.value() / 24:.1f}s @ 24fps')

    def replay_toggled(self, checked):
        self.pins.setEnabled(not checked)
        self.pins.setVisible(not checked)
        self.frames.setVisible(not checked)
        if checked:
            self.pins.setToolTip('Top rim supports are not needed during AquaSim results replay.')
        else:
            self.pins.setToolTip('Adds top-rim cloth pins in addition to source supports.')
        self.update_duration()
        self.update_tab_headers()
        self.selection_changed()

    def suggest_output(self):
        if not self.info:
            return
        suggested = str(PROJECT_ROOT / 'output' / f'{self.info.path.stem}_scene.blend')
        if not self.output.text() or self.output.text() == self.suggested_output:
            self.output.setText(suggested)
        self.suggested_output = suggested

    def browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select AquaSim model',
            self.model.text() or str(PROJECT_ROOT / 'examples/models'),
            'AquaSim models (*.amodel)'
        )
        if path:
            self.model.setText(path)

    def browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Blender scene',
            self.output.text() or str(PROJECT_ROOT / 'output'),
            'Blender scenes (*.blend)'
        )
        if path:
            self.output.setText(path if path.lower().endswith('.blend') else path + '.blend')

    def browse_results(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select AquaSim results text export',
            self.results.text() or str(PROJECT_ROOT / 'examples/models'),
            'AquaSim results (*.txt);;All files (*)'
        )
        if path:
            self.results.setText(path)

    def browse_spreader_move(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select spreader_move.obj',
            self.spreader_move_edit.text() or str(PROJECT_ROOT / 'assets/spreaders/default'),
            'Wavefront OBJ (*.obj);;All files (*)'
        )
        if path:
            self.spreader_move_edit.setText(path)

    def browse_spreader_still(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select spreader_still.obj',
            self.spreader_still_edit.text() or str(PROJECT_ROOT / 'assets/spreaders/default'),
            'Wavefront OBJ (*.obj);;All files (*)'
        )
        if path:
            self.spreader_still_edit.setText(path)

    def browse_blender(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Blender executable',
            self.blender.text(),
            'Executables (*.exe);;All files (*)' if sys.platform == 'win32' else 'All files (*)'
        )
        if path:
            self.blender.setText(path)

    def _toggle_beam_truss(self, checked: bool):
        self.beam_truss_container.setVisible(checked)
        self._update_beam_truss_toggle_text()

    def _update_beam_truss_toggle_text(self):
        arrow = '▾' if self.beam_truss_toggle.isChecked() else '▸'
        b_sel = len(self.selected_beam_ids())
        b_tot = self.beam_components.count()
        t_sel = len(self.selected_truss_ids())
        t_tot = self.truss_components.count()
        if b_tot or t_tot:
            self.beam_truss_toggle.setText(f'Beam & truss elements ({b_sel}/{b_tot} beams, {t_sel}/{t_tot} trusses) {arrow}')
        else:
            self.beam_truss_toggle.setText(f'Beam & truss elements (advanced) {arrow}')

    def selected_beam_ids(self):
        return [
            self.beam_components.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.beam_components.count())
            if self.beam_components.item(i).checkState() == Qt.CheckState.Checked
        ]

    def selected_truss_ids(self):
        return [
            self.truss_components.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.truss_components.count())
            if self.truss_components.item(i).checkState() == Qt.CheckState.Checked
        ]

    def select_all_beams(self):
        self.beam_components.blockSignals(True)
        for i in range(self.beam_components.count()):
            self.beam_components.item(i).setCheckState(Qt.CheckState.Checked)
        self.beam_components.blockSignals(False)
        self.selection_changed()

    def select_no_beams(self):
        self.beam_components.blockSignals(True)
        for i in range(self.beam_components.count()):
            self.beam_components.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.beam_components.blockSignals(False)
        self.selection_changed()

    def select_all_trusses(self):
        self.truss_components.blockSignals(True)
        for i in range(self.truss_components.count()):
            self.truss_components.item(i).setCheckState(Qt.CheckState.Checked)
        self.truss_components.blockSignals(False)
        self.selection_changed()

    def select_no_trusses(self):
        self.truss_components.blockSignals(True)
        for i in range(self.truss_components.count()):
            self.truss_components.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.truss_components.blockSignals(False)
        self.selection_changed()

    def model_changed(self):
        self.token += 1
        self.info = None
        self.components.clear()
        self.beam_components.clear()
        self.truss_components.clear()
        self.warning.clear()
        self._update_beam_truss_toggle_text()
        self.build_button.setEnabled(False)
        self.model_summary.setText('Waiting to inspect model…')
        self.load_timer.start()

    def load_model(self):
        self.load_timer.stop()
        path = self.model.text().strip()
        if not path or not Path(path).is_file():
            self.model_summary.setText('Choose an existing .amodel file.')
            return
        self.model_summary.setText('Reading active membrane components…')
        worker = Inspector(path, self.token, self)
        self.workers.append(worker)
        worker.result.connect(self.model_loaded)
        worker.finished.connect(lambda: self.workers.remove(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def model_loaded(self, token, info, error):
        if token != self.token:
            return
        if error:
            self.model_summary.setText('Could not read model: ' + error)
            return
        self.info = info
        b_count = len(getattr(info, 'beam_components', []))
        t_count = len(getattr(info, 'truss_components', []))
        self.model_summary.setText(
            f'{info.node_count:,} active nodes · {len(info.components)} membrane'
            + (f' · {b_count} beam' if b_count else '')
            + (f' · {t_count} truss' if t_count else '')
        )
        self.components.blockSignals(True)
        self.components.clear()
        key = 'membranes/' + hashlib.sha256(str(info.path).encode()).hexdigest()
        saved = self.settings.value(key, None)
        checked = {str(cid) for cid in saved} if isinstance(saved, list) else None
        for comp in info.components:
            item = QListWidgetItem(f'{comp["id"]}  ·  {comp["name"]}  ({comp["faces"]:,} faces)')
            item.setData(Qt.ItemDataRole.UserRole, comp['id'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked is None or str(comp['id']) in checked else Qt.CheckState.Unchecked)
            self.components.addItem(item)
        self.components.blockSignals(False)

        # Beam components (selected by default)
        self.beam_components.blockSignals(True)
        self.beam_components.clear()
        beam_key = 'beams/' + hashlib.sha256(str(info.path).encode()).hexdigest()
        saved_beams = self.settings.value(beam_key, None)
        checked_beams = {str(cid) for cid in saved_beams} if isinstance(saved_beams, list) else None
        for comp in getattr(info, 'beam_components', []):
            item = QListWidgetItem(f'{comp["id"]}  ·  {comp["name"]}  ({comp["elements"]:,} elements)')
            item.setData(Qt.ItemDataRole.UserRole, comp['id'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked_beams is None or str(comp['id']) in checked_beams else Qt.CheckState.Unchecked)
            self.beam_components.addItem(item)
        self.beam_components.blockSignals(False)

        # Truss components (selected by default)
        self.truss_components.blockSignals(True)
        self.truss_components.clear()
        truss_key = 'trusses/' + hashlib.sha256(str(info.path).encode()).hexdigest()
        saved_trusses = self.settings.value(truss_key, None)
        checked_trusses = {str(cid) for cid in saved_trusses} if isinstance(saved_trusses, list) else None
        for comp in getattr(info, 'truss_components', []):
            item = QListWidgetItem(f'{comp["id"]}  ·  {comp["name"]}  ({comp["elements"]:,} elements)')
            item.setData(Qt.ItemDataRole.UserRole, comp['id'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked_trusses is None or str(comp['id']) in checked_trusses else Qt.CheckState.Unchecked)
            self.truss_components.addItem(item)
        self.truss_components.blockSignals(False)

        self._update_beam_truss_toggle_text()
        self.output.clear()
        self.suggest_output()
        self.settings.setValue('model', str(info.path))
        self.selection_changed()

    def selected_ids(self):
        return [
            self.components.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.components.count())
            if self.components.item(i).checkState() == Qt.CheckState.Checked
        ]

    def needs_enclosure(self):
        return not self.opt_replay.isChecked() or self.opt_schooling.isChecked()

    def selection_changed(self):
        ids = self.selected_ids()
        beam_ids = self.selected_beam_ids()
        truss_ids = self.selected_truss_ids()
        if self.info:
            key = 'membranes/' + hashlib.sha256(str(self.info.path).encode()).hexdigest()
            self.settings.setValue(key, [str(cid) for cid in ids])
            beam_key = 'beams/' + hashlib.sha256(str(self.info.path).encode()).hexdigest()
            self.settings.setValue(beam_key, [str(cid) for cid in beam_ids])
            truss_key = 'trusses/' + hashlib.sha256(str(self.info.path).encode()).hexdigest()
            self.settings.setValue(truss_key, [str(cid) for cid in truss_ids])
        self._update_beam_truss_toggle_text()
        conflicts, involved = self.info.junctions(ids) if self.info else (0, [])
        if conflicts:
            self.warning.setText(
                f'{conflicts} edges are shared by more than two faces in components {", ".join(map(str, involved))}. '
                'Uncheck attached flaps/internal sheets to form an enclosing shell.'
            )
        else:
            self.warning.setText('Enclosing shell ready.' if ids else 'Select the enclosing walls and bottom.')

        needs_enc = self.needs_enclosure()
        ready = bool(self.info and (ids or not needs_enc) and not conflicts)
        if self.opt_replay.isChecked():
            ready = ready and (self.results_info is not None)

        self.build_button.setEnabled(bool(ready and not self.running))
        if not self.running:
            self.status.setText('Ready to build' if ready else 'Select a valid results file' if self.opt_replay.isChecked() and self.results_info is None else 'Choose enclosing components')

    def results_changed(self):
        self.results_token += 1
        self.results_info = None
        for worker in self.workers:
            if isinstance(worker, ResultsInspector):
                worker.requestInterruption()
        self.timing_summary.setText('Reading results file…' if self.results.text() else 'Select a results file to calculate total time.')
        self.results_timer.start()
        self.selection_changed()

    def load_results(self):
        self.results_timer.stop()
        path = self.results.text().strip()
        if not path or not Path(path).is_file():
            self.timing_summary.setText('Choose an existing AquaSim results export (out.txt).')
            return
        worker = ResultsInspector(path, self.results_token, self)
        self.workers.append(worker)
        worker.result.connect(self.results_loaded)
        worker.finished.connect(lambda: self.workers.remove(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def results_loaded(self, token, info, error):
        if token != self.results_token:
            return
        self.results_info = info
        if error:
            self.timing_summary.setText('Could not read results: ' + error)
        else:
            self.update_duration()
        self.selection_changed()

    def _load_saved_settings(self):
        self.blender.setText(self.settings.value('blender', find_blender()))
        self.frames.setValue(self.settings.value('frames', 120, type=int))
        self.caps.setChecked(self.settings.value('caps', True, type=bool))
        self.pins.setChecked(self.settings.value('pins', True, type=bool))

        # Environment
        self.opt_env.setChecked(self.settings.value('opt_env', True, type=bool))
        self.env_water_level.setValue(self.settings.value('env_water_level', 0.0, type=float))
        self.env_water_depth.setValue(self.settings.value('env_water_depth', 100.0, type=float))
        self.env_water_size.setValue(self.settings.value('env_water_size', 300.0, type=float))
        self.env_enable_volume.setChecked(self.settings.value('env_enable_volume', True, type=bool))
        self.env_wave_type.setCurrentIndex(max(0, self.env_wave_type.findData(self.settings.value('env_wave_type', 'regular'))))
        self.env_jonswap_gamma.setValue(self.settings.value('env_jonswap_gamma', 3.3, type=float))
        self.env_wave_components.setValue(self.settings.value('env_wave_components', 64, type=int))
        self.env_wave_seed.setValue(self.settings.value('env_wave_seed', 42, type=int))
        self.env_wave_spread_deg.setValue(self.settings.value('env_wave_spread_deg', 20.0, type=float))
        self.env_wave_height.setValue(self.settings.value('env_wave_height', 0.30, type=float))
        self.env_wave_period.setValue(self.settings.value('env_wave_period', 6.0, type=float))
        self.env_wave_length.setValue(self.settings.value('env_wave_length', 25.0, type=float))
        self.env_wave_dir.setValue(self.settings.value('env_wave_dir', 0.0, type=float))
        self.env_current_speed.setValue(self.settings.value('env_current_speed', 0.15, type=float))
        self.env_current_dir.setValue(self.settings.value('env_current_dir', 0.0, type=float))

        # Replay
        self.opt_replay.setChecked(self.settings.value('opt_replay', False, type=bool))
        self.results.setText(self.settings.value('results', ''))
        self.fps.setValue(self.settings.value('fps', 25, type=int))
        self.wave_period.setValue(self.settings.value('wave_period', 5.0, type=float))
        self.frames_per_wave.setValue(self.settings.value('frames_per_wave', 40, type=int))
        self.replay_start_offset.setValue(self.settings.value('replay_start_offset', 0, type=int))
        self.replay_max_samples.setValue(self.settings.value('replay_max_samples', 0, type=int))
        self.replay_loop.setChecked(self.settings.value('replay_loop', False, type=bool))

        # Fish Schooling
        self.opt_schooling.setChecked(self.settings.value('opt_schooling', True, type=bool))
        self.fish_count.setValue(self.settings.value('fish_count', 1000, type=int))
        self.fish_species.setText(self.settings.value('fish_species', 'Atlantic salmon'))
        self.fish_length_mean.setValue(self.settings.value('fish_length_mean', 0.775, type=float))
        self.fish_length_std.setValue(self.settings.value('fish_length_std', 0.05, type=float))
        self.fish_nominal_weight.setValue(self.settings.value('fish_nominal_weight', 5.0, type=float))
        self.fish_separation_weight.setValue(self.settings.value('fish_separation_weight', 0.35, type=float))
        self.fish_separation_radius.setValue(self.settings.value('fish_separation_radius', 1.2, type=float))
        self.fish_alignment_weight.setValue(self.settings.value('fish_alignment_weight', 0.25, type=float))
        self.fish_neighbor_radius.setValue(self.settings.value('fish_neighbor_radius', 2.5, type=float))
        self.fish_school_cohesion.setValue(self.settings.value('fish_school_cohesion', 0.15, type=float))
        self.fish_milling_weight.setValue(self.settings.value('fish_milling_weight', 0.45, type=float))
        self.fish_cohesion.setValue(self.settings.value('fish_cohesion', 0.08, type=float))
        self.fish_depth_min.setValue(self.settings.value('fish_depth_min', -12.0, type=float))
        self.fish_depth_max.setValue(self.settings.value('fish_depth_max', -2.5, type=float))
        self.fish_depth_weight.setValue(self.settings.value('fish_depth_weight', 0.25, type=float))
        self.fish_vert_osc.setValue(self.settings.value('fish_vert_osc', 0.35, type=float))
        self.fish_flow_direction.setCurrentIndex(self.settings.value('fish_flow_direction', 0, type=int))
        self.fish_cruise_speed.setValue(self.settings.value('fish_cruise_speed', 0.85, type=float))
        self.fish_wall_detection.setValue(self.settings.value('fish_wall_detection', 1.5, type=float))
        self.fish_wall_avoidance.setValue(self.settings.value('fish_wall_avoidance', 0.75, type=float))
        self.fish_wall_buffer.setValue(self.settings.value('fish_wall_buffer', 0.05, type=float))
        self.fish_max_turn_rate.setValue(self.settings.value('fish_max_turn_rate', 120.0, type=float))
        self.fish_seed.setValue(self.settings.value('fish_seed', 7, type=int))
        self.fish_tail_motion.setChecked(self.settings.value('fish_tail_motion', True, type=bool))
        self.fish_tail_amplitude.setValue(self.settings.value('fish_tail_amplitude', 0.065, type=float))
        self.fish_tail_frequency.setValue(self.settings.value('fish_tail_frequency', 2.2, type=float))

        # Feed
        self.opt_feed.setChecked(self.settings.value('opt_feed', False, type=bool))
        self.spreader_move_edit.setText(self.settings.value('spreader_move', str(PROJECT_ROOT / 'assets/spreaders/default/spreader_move.obj')))
        self.spreader_still_edit.setText(self.settings.value('spreader_still', str(PROJECT_ROOT / 'assets/spreaders/default/spreader_still.obj')))
        self.spreader_z_offset.setValue(self.settings.value('spreader_z_offset', 0.52, type=float))
        self.spreader_heave_rao.setValue(self.settings.value('spreader_heave_rao', 0.50, type=float))
        self.feed_rpm.setValue(self.settings.value('feed_rpm', -30.0, type=float))
        self.feed_mass_flow.setValue(self.settings.value('feed_mass_flow', 30.0, type=float))
        self.feed_pellet_mass.setValue(self.settings.value('feed_pellet_mass', 0.01, type=float))
        self.feed_lifetime.setValue(self.settings.value('feed_lifetime', 30.0, type=float))
        self.pellet_radius_mean.setValue(self.settings.value('pellet_radius_mean', 0.005, type=float))
        self.pellet_radius_std.setValue(self.settings.value('pellet_radius_std', 0.0008, type=float))
        self.pellet_aspect_ratio.setValue(self.settings.value('pellet_aspect_ratio', 1.6, type=float))
        self.feed_outward_speed.setValue(self.settings.value('feed_outward_speed', 1.0, type=float))
        self.feed_downward_speed.setValue(self.settings.value('feed_downward_speed', 0.001, type=float))
        self.feed_pellet_density.setValue(self.settings.value('feed_pellet_density', 1100.0, type=float))
        self.feed_water_level.setValue(self.settings.value('feed_water_level', 0.0, type=float))
        self.feed_water_drag.setValue(self.settings.value('feed_water_drag', 0.85, type=float))
        self.feed_air_drag.setValue(self.settings.value('feed_air_drag', 0.47, type=float))
        self.feed_seed.setValue(self.settings.value('feed_seed', 30030, type=int))

        # Fish Feeding
        self.opt_feeding.setChecked(self.settings.value('opt_feeding', False, type=bool))
        self.feeding_sensing_radius.setValue(self.settings.value('feeding_sensing_radius', 2.5, type=float))
        self.feeding_ingestion_radius.setValue(self.settings.value('feeding_ingestion_radius', 0.22, type=float))
        self.feeding_burst_speed.setValue(self.settings.value('feeding_burst_speed', 2.0, type=float))
        self.feeding_cooldown.setValue(self.settings.value('feeding_cooldown', 10.0, type=float))
        self.feeding_attraction_weight.setValue(self.settings.value('feeding_attraction_weight', 0.55, type=float))
        self.feeding_min_depth.setValue(self.settings.value('feeding_min_depth', -25.0, type=float))
        self.feeding_max_depth.setValue(self.settings.value('feeding_max_depth', 0.0, type=float))

        # Camera
        self.opt_camera.setChecked(self.settings.value('opt_camera', False, type=bool))
        self.camera_focal_length.setValue(self.settings.value('camera_focal_length', 32.0, type=float))
        self.camera_enable_dof.setChecked(self.settings.value('camera_enable_dof', True, type=bool))
        self.camera_fstop.setValue(self.settings.value('camera_fstop', 3.5, type=float))
        self.camera_clip_start.setValue(self.settings.value('camera_clip_start', 0.1, type=float))
        self.camera_clip_end.setValue(self.settings.value('camera_clip_end', 500.0, type=float))
        self.camera_overview_height.setValue(self.settings.value('camera_overview_height', 52.0, type=float))
        self.camera_overview_distance.setValue(self.settings.value('camera_overview_distance', 104.0, type=float))
        self.camera_swoop_height.setValue(self.settings.value('camera_swoop_height', 2.6, type=float))
        self.camera_water_depth.setValue(self.settings.value('camera_water_depth', -3.5, type=float))
        self.camera_phase1_pct.setValue(self.settings.value('camera_phase1_pct', 0.35, type=float))
        self.camera_phase2_pct.setValue(self.settings.value('camera_phase2_pct', 0.60, type=float))

        self.update_tab_headers()

    def _save_current_settings(self):
        self.settings.setValue('blender', self.blender.text().strip())
        self.settings.setValue('frames', self.frames.value())
        self.settings.setValue('caps', self.caps.isChecked())
        self.settings.setValue('pins', self.pins.isChecked())

        self.settings.setValue('opt_env', self.opt_env.isChecked())
        self.settings.setValue('env_water_level', self.env_water_level.value())
        self.settings.setValue('env_water_depth', self.env_water_depth.value())
        self.settings.setValue('env_water_size', self.env_water_size.value())
        self.settings.setValue('env_enable_volume', self.env_enable_volume.isChecked())
        self.settings.setValue('env_wave_type', self.env_wave_type.currentData())
        self.settings.setValue('env_jonswap_gamma', self.env_jonswap_gamma.value())
        self.settings.setValue('env_wave_components', self.env_wave_components.value())
        self.settings.setValue('env_wave_seed', self.env_wave_seed.value())
        self.settings.setValue('env_wave_spread_deg', self.env_wave_spread_deg.value())
        self.settings.setValue('env_wave_height', self.env_wave_height.value())
        self.settings.setValue('env_wave_period', self.env_wave_period.value())
        self.settings.setValue('env_wave_length', self.env_wave_length.value())
        self.settings.setValue('env_wave_dir', self.env_wave_dir.value())
        self.settings.setValue('env_current_speed', self.env_current_speed.value())
        self.settings.setValue('env_current_dir', self.env_current_dir.value())

        self.settings.setValue('opt_replay', self.opt_replay.isChecked())
        self.settings.setValue('results', self.results.text())
        self.settings.setValue('fps', self.fps.value())
        self.settings.setValue('wave_period', self.wave_period.value())
        self.settings.setValue('frames_per_wave', self.frames_per_wave.value())
        self.settings.setValue('replay_start_offset', self.replay_start_offset.value())
        self.settings.setValue('replay_max_samples', self.replay_max_samples.value())
        self.settings.setValue('replay_loop', self.replay_loop.isChecked())

        self.settings.setValue('opt_schooling', self.opt_schooling.isChecked())
        self.settings.setValue('fish_count', self.fish_count.value())
        self.settings.setValue('fish_species', self.fish_species.text())
        self.settings.setValue('fish_length_mean', self.fish_length_mean.value())
        self.settings.setValue('fish_length_std', self.fish_length_std.value())
        self.settings.setValue('fish_nominal_weight', self.fish_nominal_weight.value())
        self.settings.setValue('fish_separation_weight', self.fish_separation_weight.value())
        self.settings.setValue('fish_separation_radius', self.fish_separation_radius.value())
        self.settings.setValue('fish_alignment_weight', self.fish_alignment_weight.value())
        self.settings.setValue('fish_neighbor_radius', self.fish_neighbor_radius.value())
        self.settings.setValue('fish_school_cohesion', self.fish_school_cohesion.value())
        self.settings.setValue('fish_milling_weight', self.fish_milling_weight.value())
        self.settings.setValue('fish_cohesion', self.fish_cohesion.value())
        self.settings.setValue('fish_depth_min', self.fish_depth_min.value())
        self.settings.setValue('fish_depth_max', self.fish_depth_max.value())
        self.settings.setValue('fish_depth_weight', self.fish_depth_weight.value())
        self.settings.setValue('fish_vert_osc', self.fish_vert_osc.value())
        self.settings.setValue('fish_flow_direction', self.fish_flow_direction.currentIndex())
        self.settings.setValue('fish_cruise_speed', self.fish_cruise_speed.value())
        self.settings.setValue('fish_wall_detection', self.fish_wall_detection.value())
        self.settings.setValue('fish_wall_avoidance', self.fish_wall_avoidance.value())
        self.settings.setValue('fish_wall_buffer', self.fish_wall_buffer.value())
        self.settings.setValue('fish_max_turn_rate', self.fish_max_turn_rate.value())
        self.settings.setValue('fish_seed', self.fish_seed.value())
        self.settings.setValue('fish_tail_motion', self.fish_tail_motion.isChecked())
        self.settings.setValue('fish_tail_amplitude', self.fish_tail_amplitude.value())
        self.settings.setValue('fish_tail_frequency', self.fish_tail_frequency.value())

        self.settings.setValue('opt_feed', self.opt_feed.isChecked())
        self.settings.setValue('spreader_move', self.spreader_move_edit.text())
        self.settings.setValue('spreader_still', self.spreader_still_edit.text())
        self.settings.setValue('spreader_z_offset', self.spreader_z_offset.value())
        self.settings.setValue('spreader_heave_rao', self.spreader_heave_rao.value())
        self.settings.setValue('feed_rpm', self.feed_rpm.value())
        self.settings.setValue('feed_mass_flow', self.feed_mass_flow.value())
        self.settings.setValue('feed_pellet_mass', self.feed_pellet_mass.value())
        self.settings.setValue('feed_lifetime', self.feed_lifetime.value())
        self.settings.setValue('pellet_radius_mean', self.pellet_radius_mean.value())
        self.settings.setValue('pellet_radius_std', self.pellet_radius_std.value())
        self.settings.setValue('pellet_aspect_ratio', self.pellet_aspect_ratio.value())
        self.settings.setValue('feed_outward_speed', self.feed_outward_speed.value())
        self.settings.setValue('feed_downward_speed', self.feed_downward_speed.value())
        self.settings.setValue('feed_pellet_density', self.feed_pellet_density.value())
        self.settings.setValue('feed_water_level', self.feed_water_level.value())
        self.settings.setValue('feed_water_drag', self.feed_water_drag.value())
        self.settings.setValue('feed_air_drag', self.feed_air_drag.value())
        self.settings.setValue('feed_seed', self.feed_seed.value())

        self.settings.setValue('opt_feeding', self.opt_feeding.isChecked())
        self.settings.setValue('feeding_sensing_radius', self.feeding_sensing_radius.value())
        self.settings.setValue('feeding_ingestion_radius', self.feeding_ingestion_radius.value())
        self.settings.setValue('feeding_burst_speed', self.feeding_burst_speed.value())
        self.settings.setValue('feeding_cooldown', self.feeding_cooldown.value())
        self.settings.setValue('feeding_attraction_weight', self.feeding_attraction_weight.value())
        self.settings.setValue('feeding_min_depth', self.feeding_min_depth.value())
        self.settings.setValue('feeding_max_depth', self.feeding_max_depth.value())

        self.settings.setValue('opt_camera', self.opt_camera.isChecked())
        self.settings.setValue('camera_focal_length', self.camera_focal_length.value())
        self.settings.setValue('camera_enable_dof', self.camera_enable_dof.isChecked())
        self.settings.setValue('camera_fstop', self.camera_fstop.value())
        self.settings.setValue('camera_clip_start', self.camera_clip_start.value())
        self.settings.setValue('camera_clip_end', self.camera_clip_end.value())
        self.settings.setValue('camera_overview_height', self.camera_overview_height.value())
        self.settings.setValue('camera_overview_distance', self.camera_overview_distance.value())
        self.settings.setValue('camera_swoop_height', self.camera_swoop_height.value())
        self.settings.setValue('camera_water_depth', self.camera_water_depth.value())
        self.settings.setValue('camera_phase1_pct', self.camera_phase1_pct.value())
        self.settings.setValue('camera_phase2_pct', self.camera_phase2_pct.value())
        self.settings.sync()

    def start_build(self):
        if self.running:
            return
        try:
            if self.info is None:
                raise ValueError('Wait for the model to finish loading.')
            if self.needs_enclosure() and self.info.junctions(self.selected_ids())[0]:
                raise ValueError('Remove overlapping membrane components first.')
            if not self.output.text().strip():
                raise ValueError('Choose where to save the scene.')

            env_dict = None
            if self.opt_env.isChecked():
                env_dict = {
                    'enabled': True,
                    'water_level_m': self.env_water_level.value(),
                    'water_depth_m': self.env_water_depth.value(),
                    'water_size_m': self.env_water_size.value(),
                    'enable_volume': self.env_enable_volume.isChecked(),
                    'current_speed_m_s': self.env_current_speed.value(),
                    'current_direction_deg': self.env_current_dir.value(),
                    'wave_type': self.env_wave_type.currentData(),
                    'jonswap_gamma': self.env_jonswap_gamma.value(),
                    'wave_components': self.env_wave_components.value(),
                    'wave_seed': self.env_wave_seed.value(),
                    'wave_spread_deg': self.env_wave_spread_deg.value(),
                    'wave_height_m': self.env_wave_height.value(),
                    'wave_period_s': self.env_wave_period.value(),
                    'wave_length_m': self.env_wave_length.value(),
                    'wave_direction_deg': self.env_wave_dir.value(),
                }

            replay_dict = None
            if self.opt_replay.isChecked():
                if self.results_info is None:
                    raise ValueError('Wait for a valid AquaSim results file.')
                replay_dict = {
                    'enabled': True,
                    'results': str(Path(self.results.text().strip()).resolve()),
                    'wave_period': self.wave_period.value(),
                    'frames_per_wave': self.frames_per_wave.value(),
                    'fps': self.fps.value(),
                    'start_offset': self.replay_start_offset.value(),
                    'max_samples': self.replay_max_samples.value(),
                    'loop': self.replay_loop.isChecked(),
                }

            schooling_dict = None
            if self.opt_schooling.isChecked():
                flow_dir_val = 1.0 if self.fish_flow_direction.currentIndex() == 0 else -1.0
                schooling_dict = {
                    'enabled': True,
                    'fish_count': self.fish_count.value(),
                    'species': self.fish_species.text().strip(),
                    'fish_length_mean_m': self.fish_length_mean.value(),
                    'fish_length_std_m': self.fish_length_std.value(),
                    'nominal_weight_kg': self.fish_nominal_weight.value(),
                    'swim_speed_bl_s': self.fish_cruise_speed.value(),
                    'random_seed': self.fish_seed.value(),
                    'separation_weight': self.fish_separation_weight.value(),
                    'separation_radius_m': self.fish_separation_radius.value(),
                    'alignment_weight': self.fish_alignment_weight.value(),
                    'neighbor_radius_m': self.fish_neighbor_radius.value(),
                    'school_cohesion_weight': self.fish_school_cohesion.value(),
                    'milling_weight': self.fish_milling_weight.value(),
                    'cohesion_weight': self.fish_cohesion.value(),
                    'cage_cohesion_weight': self.fish_cohesion.value(),
                    'flow_direction': flow_dir_val,
                    'preferred_depth_min_m': self.fish_depth_min.value(),
                    'preferred_depth_max_m': self.fish_depth_max.value(),
                    'depth_weight': self.fish_depth_weight.value(),
                    'vertical_oscillation_m': self.fish_vert_osc.value(),
                    'wall_detection_dist_m': self.fish_wall_detection.value(),
                    'wall_avoidance_weight': self.fish_wall_avoidance.value(),
                    'wall_buffer_m': self.fish_wall_buffer.value(),
                    'max_turn_rate_deg_s': self.fish_max_turn_rate.value(),
                    'tail_motion': self.fish_tail_motion.isChecked(),
                    'tail_amplitude_m': self.fish_tail_amplitude.value(),
                    'tail_frequency_hz': self.fish_tail_frequency.value(),
                }

            feed_dict = None
            if self.opt_feed.isChecked():
                feed_dict = {
                    'enabled': True,
                    'spreader_move_obj': self.spreader_move_edit.text().strip(),
                    'spreader_still_obj': self.spreader_still_edit.text().strip(),
                    'spreader_z_offset': self.spreader_z_offset.value(),
                    'spreader_heave_rao': self.spreader_heave_rao.value(),
                    'rpm': self.feed_rpm.value(),
                    'mass_flow_kg_min': self.feed_mass_flow.value(),
                    'visual_particle_mass_kg': self.feed_pellet_mass.value(),
                    'particle_lifetime_s': self.feed_lifetime.value(),
                    'pellet_radius_mean_m': self.pellet_radius_mean.value(),
                    'pellet_radius_std_m': self.pellet_radius_std.value(),
                    'pellet_aspect_ratio': self.pellet_aspect_ratio.value(),
                    'outward_speed_m_s': self.feed_outward_speed.value(),
                    'downward_speed_m_s': self.feed_downward_speed.value(),
                    'pellet_density_kg_m3': self.feed_pellet_density.value(),
                    'water_level_z': self.feed_water_level.value(),
                    'water_drag_coeff': self.feed_water_drag.value(),
                    'air_drag_coeff': self.feed_air_drag.value(),
                    'random_seed': self.feed_seed.value(),
                    'current_speed_m_s': self.env_current_speed.value() if self.opt_env.isChecked() else 0.0,
                    'current_direction_deg': self.env_current_dir.value() if self.opt_env.isChecked() else 0.0,
                    'wave_height_m': self.env_wave_height.value() if self.opt_env.isChecked() else 0.0,
                    'wave_period_s': self.env_wave_period.value() if self.opt_env.isChecked() else 5.0,
                    'wave_length_m': self.env_wave_length.value() if self.opt_env.isChecked() else 30.0,
                    'wave_direction_deg': self.env_wave_dir.value() if self.opt_env.isChecked() else 0.0,
                }

            feeding_dict = None
            if self.opt_feeding.isChecked():
                feeding_dict = {
                    'enabled': True,
                    'sensing_radius_m': self.feeding_sensing_radius.value(),
                    'ingestion_radius_m': self.feeding_ingestion_radius.value(),
                    'feeding_speed_bl_s': self.feeding_burst_speed.value(),
                    'feeding_cooldown_s': self.feeding_cooldown.value(),
                    'attraction_weight': self.feeding_attraction_weight.value(),
                    'min_feeding_depth_m': self.feeding_min_depth.value(),
                    'max_feeding_depth_m': self.feeding_max_depth.value(),
                }

            camera_dict = None
            if self.opt_camera.isChecked():
                camera_dict = {
                    'enabled': True,
                    'focal_length_mm': self.camera_focal_length.value(),
                    'enable_depth_of_field': self.camera_enable_dof.isChecked(),
                    'fstop': self.camera_fstop.value(),
                    'clip_start_m': self.camera_clip_start.value(),
                    'clip_end_m': self.camera_clip_end.value(),
                    'overview_height_m': self.camera_overview_height.value(),
                    'overview_distance_m': self.camera_overview_distance.value(),
                    'swoop_height_m': self.camera_swoop_height.value(),
                    'water_entry_depth_m': self.camera_water_depth.value(),
                    'phase1_percent': self.camera_phase1_pct.value(),
                    'phase2_percent': self.camera_phase2_pct.value(),
                }

            job = PipelineJob(
                blender=Path(self.blender.text().strip()),
                model=self.info.path,
                output=Path(self.output.text().strip()),
                membrane_ids=self.selected_ids(),
                beam_ids=self.selected_beam_ids(),
                truss_ids=self.selected_truss_ids(),
                cap_openings=self.caps.isChecked(),
                pin_top=self.pins.isChecked(),
                frames=self.frames.value(),
                environment=env_dict,
                replay=replay_dict,
                fish_schooling=schooling_dict,
                feed_animation=feed_dict,
                fish_feeding=feeding_dict,
                cinematic_camera=camera_dict,
            )

            program, args = job.command()

            if job.output.exists() and QMessageBox.question(
                self, 'Replace scene?',
                f'Replace this existing scene?\n{job.output}',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

            job.output.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = job.output.with_suffix('.build.log').open('w', encoding='utf-8')
            self.previous_stamp = job.output.stat().st_mtime_ns if job.output.exists() else None
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Check build settings', str(exc))
            return

        self.job = job
        self.cancelled = False
        self.last_output = None
        self._save_current_settings()

        self.log.clear()
        self.pending_line = ''
        self.decoder.reset()
        self.set_running(True)
        self.status.setText('Starting Blender…')
        self.progress.setRange(0, 0)
        self.log_note.setText('Build log: ' + str(job.output.with_suffix('.build.log')))

        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONIOENCODING', 'utf-8')
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.start(program, args)

    def set_running(self, value):
        self.running = value
        self.main_split.widget(0).setEnabled(not value)
        self.main_split.widget(1).setEnabled(not value)
        self.build_button.setEnabled(not value and self.info is not None and (not self.needs_enclosure() or bool(self.selected_ids())))
        self.cancel_button.setEnabled(value)
        self.open_button.setEnabled(not value and self.last_output is not None)
        self.folder_button.setEnabled(not value and self.job is not None)

    def consume_output(self, text):
        if not text:
            return
        if self.log_file:
            self.log_file.write(text)
            self.log_file.flush()
        text = text.replace('\r', '\n')
        self.pending_line += text
        lines = self.pending_line.split('\n')
        self.pending_line = lines.pop()
        for line in lines:
            if not line:
                continue
            self.log.appendPlainText(line)
            match = re.search(r'Validated \d+.* fish at frame (\d+)/(\d+)', line)
            if match:
                frame, total = map(int, match.groups())
                self.progress.setRange(0, total)
                self.progress.setValue(frame)
                self.status.setText(f'Animating salmon · frame {frame} of {total}')
            elif line.startswith('GUI_STAGE:'):
                self.status.setText(line.removeprefix('GUI_STAGE:').strip())
                self.progress.setRange(0, 0)
            elif 'Baking cloth:' in line or 'Simulating cage cloth' in line:
                self.status.setText('Simulating cage net cloth…')
            elif 'Saved as' in line or 'Saving scene' in line:
                self.status.setText('Saving Blender scene…')

    def read_output(self):
        self.consume_output(self.decoder.decode(bytes(self.process.readAllStandardOutput())))

    def finished(self, code, exit_status):
        self.cancel_timer.stop()
        self.read_output()
        self.consume_output(self.decoder.decode(b'', final=True) + '\n')
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        if not self.running:
            return
        success = (
            not self.cancelled and code == 0 and exit_status == QProcess.ExitStatus.NormalExit
            and self.job.output.is_file() and self.job.output.stat().st_mtime_ns != self.previous_stamp
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        if success:
            self.last_output = self.job.output.resolve()
            self.last_blender = executable_path(self.job.blender)
            self.status.setText('Scene ready. Open it in Blender to view and play.')
        elif self.cancelled:
            self.status.setText('Build cancelled.')
        else:
            self.status.setText(f'Build failed (exit {code}). Read the log, adjust settings, and retry.')
        self.set_running(False)

    def process_error(self, error):
        if error != QProcess.ProcessError.FailedToStart:
            return
        self.status.setText('Could not start Blender. Check its executable path in Advanced settings.')
        self.log.appendPlainText(self.process.errorString())
        if self.log_file:
            self.log_file.write(self.process.errorString())
            self.log_file.close()
            self.log_file = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.set_running(False)

    def cancel(self):
        if not self.running:
            return
        self.cancelled = True
        self.status.setText('Stopping Blender…')
        self.cancel_button.setEnabled(False)
        self.process.terminate()
        self.cancel_timer.start(2000)

    def open_scene(self):
        if self.last_output:
            ok, _ = QProcess.startDetached(str(self.last_blender), [str(self.last_output)], str(PROJECT_ROOT))
            if not ok:
                QMessageBox.warning(self, 'Could not open Blender', 'Check the Blender installation and try again.')

    def visualize_spreader_waterline(self):
        blender_path = (self.blender_edit.text().strip() if hasattr(self, 'blender_edit') else '') or find_blender()
        if not blender_path or not Path(blender_path).is_file():
            QMessageBox.warning(self, 'Blender Not Found', 'Please configure the Blender executable path in Advanced settings.')
            return

        script_path = PROJECT_ROOT / 'scripts' / 'blender' / 'blender_spreader_waterline.py'
        if not script_path.is_file():
            QMessageBox.warning(self, 'Script Not Found', f'Could not find {script_path}')
            return

        move_obj = self.spreader_move_edit.text().strip() if hasattr(self, 'spreader_move_edit') else ''
        still_obj = self.spreader_still_edit.text().strip() if hasattr(self, 'spreader_still_edit') else ''
        z_offset = str(self.spreader_z_offset.value() if hasattr(self, 'spreader_z_offset') else 0.52)
        heave_rao = str(self.spreader_heave_rao.value() if hasattr(self, 'spreader_heave_rao') else 0.5)
        water_level = str(self.feed_water_level.value() if hasattr(self, 'feed_water_level') else 0.0)
        wave_height = str(self.env_wave_height.value() if (hasattr(self, 'opt_env') and self.opt_env.isChecked() and hasattr(self, 'env_wave_height')) else 0.0)

        args = [
            '--python', str(script_path),
            '--',
            '--move-obj', move_obj,
            '--still-obj', still_obj,
            '--z-offset', z_offset,
            '--water-level', water_level,
            '--heave-rao', heave_rao,
            '--wave-height', wave_height,
        ]

        ok, _ = QProcess.startDetached(str(blender_path), args, str(PROJECT_ROOT))
        if ok:
            self.status.setText(f'Launched Blender for spreader waterline calibration (Lift: +{z_offset} m)')
        else:
            QMessageBox.warning(self, 'Launch Failed', 'Could not launch Blender for waterline calibration.')

    def open_folder(self):
        if self.job:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.job.output.resolve().parent)))

    def closeEvent(self, event):
        if self.running:
            QMessageBox.information(self, 'Build running', 'Cancel the build before closing this window.')
            event.ignore()
            return
        if self.workers:
            self.status.setText('Finishing model inspection. Please close again in a moment.')
            event.ignore()
            return
        self._save_current_settings()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Sim2Blender')
    app.setStyle('Fusion')
    app.setPalette(light_palette())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
