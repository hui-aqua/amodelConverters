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
from sim2blender.gui.model_job import PipelineJob, find_blender, inspect_model
from sim2blender.io.aquasim.results import inspect_results
from sim2blender.core.timeline import wave_timing


def light_palette():
    """Return the application's light palette, independent of the OS theme."""
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: '#f1f5f7',
        QPalette.ColorRole.WindowText: '#192d3b',
        QPalette.ColorRole.Base: '#ffffff',
        QPalette.ColorRole.AlternateBase: '#f1f5f7',
        QPalette.ColorRole.ToolTipBase: '#ffffff',
        QPalette.ColorRole.ToolTipText: '#192d3b',
        QPalette.ColorRole.Text: '#192d3b',
        QPalette.ColorRole.Button: '#e3edf2',
        QPalette.ColorRole.ButtonText: '#192d3b',
        QPalette.ColorRole.BrightText: '#ffffff',
        QPalette.ColorRole.Highlight: '#087e8b',
        QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.PlaceholderText: '#8998a1',
        QPalette.ColorRole.Link: '#087e8b',
        QPalette.ColorRole.Light: '#ffffff',
        QPalette.ColorRole.Midlight: '#edf3f6',
        QPalette.ColorRole.Mid: '#c6d5de',
        QPalette.ColorRole.Dark: '#8998a1',
        QPalette.ColorRole.Shadow: '#536875',
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#8998a1'))
    return palette


class Inspector(QThread):
    result = Signal(int, object, str)

    def __init__(self, path, token, parent):
        super().__init__(parent)
        self.path, self.token = path, token

    def run(self):
        try:
            self.result.emit(self.token, inspect_model(self.path), '')
        except Exception as exc:
            self.result.emit(self.token, None, str(exc))


class ResultsInspector(Inspector):
    def run(self):
        try:
            before = Path(self.path).stat()
            info = inspect_results(self.path, self.isInterruptionRequested)
            after = Path(self.path).stat()
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise ValueError('Results file changed during inspection; select it again when export finishes.')
            info['stamp'] = (after.st_mtime_ns, after.st_size)
            self.result.emit(self.token, info, '')
        except Exception as exc:
            self.result.emit(self.token, None, str(exc))


