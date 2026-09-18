"""Desktop model-to-Blender workflow with asynchronous inspection and execution."""
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
    QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from sim2blender.core.paths import PROJECT_ROOT
from sim2blender.gui.model_job import ModelJob, ReplayJob, find_blender, inspect_model
from sim2blender.io.aquasim.results import inspect_results
from sim2blender.core.timeline import wave_timing


def light_palette():
    """Return the application's light palette, independent of the OS theme."""
    palette=QPalette()
    colors={
        QPalette.ColorRole.Window:'#f1f5f7',
        QPalette.ColorRole.WindowText:'#192d3b',
        QPalette.ColorRole.Base:'#ffffff',
        QPalette.ColorRole.AlternateBase:'#f1f5f7',
        QPalette.ColorRole.ToolTipBase:'#ffffff',
        QPalette.ColorRole.ToolTipText:'#192d3b',
        QPalette.ColorRole.Text:'#192d3b',
        QPalette.ColorRole.Button:'#e3edf2',
        QPalette.ColorRole.ButtonText:'#192d3b',
        QPalette.ColorRole.BrightText:'#ffffff',
        QPalette.ColorRole.Highlight:'#087e8b',
        QPalette.ColorRole.HighlightedText:'#ffffff',
        QPalette.ColorRole.PlaceholderText:'#8998a1',
        QPalette.ColorRole.Link:'#087e8b',
        QPalette.ColorRole.Light:'#ffffff',
        QPalette.ColorRole.Midlight:'#edf3f6',
        QPalette.ColorRole.Mid:'#c6d5de',
        QPalette.ColorRole.Dark:'#8998a1',
        QPalette.ColorRole.Shadow:'#536875',
    }
    for role,color in colors.items():palette.setColor(role,QColor(color))
    for role in (QPalette.ColorRole.WindowText,QPalette.ColorRole.Text,QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled,role,QColor('#8998a1'))
    return palette


class Inspector(QThread):
    result=Signal(int,object,str)

    def __init__(self,path,token,parent):
        super().__init__(parent)
        self.path,self.token=path,token

    def run(self):
        try:self.result.emit(self.token,inspect_model(self.path),'')
        except Exception as exc:self.result.emit(self.token,None,str(exc))


class ResultsInspector(Inspector):
    def run(self):
        try:
            before=Path(self.path).stat()
            info=inspect_results(self.path,self.isInterruptionRequested)
            after=Path(self.path).stat()
            if (before.st_mtime_ns,before.st_size)!=(after.st_mtime_ns,after.st_size):
                raise ValueError('Results file changed during inspection; select it again when the export is complete.')
            info['stamp']=(after.st_mtime_ns,after.st_size)
            self.result.emit(self.token,info,'')
        except Exception as exc:self.result.emit(self.token,None,str(exc))