class MainWindow(QMainWindow):
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

        self.opt_replay = QCheckBox('AquaSim results replay')
        self.opt_schooling = QCheckBox('Simple fish schooling')
        self.opt_feed = QCheckBox('Feed animation')
        self.opt_feeding = QCheckBox('Fish feeding interaction')
        self.opt_camera = QCheckBox('Cinematic camera')

        stage_items = [
            (self.opt_replay, 0, 'Replaces cloth baking with out.txt displacements'),
            (self.opt_schooling, 1, 'Boid fish schooling contained in cage'),
            (self.opt_feed, 2, 'Spreader rotor (30 RPM) & ballistic feed pellets'),
            (self.opt_feeding, 3, 'Coupled schooling & feed pellet consumption'),
            (self.opt_camera, 4, 'Multi-phase cinematic tracking camera'),
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
        col2_title_box.addStretch()
        col2_layout.addLayout(col2_title_box)

        self.tab_config = QTabWidget()
        self.tab_config.setObjectName('ConfigTabs')
        col2_layout.addWidget(self.tab_config, 1)
        self.main_split.addWidget(col2_widget)

        # Build individual configuration tabs
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
        self.tab_config.setCurrentIndex(index)

    def update_tab_headers(self):
        titles = [
            ('🌊 Replay' + (' ✓' if self.opt_replay.isChecked() else ''), 0),
            ('🐟 Schooling' + (' ✓' if self.opt_schooling.isChecked() else ''), 1),
            ('🌀 Feed' + (' ✓' if self.opt_feed.isChecked() else ''), 2),
            ('🍴 Feeding' + (' ✓' if self.opt_feeding.isChecked() else ''), 3),
            ('🎥 Camera' + (' ✓' if self.opt_camera.isChecked() else ''), 4),
        ]
        for name, idx in titles:
            self.tab_config.setTabText(idx, name)

    # -------------------------------------------------------------
    # Configuration Tabs Construction
    # -------------------------------------------------------------
    def _build_tab_replay(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        gb_source = QGroupBox('AquaSim Results File & Wave Timing')
        f = QFormLayout(gb_source)
        self.results = QLineEdit()
        self.results.setPlaceholderText('Matching AquaSim text export (e.g. out.txt)')
        self.results.textChanged.connect(self.results_changed)
        f.addRow('Results File', self.path_row(self.results, self.browse_results))

        r_timing = QHBoxLayout()
        self.wave_period = QDoubleSpinBox()
        self.wave_period.setDecimals(4)
        self.wave_period.setRange(0.0001, 86400)
        self.wave_period.setValue(5.0)
        self.wave_period.setSuffix(' s')
        self.wave_period.valueChanged.connect(self.update_duration)
        self.frames_per_wave = QSpinBox()
        self.frames_per_wave.setRange(1, 1000000)
        self.frames_per_wave.setValue(40)
        self.frames_per_wave.valueChanged.connect(self.update_duration)
        self.fps = QSpinBox()
        self.fps.setRange(1, 240)
        self.fps.setValue(25)
        self.fps.valueChanged.connect(self.update_duration)
        r_timing.addWidget(QLabel('Wave Period:'))
        r_timing.addWidget(self.wave_period)
        r_timing.addWidget(QLabel('Frames/Wave:'))
        r_timing.addWidget(self.frames_per_wave)
        r_timing.addWidget(QLabel('Video FPS:'))
        r_timing.addWidget(self.fps)
        f.addRow('Wave Setup', r_timing)

        self.timing_summary = QLabel('Select a results file to calculate total time.')
        self.timing_summary.setWordWrap(True)
        f.addRow(self.timing_summary)
        v.addWidget(gb_source)

        gb_timeline = QGroupBox('Timeline & Scope Control')
        ft = QFormLayout(gb_timeline)
        self.replay_start_offset = QSpinBox()
        self.replay_start_offset.setRange(0, 100000)
        self.replay_start_offset.setValue(0)
        self.replay_max_samples = QSpinBox()
        self.replay_max_samples.setRange(0, 1000000)
        self.replay_max_samples.setValue(0)
        self.replay_max_samples.setToolTip('0 = all available samples')
        ft.addRow('Start Sample Offset', self.replay_start_offset)
        ft.addRow('Max Samples (0=all)', self.replay_max_samples)
        self.replay_loop = QCheckBox('Loop animation cycle')
        self.replay_loop.setChecked(False)
        ft.addRow('Cyclic Motion', self.replay_loop)
        v.addWidget(gb_timeline)

        v.addStretch()
        self.tab_config.addTab(tab, '🌊 Replay')

    def _build_tab_schooling(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        gb_pop = QGroupBox('Fish Population & Biological Dimensions')
        f = QFormLayout(gb_pop)
        self.fish_count = QSpinBox()
        self.fish_count.setRange(0, 100000)
        self.fish_count.setValue(1000)
        self.fish_count.setGroupSeparatorShown(True)
        f.addRow('Number of Fish', self.fish_count)

        self.fish_species = QLineEdit('Atlantic salmon')
        f.addRow('Species Name', self.fish_species)

        geom_row = QHBoxLayout()
        self.fish_length_mean = QDoubleSpinBox()
        self.fish_length_mean.setRange(0.05, 5.0)
        self.fish_length_mean.setDecimals(3)
        self.fish_length_mean.setValue(0.775)
        self.fish_length_mean.setSuffix(' m')
        self.fish_length_std = QDoubleSpinBox()
        self.fish_length_std.setRange(0.001, 1.0)
        self.fish_length_std.setDecimals(3)
        self.fish_length_std.setValue(0.05)
        self.fish_length_std.setSuffix(' m')
        geom_row.addWidget(QLabel('Mean Length μ:'))
        geom_row.addWidget(self.fish_length_mean)
        geom_row.addWidget(QLabel('Std Dev σ:'))
        geom_row.addWidget(self.fish_length_std)
        f.addRow('Body Length N(μ, σ²)', geom_row)

        self.fish_nominal_weight = QDoubleSpinBox()
        self.fish_nominal_weight.setRange(0.01, 50.0)
        self.fish_nominal_weight.setValue(5.0)
        self.fish_nominal_weight.setSuffix(' kg')
        f.addRow('Nominal Weight', self.fish_nominal_weight)
        v.addWidget(gb_pop)

        gb_kinematics = QGroupBox('Swimming Kinematics & Containment')
        fk = QFormLayout(gb_kinematics)
        self.fish_cruise_speed = QDoubleSpinBox()
        self.fish_cruise_speed.setRange(0.01, 10.0)
        self.fish_cruise_speed.setDecimals(2)
        self.fish_cruise_speed.setValue(0.85)
        self.fish_cruise_speed.setSuffix(' BL/s')
        fk.addRow('Cruise Speed', self.fish_cruise_speed)

        self.fish_seed = QSpinBox()
        self.fish_seed.setRange(0, 2147483647)
        self.fish_seed.setValue(7)
        fk.addRow('Random Seed', self.fish_seed)

        self.fish_wall_buffer = QDoubleSpinBox()
        self.fish_wall_buffer.setRange(0.0, 5.0)
        self.fish_wall_buffer.setValue(0.1)
        self.fish_wall_buffer.setSuffix(' m')
        fk.addRow('Net Wall Clearance', self.fish_wall_buffer)
        v.addWidget(gb_kinematics)

        gb_boid = QGroupBox('Boid Group Forces & Oscillations')
        fb = QFormLayout(gb_boid)
        self.fish_cohesion = QDoubleSpinBox()
        self.fish_cohesion.setRange(0.0, 1.0)
        self.fish_cohesion.setValue(0.08)
        fb.addRow('Cage Center Cohesion', self.fish_cohesion)

        self.fish_flow_direction = QComboBox()
        self.fish_flow_direction.addItems(['Counter-Clockwise (+Z)', 'Clockwise (-Z)'])
        fb.addRow('Rotational Flow Direction', self.fish_flow_direction)

        self.fish_vert_osc = QDoubleSpinBox()
        self.fish_vert_osc.setRange(0.0, 5.0)
        self.fish_vert_osc.setValue(0.35)
        self.fish_vert_osc.setSuffix(' m')
        fb.addRow('Vertical Oscillation Amplitude', self.fish_vert_osc)
        v.addWidget(gb_boid)

        v.addStretch()
        self.tab_config.addTab(tab, '🐟 Schooling')

    def _build_tab_feed(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        gb_models = QGroupBox('3D Spreader Models (OBJ)')
        fm = QFormLayout(gb_models)
        self.spreader_move_edit = QLineEdit(str(PROJECT_ROOT / 'examples/models/spreader_move.obj'))
        fm.addRow('Rotating Rotor OBJ', self.path_row(self.spreader_move_edit, self.browse_spreader_move))
        self.spreader_still_edit = QLineEdit(str(PROJECT_ROOT / 'examples/models/spreader_still.obj'))
        fm.addRow('Stationary Base OBJ', self.path_row(self.spreader_still_edit, self.browse_spreader_still))
        v.addWidget(gb_models)

        gb_rotor = QGroupBox('Rotor Kinematics & Discharge Flow')
        fr = QFormLayout(gb_rotor)
        r_flow = QHBoxLayout()
        self.feed_rpm = QDoubleSpinBox()
        self.feed_rpm.setRange(-300.0, 300.0)
        self.feed_rpm.setValue(-30.0)
        self.feed_rpm.setSuffix(' RPM')
        self.feed_mass_flow = QDoubleSpinBox()
        self.feed_mass_flow.setRange(0.1, 1000.0)
        self.feed_mass_flow.setValue(30.0)
        self.feed_mass_flow.setSuffix(' kg/min')
        r_flow.addWidget(QLabel('Rotor:'))
        r_flow.addWidget(self.feed_rpm)
        r_flow.addWidget(QLabel('Mass Flow:'))
        r_flow.addWidget(self.feed_mass_flow)
        fr.addRow('Discharge', r_flow)

        r_proxy = QHBoxLayout()
        self.feed_pellet_mass = QDoubleSpinBox()
        self.feed_pellet_mass.setDecimals(4)
        self.feed_pellet_mass.setRange(0.0001, 1.0)
        self.feed_pellet_mass.setValue(0.01)
        self.feed_pellet_mass.setSuffix(' kg')
        self.feed_lifetime = QDoubleSpinBox()
        self.feed_lifetime.setRange(1.0, 600.0)
        self.feed_lifetime.setValue(30.0)
        self.feed_lifetime.setSuffix(' s')
        r_proxy.addWidget(QLabel('Visual Mass:'))
        r_proxy.addWidget(self.feed_pellet_mass)
        r_proxy.addWidget(QLabel('Lifetime:'))
        r_proxy.addWidget(self.feed_lifetime)
        fr.addRow('Particle Proxy', r_proxy)
        v.addWidget(gb_rotor)

        gb_pellet = QGroupBox('Pellet Geometry & Morphology')
        fp = QFormLayout(gb_pellet)
        geom_row = QHBoxLayout()
        self.pellet_radius_mean = QDoubleSpinBox()
        self.pellet_radius_mean.setDecimals(4)
        self.pellet_radius_mean.setRange(0.0005, 0.1)
        self.pellet_radius_mean.setValue(0.005)
        self.pellet_radius_mean.setSuffix(' m')
        self.pellet_radius_std = QDoubleSpinBox()
        self.pellet_radius_std.setDecimals(5)
        self.pellet_radius_std.setRange(0.00001, 0.05)
        self.pellet_radius_std.setValue(0.0008)
        self.pellet_radius_std.setSuffix(' m')
        self.pellet_aspect_ratio = QDoubleSpinBox()
        self.pellet_aspect_ratio.setDecimals(2)
        self.pellet_aspect_ratio.setRange(0.5, 10.0)
        self.pellet_aspect_ratio.setValue(1.6)
        geom_row.addWidget(QLabel('Mean Radius:'))
        geom_row.addWidget(self.pellet_radius_mean)
        geom_row.addWidget(QLabel('Std Dev:'))
        geom_row.addWidget(self.pellet_radius_std)
        geom_row.addWidget(QLabel('Aspect L/D:'))
        geom_row.addWidget(self.pellet_aspect_ratio)
        fp.addRow('Dimensions', geom_row)
        v.addWidget(gb_pellet)

        gb_fluid = QGroupBox('Dual-Medium Fluid & Ballistic Physics')
        ff = QFormLayout(gb_fluid)
        eject_row = QHBoxLayout()
        self.feed_outward_speed = QDoubleSpinBox()
        self.feed_outward_speed.setDecimals(2)
        self.feed_outward_speed.setRange(0.0, 50.0)
        self.feed_outward_speed.setValue(1.0)
        self.feed_outward_speed.setSuffix(' m/s')
        self.feed_downward_speed = QDoubleSpinBox()
        self.feed_downward_speed.setDecimals(4)
        self.feed_downward_speed.setRange(0.0, 50.0)
        self.feed_downward_speed.setValue(0.001)
        self.feed_downward_speed.setSuffix(' m/s')
        eject_row.addWidget(QLabel('Radial Outward:'))
        eject_row.addWidget(self.feed_outward_speed)
        eject_row.addWidget(QLabel('Downward Vertical:'))
        eject_row.addWidget(self.feed_downward_speed)
        ff.addRow('Ejection Speed', eject_row)

        dens_row = QHBoxLayout()
        self.feed_pellet_density = QDoubleSpinBox()
        self.feed_pellet_density.setRange(500.0, 3000.0)
        self.feed_pellet_density.setValue(1100.0)
        self.feed_pellet_density.setSuffix(' kg/m³')
        self.feed_water_level = QDoubleSpinBox()
        self.feed_water_level.setRange(-50.0, 50.0)
        self.feed_water_level.setValue(0.0)
        self.feed_water_level.setSuffix(' m')
        dens_row.addWidget(QLabel('Pellet Density:'))
        dens_row.addWidget(self.feed_pellet_density)
        dens_row.addWidget(QLabel('Water Level Z:'))
        dens_row.addWidget(self.feed_water_level)
        ff.addRow('Density & Water Level', dens_row)

        drag_row = QHBoxLayout()
        self.feed_water_drag = QDoubleSpinBox()
        self.feed_water_drag.setRange(0.01, 5.0)
        self.feed_water_drag.setValue(0.85)
        self.feed_air_drag = QDoubleSpinBox()
        self.feed_air_drag.setRange(0.01, 5.0)
        self.feed_air_drag.setValue(0.47)
        drag_row.addWidget(QLabel('Water Cd:'))
        drag_row.addWidget(self.feed_water_drag)
        drag_row.addWidget(QLabel('Air Cd:'))
        drag_row.addWidget(self.feed_air_drag)
        ff.addRow('Drag Coefficients', drag_row)

        self.feed_seed = QSpinBox()
        self.feed_seed.setRange(0, 2147483647)
        self.feed_seed.setValue(30030)
        ff.addRow('Random Seed', self.feed_seed)
        v.addWidget(gb_fluid)

        v.addStretch()
        self.tab_config.addTab(tab, '🌀 Feed')

    def _build_tab_feeding(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        gb_sensing = QGroupBox('Sensory Detection & Ingestion Radii')
        fs = QFormLayout(gb_sensing)
        radii_row = QHBoxLayout()
        self.feeding_sensing_radius = QDoubleSpinBox()
        self.feeding_sensing_radius.setRange(0.1, 50.0)
        self.feeding_sensing_radius.setValue(2.5)
        self.feeding_sensing_radius.setSuffix(' m')
        self.feeding_ingestion_radius = QDoubleSpinBox()
        self.feeding_ingestion_radius.setRange(0.01, 5.0)
        self.feeding_ingestion_radius.setValue(0.22)
        self.feeding_ingestion_radius.setSuffix(' m')
        radii_row.addWidget(QLabel('Sensing Radius:'))
        radii_row.addWidget(self.feeding_sensing_radius)
        radii_row.addWidget(QLabel('Ingestion Radius:'))
        radii_row.addWidget(self.feeding_ingestion_radius)
        fs.addRow('Physical Radii', radii_row)

        self.feeding_attraction_weight = QDoubleSpinBox()
        self.feeding_attraction_weight.setRange(0.0, 1.0)
        self.feeding_attraction_weight.setValue(0.55)
        fs.addRow('Attraction Steering Weight', self.feeding_attraction_weight)
        v.addWidget(gb_sensing)

        gb_burst = QGroupBox('Sprint Dynamics & Satiety Model')
        fb = QFormLayout(gb_burst)
        self.feeding_burst_speed = QDoubleSpinBox()
        self.feeding_burst_speed.setRange(0.1, 20.0)
        self.feeding_burst_speed.setValue(2.0)
        self.feeding_burst_speed.setSuffix(' BL/s')
        fb.addRow('Burst Sprint Speed', self.feeding_burst_speed)

        self.feeding_cooldown = QDoubleSpinBox()
        self.feeding_cooldown.setRange(0.1, 300.0)
        self.feeding_cooldown.setValue(10.0)
        self.feeding_cooldown.setSuffix(' s')
        fb.addRow('Satiety Refractory Cooldown', self.feeding_cooldown)
        v.addWidget(gb_burst)

        gb_depth = QGroupBox('Depth Boundaries for Feeding')
        fd = QFormLayout(gb_depth)
        depth_row = QHBoxLayout()
        self.feeding_min_depth = QDoubleSpinBox()
        self.feeding_min_depth.setRange(-200.0, 0.0)
        self.feeding_min_depth.setValue(-25.0)
        self.feeding_min_depth.setSuffix(' m')
        self.feeding_max_depth = QDoubleSpinBox()
        self.feeding_max_depth.setRange(-50.0, 5.0)
        self.feeding_max_depth.setValue(0.0)
        self.feeding_max_depth.setSuffix(' m')
        depth_row.addWidget(QLabel('Min Depth Z:'))
        depth_row.addWidget(self.feeding_min_depth)
        depth_row.addWidget(QLabel('Max Depth Z:'))
        depth_row.addWidget(self.feeding_max_depth)
        fd.addRow('Active Feeding Depth Range', depth_row)
        v.addWidget(gb_depth)

        v.addStretch()
        self.tab_config.addTab(tab, '🍴 Feeding')

    def _build_tab_camera(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        v = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        gb_optics = QGroupBox('Camera Optics & Depth of Field')
        fo = QFormLayout(gb_optics)
        lens_row = QHBoxLayout()
        self.camera_focal_length = QDoubleSpinBox()
        self.camera_focal_length.setRange(10.0, 300.0)
        self.camera_focal_length.setValue(32.0)
        self.camera_focal_length.setSuffix(' mm')
        self.camera_enable_dof = QCheckBox('Depth of Field')
        self.camera_enable_dof.setChecked(True)
        self.camera_fstop = QDoubleSpinBox()
        self.camera_fstop.setRange(0.5, 32.0)
        self.camera_fstop.setValue(3.5)
        self.camera_fstop.setPrefix('f/')
        lens_row.addWidget(QLabel('Focal Length:'))
        lens_row.addWidget(self.camera_focal_length)
        lens_row.addWidget(self.camera_enable_dof)
        lens_row.addWidget(self.camera_fstop)
        fo.addRow('Lens & Aperture', lens_row)

        clip_row = QHBoxLayout()
        self.camera_clip_start = QDoubleSpinBox()
        self.camera_clip_start.setRange(0.01, 10.0)
        self.camera_clip_start.setValue(0.1)
        self.camera_clip_start.setSuffix(' m')
        self.camera_clip_end = QDoubleSpinBox()
        self.camera_clip_end.setRange(10.0, 5000.0)
        self.camera_clip_end.setValue(500.0)
        self.camera_clip_end.setSuffix(' m')
        clip_row.addWidget(QLabel('Clip Start:'))
        clip_row.addWidget(self.camera_clip_start)
        clip_row.addWidget(QLabel('Clip End:'))
        clip_row.addWidget(self.camera_clip_end)
        fo.addRow('Clipping Planes', clip_row)
        v.addWidget(gb_optics)

        gb_waypoints = QGroupBox('Multi-Phase Trajectory Waypoints')
        fw = QFormLayout(gb_waypoints)
        aerial_row = QHBoxLayout()
        self.camera_overview_height = QDoubleSpinBox()
        self.camera_overview_height.setRange(1.0, 500.0)
        self.camera_overview_height.setValue(52.0)
        self.camera_overview_height.setSuffix(' m')
        self.camera_overview_distance = QDoubleSpinBox()
        self.camera_overview_distance.setRange(1.0, 1000.0)
        self.camera_overview_distance.setValue(104.0)
        self.camera_overview_distance.setSuffix(' m')
        aerial_row.addWidget(QLabel('Overview Height Z:'))
        aerial_row.addWidget(self.camera_overview_height)
        aerial_row.addWidget(QLabel('Overview Dist:'))
        aerial_row.addWidget(self.camera_overview_distance)
        fw.addRow('Phase 1 Aerial', aerial_row)

        dive_row = QHBoxLayout()
        self.camera_swoop_height = QDoubleSpinBox()
        self.camera_swoop_height.setRange(0.1, 50.0)
        self.camera_swoop_height.setValue(2.6)
        self.camera_swoop_height.setSuffix(' m')
        self.camera_water_depth = QDoubleSpinBox()
        self.camera_water_depth.setRange(-100.0, 0.0)
        self.camera_water_depth.setValue(-3.5)
        self.camera_water_depth.setSuffix(' m')
        dive_row.addWidget(QLabel('Swoop Height:'))
        dive_row.addWidget(self.camera_swoop_height)
        dive_row.addWidget(QLabel('Underwater Dive Z:'))
        dive_row.addWidget(self.camera_water_depth)
        fw.addRow('Phase 2 & 3', dive_row)
        v.addWidget(gb_waypoints)

        gb_timeline = QGroupBox('Phase Timeline Percentages')
        ft = QFormLayout(gb_timeline)
        phase_row = QHBoxLayout()
        self.camera_phase1_pct = QDoubleSpinBox()
        self.camera_phase1_pct.setRange(0.05, 0.90)
        self.camera_phase1_pct.setValue(0.35)
        self.camera_phase2_pct = QDoubleSpinBox()
        self.camera_phase2_pct.setRange(0.10, 0.95)
        self.camera_phase2_pct.setValue(0.60)
        phase_row.addWidget(QLabel('Phase 1 End:'))
        phase_row.addWidget(self.camera_phase1_pct)
        phase_row.addWidget(QLabel('Phase 2 End:'))
        phase_row.addWidget(self.camera_phase2_pct)
        ft.addRow('Timeline Distribution', phase_row)
        v.addWidget(gb_timeline)

        v.addStretch()
        self.tab_config.addTab(tab, '🎥 Camera')

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
                f"Source frames: {timing['samples']:,} · {self.results_info['nodes_per_sample']:,} nodes/frame\n"
                f"Sample interval: {step:.6g} s\n"
                f"AquaSim time: {timing['duration_seconds']:.6g} s\n"
                f"Total video frames: {timing['video_frame_end']:,} ({timing['video_duration_seconds']:.4g} s at {self.fps.value()} fps)"
            )
        if self.opt_replay.isChecked():
            self.duration.setText(f'AquaSim replay ({self.fps.value()} fps)')
        else:
            self.duration.setText(f'{self.frames.value() / 24:.1f}s @ 24fps')

    def replay_toggled(self, checked):
        self.pins.setEnabled(not checked)
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
            self.spreader_move_edit.text() or str(PROJECT_ROOT / 'examples/models'),
            'Wavefront OBJ (*.obj);;All files (*)'
        )
        if path:
            self.spreader_move_edit.setText(path)

    def browse_spreader_still(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select spreader_still.obj',
            self.spreader_still_edit.text() or str(PROJECT_ROOT / 'examples/models'),
            'Wavefront OBJ (*.obj);;All files (*)'
        )
        if path:
            self.spreader_still_edit.setText(path)

    def browse_blender(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Blender executable',
            self.blender.text(),
            'Executables (*.exe);;All files (*)'
        )
        if path:
            self.blender.setText(path)

    def model_changed(self):
        self.token += 1
        self.info = None
        self.components.clear()
        self.warning.clear()
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
        self.model_summary.setText(f'{info.node_count:,} active nodes · {len(info.components)} membrane components')
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

    def selection_changed(self):
        ids = self.selected_ids()
        if self.info:
            key = 'membranes/' + hashlib.sha256(str(self.info.path).encode()).hexdigest()
            self.settings.setValue(key, [str(cid) for cid in ids])
        conflicts, involved = self.info.junctions(ids) if self.info else (0, [])
        if conflicts:
            self.warning.setText(
                f'{conflicts} edges are shared by more than two faces in components {", ".join(map(str, involved))}. '
                'Uncheck attached flaps/internal sheets to form an enclosing shell.'
            )
        else:
            self.warning.setText('Enclosing shell ready.' if ids else 'Select the enclosing walls and bottom.')

        ready = bool(self.info and ids and not conflicts)
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
        self.fish_cruise_speed.setValue(self.settings.value('fish_cruise_speed', 0.85, type=float))
        self.fish_seed.setValue(self.settings.value('fish_seed', 7, type=int))
        self.fish_wall_buffer.setValue(self.settings.value('fish_wall_buffer', 0.1, type=float))
        self.fish_cohesion.setValue(self.settings.value('fish_cohesion', 0.08, type=float))
        self.fish_flow_direction.setCurrentIndex(self.settings.value('fish_flow_direction', 0, type=int))
        self.fish_vert_osc.setValue(self.settings.value('fish_vert_osc', 0.35, type=float))

        # Feed
        self.opt_feed.setChecked(self.settings.value('opt_feed', False, type=bool))
        self.spreader_move_edit.setText(self.settings.value('spreader_move', str(PROJECT_ROOT / 'examples/models/spreader_move.obj')))
        self.spreader_still_edit.setText(self.settings.value('spreader_still', str(PROJECT_ROOT / 'examples/models/spreader_still.obj')))
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
        self.settings.setValue('fish_cruise_speed', self.fish_cruise_speed.value())
        self.settings.setValue('fish_seed', self.fish_seed.value())
        self.settings.setValue('fish_wall_buffer', self.fish_wall_buffer.value())
        self.settings.setValue('fish_cohesion', self.fish_cohesion.value())
        self.settings.setValue('fish_flow_direction', self.fish_flow_direction.currentIndex())
        self.settings.setValue('fish_vert_osc', self.fish_vert_osc.value())

        self.settings.setValue('opt_feed', self.opt_feed.isChecked())
        self.settings.setValue('spreader_move', self.spreader_move_edit.text())
        self.settings.setValue('spreader_still', self.spreader_still_edit.text())
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
            if self.info.junctions(self.selected_ids())[0]:
                raise ValueError('Remove overlapping membrane components first.')
            if not self.output.text().strip():
                raise ValueError('Choose where to save the scene.')

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
                    'wall_buffer_m': self.fish_wall_buffer.value(),
                    'cohesion_weight': self.fish_cohesion.value(),
                    'flow_direction': flow_dir_val,
                    'vertical_oscillation_m': self.fish_vert_osc.value(),
                }

            feed_dict = None
            if self.opt_feed.isChecked():
                feed_dict = {
                    'enabled': True,
                    'spreader_move_obj': self.spreader_move_edit.text().strip(),
                    'spreader_still_obj': self.spreader_still_edit.text().strip(),
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
                cap_openings=self.caps.isChecked(),
                pin_top=self.pins.isChecked(),
                frames=self.frames.value(),
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
        self.build_button.setEnabled(not value and self.info is not None and bool(self.selected_ids()))
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
            self.last_blender = self.job.blender.resolve()
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