class MainWindow(QMainWindow):
    def __init__(self,settings_path=None):
        super().__init__()
        # Fusion still inherits the Windows system palette. Pin this deliberately
        # light interface to a light palette so dark mode cannot leak through
        # unstyled container margins or native editor subcontrols.
        app=QApplication.instance()
        palette=light_palette()
        if app is not None:app.setPalette(palette)
        self.setPalette(palette)
        self.setWindowTitle('Sim2Blender — AquaSim scene builder')
        self.resize(1120,850)
        self.settings=QSettings(str(settings_path or PROJECT_ROOT/'output'/'gui-settings.ini'),QSettings.Format.IniFormat)
        self.info=None
        self.workers=[]
        self.token=0
        self.results_token=0
        self.results_info=None
        self.running=False
        self.cancelled=False
        self.last_output=None
        self.last_blender=None
        self.job=None
        self.suggested_output=None
        self.log_file=None
        self.decoder=codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.pending_line=''
        self.process=QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.cancel_timer=QTimer(self)
        self.cancel_timer.setSingleShot(True)
        self.cancel_timer.timeout.connect(self.process.kill)
        self.load_timer=QTimer(self)
        self.load_timer.setSingleShot(True)
        self.load_timer.setInterval(400)
        self.load_timer.timeout.connect(self.load_model)
        self.results_timer=QTimer(self);self.results_timer.setSingleShot(True);self.results_timer.setInterval(400)
        self.results_timer.timeout.connect(self.load_results)
        self._build_ui()
        self.count.setValue(self.settings.value('fish_count',1000,type=int))
        self.frames.setValue(self.settings.value('frames',120,type=int))
        self.blender.setText(self.settings.value('blender',find_blender()))
        self.results.setText(self.settings.value('results',''))
        self.fps.setValue(self.settings.value('replay_fps',25,type=int))
        self.frames_per_wave.setValue(self.settings.value('frames_per_wave',40,type=int))
        self.wave_period.setValue(self.settings.value('wave_period',self.settings.value('step_seconds',.125,type=float)*self.frames_per_wave.value(),type=float))
        self.add_fish.setChecked(self.settings.value('replay_add_fish',True,type=bool))
        self.workflow.setCurrentIndex(self.settings.value('workflow',0,type=int))
        self.workflow_changed()
        previous=self.settings.value('model','')
        if previous:self.model.setText(previous)

    def _build_ui(self):
        root=QWidget();root.setObjectName('AppRoot');self.setCentralWidget(root)
        layout=QVBoxLayout(root);layout.setContentsMargins(24,20,24,20);layout.setSpacing(16)
        title=QLabel('Sim2Blender');title.setObjectName('Title');layout.addWidget(title)
        subtitle=QLabel('AquaSim model → animated Blender scene');subtitle.setObjectName('Subtitle');layout.addWidget(subtitle)
        split=QSplitter();layout.addWidget(split,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(520)
        self.form=QWidget();self.form.setObjectName('FormPanel');left=QVBoxLayout(self.form);left.setContentsMargins(0,0,14,0);left.setSpacing(14)
        scroll.setWidget(self.form);split.addWidget(scroll)
        files=QGroupBox('1   Select inputs');f=QFormLayout(files)
        self.workflow=QComboBox();self.workflow.addItems(['Model → Blender physics + salmon','AquaSim results replay'])
        f.addRow('Workflow',self.workflow)
        self.model=QLineEdit();self.model.setPlaceholderText('Choose an AquaSim .amodel file')
        f.addRow('AquaSim model',self.path_row(self.model,self.browse_model))
        self.output=QLineEdit();self.output.setPlaceholderText('Where to save the Blender scene')
        f.addRow('Save scene as',self.path_row(self.output,self.browse_output))
        self.model_summary=QLabel('Select a model to inspect its active membrane components.');self.model_summary.setWordWrap(True)
        f.addRow(self.model_summary);left.addWidget(files)
        self.model.textChanged.connect(self.model_changed)
        self.replay_options=QGroupBox('Replay settings');rp=QFormLayout(self.replay_options)
        self.results=QLineEdit();self.results.setPlaceholderText('Matching AquaSim text export, e.g. out.txt')
        rp.addRow('Results file',self.path_row(self.results,self.browse_results))
        self.fps=QSpinBox();self.fps.setRange(1,240);self.fps.setValue(25)
        self.wave_period=QDoubleSpinBox();self.wave_period.setDecimals(6);self.wave_period.setRange(.000001,86400);self.wave_period.setValue(5);self.wave_period.setSuffix(' s')
        self.frames_per_wave=QSpinBox();self.frames_per_wave.setRange(1,1000000);self.frames_per_wave.setValue(40)
        self.frames_per_wave.setToolTip('AquaSim structural steps per wave cycle, not video frames. If both cycle endpoints are included, use intervals (sample count minus one).')
        rp.addRow('Wave period',self.wave_period);rp.addRow('Source frames / wave',self.frames_per_wave);rp.addRow('Video FPS',self.fps)
        self.timing_summary=QLabel('Select a results file to calculate total time.');self.timing_summary.setWordWrap(True);rp.addRow(self.timing_summary)
        self.add_fish=QCheckBox('Add salmon to the replay');self.add_fish.setChecked(True);rp.addRow(self.add_fish)
        replay_note=QLabel('Use the wave settings from AquaSim. Sample interval = period / source frames per wave. The first sample is time zero; fish and structure share this timeline.')
        replay_note.setWordWrap(True);rp.addRow(replay_note);left.addWidget(self.replay_options)
        self.enclosure=QGroupBox('2   Choose the enclosing net');enclosure=self.enclosure;e=QVBoxLayout(enclosure)
        help_label=QLabel('Select the cage walls and bottom. Exclude attached flaps and internal sheets.');help_label.setWordWrap(True);e.addWidget(help_label)
        self.components=QListWidget();self.components.setFixedHeight(105)
        self.components.itemChanged.connect(self.selection_changed);e.addWidget(self.components)
        self.warning=QLabel('');self.warning.setWordWrap(True);self.warning.setObjectName('Warning');e.addWidget(self.warning)
        self.caps=QCheckBox('Close planar openings for fish containment');self.caps.setChecked(True)
        self.caps.setToolTip('Adds invisible containment caps; does not add physical net material.')
        self.pins=QCheckBox('Support the top rim');self.pins.setChecked(True)
        self.pins.setToolTip('Adds top-rim cloth pins in addition to source supports.')
        e.addWidget(self.caps);e.addWidget(self.pins);left.addWidget(enclosure)
        self.school=QGroupBox('3   Fish and animation');school=self.school;s=QFormLayout(school);self.school_layout=s
        s.addRow(QLabel('Atlantic salmon · 77.5 cm · nominal 5 kg'))
        self.count=QSpinBox();self.count.setRange(0,100000);self.count.setValue(1000);self.count.setGroupSeparatorShown(True)
        self.frames=QSpinBox();self.frames.setRange(1,100000);self.frames.setValue(120)
        s.addRow('Number of salmon',self.count);s.addRow('Animation frames',self.frames)
        self.duration=QLabel();self.frames.valueChanged.connect(self.update_duration);self.update_duration();s.addRow(self.duration)
        self.method_note=QLabel();self.method_note.setWordWrap(True);s.addRow(self.method_note)
        left.addWidget(school)
        self.advanced_toggle=QPushButton('Advanced settings ▸');self.advanced_toggle.setCheckable(True)
        left.addWidget(self.advanced_toggle)
        self.advanced=QGroupBox();a=QFormLayout(self.advanced)
        self.blender=QLineEdit();a.addRow('Blender executable',self.path_row(self.blender,self.browse_blender))
        self.speed=QDoubleSpinBox();self.speed.setRange(0,20);self.speed.setDecimals(2);self.speed.setValue(.6);self.speed.setSuffix(' m/s')
        self.seed=QSpinBox();self.seed.setRange(0,2147483647);self.seed.setValue(7)
        a.addRow('Swimming speed',self.speed);a.addRow('Random seed',self.seed)
        self.advanced.setVisible(False);self.advanced_toggle.toggled.connect(self.advanced.setVisible);left.addWidget(self.advanced)
        left.addStretch()
        right=QWidget();right.setObjectName('StatusPanel');r=QVBoxLayout(right);r.setContentsMargins(12,0,0,0)
        status_title=QLabel('Build status');status_title.setObjectName('SectionTitle');r.addWidget(status_title)
        self.status=QLabel('Ready to select a model');self.status.setWordWrap(True);r.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);r.addWidget(self.progress)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(4000)
        self.log.setPlaceholderText('Blender progress and any errors will appear here.');r.addWidget(self.log,1)
        self.log_note=QLabel('A complete build log is saved beside the output scene.');self.log_note.setWordWrap(True);r.addWidget(self.log_note)
        self.open_button=QPushButton('Open scene in Blender');self.open_button.setEnabled(False);self.open_button.clicked.connect(self.open_scene);r.addWidget(self.open_button)
        self.folder_button=QPushButton('Show output folder');self.folder_button.setEnabled(False);self.folder_button.clicked.connect(self.open_folder);r.addWidget(self.folder_button)
        split.addWidget(right);split.setSizes([600,440])
        bottom=QHBoxLayout();bottom.addStretch()
        self.cancel_button=QPushButton('Cancel build');self.cancel_button.setEnabled(False);self.cancel_button.clicked.connect(self.cancel);bottom.addWidget(self.cancel_button)
        self.build_button=QPushButton('Build Blender scene');self.build_button.setObjectName('Primary');self.build_button.setEnabled(False)
        self.build_button.clicked.connect(self.start_build);bottom.addWidget(self.build_button);layout.addLayout(bottom)
        self.workflow.currentIndexChanged.connect(self.workflow_changed)
        self.add_fish.toggled.connect(self.workflow_changed)
        self.results.textChanged.connect(self.results_changed)
        self.fps.valueChanged.connect(self.update_duration)
        self.wave_period.valueChanged.connect(self.update_duration)
        self.frames_per_wave.valueChanged.connect(self.update_duration)
        self.setStyleSheet('''
            QMainWindow, QWidget#AppRoot, QWidget#FormPanel, QWidget#StatusPanel,
            QScrollArea, QScrollArea > QWidget > QWidget { background: #f1f5f7; }
            QWidget { color: #192d3b; font-family: "Segoe UI"; font-size: 13px; }
            QScrollArea { border: none; }
            QLabel#Title { font-size: 29px; font-weight: 700; color: #123e50; }
            QLabel#Subtitle { color: #536875; font-size: 15px; }
            QLabel#SectionTitle { font-size: 18px; font-weight: 600; }
            QLabel#Warning { color: #9a5515; }
            QGroupBox { background: white; border: 1px solid #d5e0e5; border-radius: 8px;
                        margin-top: 12px; padding: 17px 12px 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget { background: white; color: #192d3b;
                        border: 1px solid #c6d5de;
                        border-radius: 4px; padding: 6px; }
            QComboBox QAbstractItemView { background: white; color: #192d3b;
                        selection-background-color: #087e8b; selection-color: white; }
            QPlainTextEdit { background: #132733; color: #dce9ef; border-radius: 6px;
                            padding: 10px; font-family: Consolas; font-size: 12px; }
            QPushButton { background: #e3edf2; border: 1px solid #c9d9e2; border-radius: 5px; padding: 9px 14px; }
            QPushButton:hover { background: #d3e5ee; }
            QPushButton#Primary { background: #087e8b; color: white; font-weight: 600; padding: 12px 25px; }
            QPushButton:disabled { background: #e4e9ec; color: #8998a1; }
            QProgressBar { background: white; color: #192d3b; border: 1px solid #c6d5de;
                           border-radius: 4px; text-align: center; height: 20px; }
            QProgressBar::chunk { background: #42a5ad; }
        ''')

    def path_row(self,edit,callback):
        widget=QWidget();row=QHBoxLayout(widget);row.setContentsMargins(0,0,0,0)
        row.addWidget(edit,1);button=QPushButton('Browse…');button.clicked.connect(callback);row.addWidget(button)
        return widget

    def update_duration(self):
        step=self.wave_period.value()/self.frames_per_wave.value()
        if self.results_info:
            timing=wave_timing(self.results_info['samples'],self.wave_period.value(),self.frames_per_wave.value(),self.fps.value())
            self.timing_summary.setText(f"Source frames: {timing['samples']:,} · {self.results_info['nodes_per_sample']:,} nodes/frame\n"
                f"Sample interval: {step:.9g} s\n"
                f"Structural motion time: {timing['duration_seconds']:.9g} s\n"
                f"Video / fish frames: {timing['video_frame_end']:,} · clip length: {timing['video_duration_seconds']:.9g} s\n"
                f"Last sample at video frame {timing['last_sample_frame']:.9g}; final-frame hold {timing['final_hold_seconds']:.6g} s.")
        if self.workflow.currentIndex()==1:
            self.duration.setText(f'Same timeline as structural replay · {self.fps.value()} fps · {step:.9g} s per source sample')
        else:self.duration.setText(f'{self.frames.value()/24:.1f} seconds at 24 fps')

    def is_replay(self):
        return self.workflow.currentIndex()==1

    def needs_enclosure(self):
        return not self.is_replay() or self.add_fish.isChecked()

    def workflow_changed(self):
        replay=self.is_replay()
        self.replay_options.setVisible(replay)
        self.enclosure.setVisible(self.needs_enclosure())
        self.school.setVisible(self.needs_enclosure())
        self.pins.setVisible(not replay)
        self.school_layout.setRowVisible(self.frames,not replay)
        self.method_note.setText('Salmon follow the replayed enclosure. Membrane selection affects fish containment; all source components remain in the replay.' if replay else 'Blender cloth motion is illustrative; this workflow does not replay AquaSim simulation results.')
        self.update_duration();self.suggest_output();self.selection_changed()

    def suggest_output(self):
        if not self.info:return
        suffix='_replay_salmon' if self.is_replay() and self.add_fish.isChecked() else '_replay' if self.is_replay() else '_salmon'
        suggested=str(PROJECT_ROOT/'output'/f'{self.info.path.stem}{suffix}.blend')
        if not self.output.text() or self.output.text()==self.suggested_output:self.output.setText(suggested)
        self.suggested_output=suggested

    def browse_results(self):
        path,_=QFileDialog.getOpenFileName(self,'Select AquaSim results text export',self.results.text() or str(PROJECT_ROOT/'examples/models'),'AquaSim results (*.txt);;All files (*)')
        if path:self.results.setText(path)

    def results_changed(self):
        self.results_token+=1;self.results_info=None
        for worker in self.workers:
            if isinstance(worker,ResultsInspector):worker.requestInterruption()
        self.timing_summary.setText('Reading results frame count…' if self.results.text() else 'Select a results file to calculate total time.')
        self.results_timer.start();self.selection_changed()

    def load_results(self):
        self.results_timer.stop()
        path=self.results.text().strip()
        if not path or not Path(path).is_file():
            self.timing_summary.setText('Choose an existing AquaSim results text export.');return
        worker=ResultsInspector(path,self.results_token,self);self.workers.append(worker)
        worker.result.connect(self.results_loaded)
        worker.finished.connect(lambda:self.workers.remove(worker));worker.finished.connect(worker.deleteLater)
        worker.start()

    def results_loaded(self,token,info,error):
        if token!=self.results_token:return
        self.results_info=info
        if error:self.timing_summary.setText('Could not read results: '+error)
        else:self.update_duration()
        self.selection_changed()

    def browse_model(self):
        path,_=QFileDialog.getOpenFileName(self,'Select AquaSim model',self.model.text() or str(PROJECT_ROOT/'examples/models'),'AquaSim models (*.amodel)')
        if path:self.model.setText(path)

    def browse_output(self):
        path,_=QFileDialog.getSaveFileName(self,'Save Blender scene',self.output.text() or str(PROJECT_ROOT/'output'),'Blender scenes (*.blend)')
        if path:self.output.setText(path if path.lower().endswith('.blend') else path+'.blend')

    def browse_blender(self):
        path,_=QFileDialog.getOpenFileName(self,'Select Blender executable',self.blender.text(),'Executables (*.exe);;All files (*)')
        if path:self.blender.setText(path)

    def model_changed(self):
        self.token+=1;self.info=None;self.components.clear();self.warning.clear()
        self.build_button.setEnabled(False)
        self.model_summary.setText('Waiting to inspect model…')
        self.load_timer.start()

    def load_model(self):
        self.load_timer.stop()
        path=self.model.text().strip()
        if not path or not Path(path).is_file():
            self.model_summary.setText('Choose an existing .amodel file.');return
        self.model_summary.setText('Reading active components…')
        worker=Inspector(path,self.token,self)
        self.workers.append(worker)
        worker.result.connect(self.model_loaded)
        worker.finished.connect(lambda: self.workers.remove(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def model_loaded(self,token,info,error):
        if token!=self.token:return
        if error:
            self.model_summary.setText('Could not read model: '+error);return
        self.info=info
        self.model_summary.setText(f'{info.node_count:,} active nodes · {len(info.components)} membrane components')
        self.components.blockSignals(True)
        self.components.clear()
        key='membranes/'+hashlib.sha256(str(info.path).encode()).hexdigest()
        saved=self.settings.value(key,None)
        checked={str(cid) for cid in saved} if isinstance(saved,list) else None
        for comp in info.components:
            item=QListWidgetItem(f'{comp["id"]}  ·  {comp["name"]}  ({comp["faces"]:,} faces)')
            item.setData(Qt.ItemDataRole.UserRole,comp['id'])
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked is None or str(comp['id']) in checked else Qt.CheckState.Unchecked)
            self.components.addItem(item)
        self.components.blockSignals(False)
        self.output.clear();self.suggest_output()
        self.settings.setValue('model',str(info.path))
        self.selection_changed()

    def selected_ids(self):
        return [self.components.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.components.count())
                if self.components.item(i).checkState()==Qt.CheckState.Checked]

    def selection_changed(self):
        ids=self.selected_ids()
        if self.info:
            key='membranes/'+hashlib.sha256(str(self.info.path).encode()).hexdigest()
            self.settings.setValue(key,[str(cid) for cid in ids])
        conflicts,involved=self.info.junctions(ids) if self.info else (0,[])
        if conflicts:
            self.warning.setText(f'{conflicts} edges are shared by more than two faces in components {", ".join(map(str,involved))}. Uncheck attached flaps/internal sheets to form an enclosing shell.')
        else:self.warning.setText('The enclosing shell will be checked by Blender before simulation.' if ids else 'Select the enclosing walls and bottom.')
        ready=bool(self.info and (not self.needs_enclosure() or (ids and not conflicts)))
        if self.is_replay():ready=ready and self.results_info is not None
        self.build_button.setEnabled(bool(ready and not self.running))
        if not self.running:
            self.status.setText('Ready to build' if ready else 'Select a valid results file and wait for timing inspection' if self.is_replay() and self.results_info is None else 'Choose enclosing components')

    def start_build(self):
        if self.running:return
        try:
            if self.info is None:raise ValueError('Wait for the model to finish loading.')
            if self.needs_enclosure() and self.info.junctions(self.selected_ids())[0]:raise ValueError('Remove the overlapping membrane components first.')
            if not self.output.text().strip():raise ValueError('Choose where to save the scene.')
            if self.is_replay():
                if self.results_info is None:raise ValueError('Wait for a valid results file and its timing summary.')
                stamp=Path(self.results.text().strip()).stat()
                if (stamp.st_mtime_ns,stamp.st_size)!=self.results_info['stamp']:
                    self.results_changed()
                    raise ValueError('The results file changed. Its timing is being inspected again; review the updated summary before building.')
            job_type=ReplayJob if self.is_replay() else ModelJob
            extra=dict(results=Path(self.results.text().strip()),fps=self.fps.value(),wave_period=self.wave_period.value(),frames_per_wave=self.frames_per_wave.value(),add_fish=self.add_fish.isChecked()) if self.is_replay() else {}
            job=job_type(Path(self.blender.text().strip()),self.info.path,Path(self.output.text().strip()),
                         self.selected_ids(),self.count.value(),self.frames.value(),speed=self.speed.value(),
                         seed=self.seed.value(),cap_openings=self.caps.isChecked(),pin_top=self.pins.isChecked(),**extra)
            program,args=job.command()
            if job.output.exists() and QMessageBox.question(self,'Replace scene?',f'Replace this existing scene?\n{job.output}',
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            job.output.parent.mkdir(parents=True,exist_ok=True)
            self.log_file=job.output.with_suffix('.build.log').open('w',encoding='utf-8')
            self.previous_stamp=job.output.stat().st_mtime_ns if job.output.exists() else None
        except (ValueError,OSError) as exc:
            QMessageBox.warning(self,'Check build settings',str(exc));return
        self.job=job;self.cancelled=False;self.last_output=None
        self.settings.setValue('fish_count',job.fish_count);self.settings.setValue('frames',job.frames)
        self.settings.setValue('workflow',self.workflow.currentIndex())
        self.settings.setValue('results',self.results.text())
        self.settings.setValue('replay_fps',self.fps.value())
        self.settings.setValue('wave_period',self.wave_period.value());self.settings.setValue('frames_per_wave',self.frames_per_wave.value())
        self.settings.setValue('replay_add_fish',self.add_fish.isChecked())
        self.settings.setValue('blender',program);self.settings.sync()
        self.log.clear();self.pending_line='';self.decoder.reset()
        self.set_running(True);self.status.setText('Starting Blender…');self.progress.setRange(0,0)
        self.log_note.setText('Build log: '+str(job.output.with_suffix('.build.log')))
        env=QProcessEnvironment.systemEnvironment();env.insert('PYTHONIOENCODING','utf-8')
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.start(program,args)

    def set_running(self,value):
        self.running=value;self.form.setEnabled(not value)
        self.build_button.setEnabled(not value and self.info is not None and (not self.needs_enclosure() or bool(self.selected_ids())))
        self.cancel_button.setEnabled(value)
        self.open_button.setEnabled(not value and self.last_output is not None)
        self.folder_button.setEnabled(not value and self.job is not None)

    def consume_output(self,text):
        if not text:return
        if self.log_file:self.log_file.write(text);self.log_file.flush()
        text=text.replace('\r','\n')
        self.pending_line+=text
        lines=self.pending_line.split('\n');self.pending_line=lines.pop()
        for line in lines:
            if not line:continue
            self.log.appendPlainText(line)
            match=re.search(r'Validated \d+ fish at frame (\d+)/(\d+)',line)
            if match:
                frame,total=map(int,match.groups());self.progress.setRange(0,total);self.progress.setValue(frame)
                self.status.setText(f'Animating salmon · frame {frame} of {total}')
            elif line.startswith('GUI_STAGE:'):
                self.status.setText(line.removeprefix('GUI_STAGE:').strip());self.progress.setRange(0,0)
            elif line.startswith(('Replaying ','Replay timing:','Reading AquaSim')):self.status.setText(line)
            elif 'Baking rope' in line:self.status.setText(line)
            elif 'Baking cloth:' in line:self.status.setText('Simulating the cage net…')
            elif 'Saved as' in line:self.status.setText('Finishing scene…')

    def read_output(self):
        self.consume_output(self.decoder.decode(bytes(self.process.readAllStandardOutput())))

    def finished(self,code,exit_status):
        self.cancel_timer.stop();self.read_output()
        self.consume_output(self.decoder.decode(b'',final=True)+'\n')
        if self.log_file:self.log_file.close();self.log_file=None
        if not self.running:return
        success=(not self.cancelled and code==0 and exit_status==QProcess.ExitStatus.NormalExit
                 and self.job.output.is_file() and self.job.output.stat().st_mtime_ns!=self.previous_stamp)
        self.progress.setRange(0,100);self.progress.setValue(100 if success else 0)
        if success:
            self.last_output=self.job.output.resolve();self.last_blender=self.job.blender.resolve()
            self.status.setText('Scene ready. Open it in Blender to play the animation.')
        elif self.cancelled:self.status.setText('Build cancelled. Any incomplete output should be rebuilt.')
        else:self.status.setText(f'Build failed (exit {code}). Read the last error in the log, adjust settings, and retry.')
        self.set_running(False)

    def process_error(self,error):
        if error!=QProcess.ProcessError.FailedToStart:return
        self.status.setText('Could not start Blender. Check its executable path in Advanced settings.')
        self.log.appendPlainText(self.process.errorString())
        if self.log_file:self.log_file.write(self.process.errorString());self.log_file.close();self.log_file=None
        self.progress.setRange(0,100);self.progress.setValue(0);self.set_running(False)

    def cancel(self):
        if not self.running:return
        self.cancelled=True;self.status.setText('Stopping Blender…');self.cancel_button.setEnabled(False)
        self.process.terminate();self.cancel_timer.start(2000)

    def open_scene(self):
        if self.last_output:
            ok,_=QProcess.startDetached(str(self.last_blender),[str(self.last_output)],str(PROJECT_ROOT))
            if not ok:QMessageBox.warning(self,'Could not open Blender','Check the Blender installation and try again.')

    def open_folder(self):
        if self.job:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.job.output.resolve().parent)))

    def closeEvent(self,event):
        if self.running:
            QMessageBox.information(self,'Build running','Cancel the build before closing this window.');event.ignore();return
        if self.workers:
            self.status.setText('Finishing model inspection. Please close again in a moment.');event.ignore();return
        self.settings.sync();event.accept()


def main():
    app=QApplication(sys.argv);app.setApplicationName('Sim2Blender');app.setStyle('Fusion');app.setPalette(light_palette())
    window=MainWindow();window.show()
    sys.exit(app.exec())


if __name__=='__main__':main()
