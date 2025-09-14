import sys
import os
import vlc
import json
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QFileDialog, QListWidget, QListWidgetItem,
                               QCheckBox, QLabel, QLineEdit, QProgressBar,
                               QFrame, QSplitter, QGroupBox, QSpinBox, QMessageBox,
                               QApplication, QHeaderView, QTableWidget, QTableWidgetItem, QSlider)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QPalette, QColor

from processing import VideoProcessor, ClipType

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("智能视频剪辑助手")
        self.setGeometry(100, 100, 1200, 800)

        # --- Data ---
        self.video_path = ""
        self.clips = []
        self.filler_words = ["嗯", "那个", "就是", "然后", "这个" ]
        self.silence_threshold = 0.8
        
        # --- Config ---
        self.config_file = "video_editor_config.json"
        self.load_config()

        # --- VLC Instance ---
        self.vlc_instance = vlc.Instance()
        self.media_player = self.vlc_instance.media_player_new()

        # --- CUDA Status Check ---
        self.cuda_available = self.check_cuda_status()

        self.setup_ui()
        self.processor_thread = None

    def setup_ui(self):
        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Section: File selection and controls
        top_controls_layout = QHBoxLayout()
        self.select_video_btn = QPushButton("选择视频文件")
        self.select_video_btn.clicked.connect(self.select_video)
        self.video_path_label = QLabel("未选择文件")
        self.video_path_label.setStyleSheet("font-style: italic; color: grey;")
        self.start_analysis_btn = QPushButton("开始分析")
        self.start_analysis_btn.clicked.connect(self.start_analysis)
        self.start_analysis_btn.setEnabled(False)

        top_controls_layout.addWidget(self.select_video_btn)
        top_controls_layout.addWidget(self.video_path_label, 1)
        top_controls_layout.addWidget(self.start_analysis_btn)
        main_layout.addLayout(top_controls_layout)

        # Middle Section: Splitter for Player and Clip List
        splitter = QSplitter(Qt.Horizontal)

        # --- Left Side: Player and Settings ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Video Player
        self.video_frame = QFrame()
        self.video_frame.setFrameShape(QFrame.Box)
        self.video_frame.setFrameShadow(QFrame.Sunken)
        palette = self.video_frame.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.video_frame.setPalette(palette)
        self.video_frame.setAutoFillBackground(True)
        left_layout.addWidget(self.video_frame, 1)
        
        # Video Controls
        controls_layout = QHBoxLayout()
        
        # Play/Pause button
        self.play_pause_btn = QPushButton("▶ 播放")
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        self.play_pause_btn.setEnabled(False)
        controls_layout.addWidget(self.play_pause_btn)
        
        # Stop button
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self.stop_video)
        self.stop_btn.setEnabled(False)
        controls_layout.addWidget(self.stop_btn)
        
        # Time display
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setStyleSheet("font-family: monospace; color: #666;")
        controls_layout.addWidget(self.time_label, 1)
        
        # Progress slider
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.sliderPressed.connect(self.on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self.on_slider_released)
        self.progress_slider.setEnabled(False)
        controls_layout.addWidget(self.progress_slider)
        
        left_layout.addLayout(controls_layout)
        
        # Timer for updating time display
        from PySide6.QtCore import QTimer
        self.time_update_timer = QTimer()
        self.time_update_timer.timeout.connect(self.update_time_display)
        self.time_update_timer.start(100)  # Update every 100ms
        
        self.slider_pressed = False

        # Settings Box
        settings_box = QGroupBox("分析设置")
        settings_layout = QVBoxLayout()
        
        # CUDA Status
        cuda_status_text = "✅ CUDA加速可用" if self.cuda_available else "❌ CUDA加速不可用 (仅使用CPU)"
        cuda_status_color = "green" if self.cuda_available else "red"
        cuda_status_label = QLabel(f"GPU加速状态: {cuda_status_text}")
        cuda_status_label.setStyleSheet(f"color: {cuda_status_color}; font-weight: bold;")
        settings_layout.addWidget(cuda_status_label)
        
        # Silence threshold
        silence_layout = QHBoxLayout()
        silence_label = QLabel("静音片段时长 (秒) 大于:")
        self.silence_threshold_input = QLineEdit(str(self.silence_threshold))
        self.silence_threshold_input.textChanged.connect(self.save_config)
        silence_layout.addWidget(silence_label)
        silence_layout.addWidget(self.silence_threshold_input)
        settings_layout.addLayout(silence_layout)

        # Filler words
        filler_label = QLabel("无用词列表 (用逗号分隔):")
        self.filler_words_input = QLineEdit(", ".join(self.filler_words))
        self.filler_words_input.textChanged.connect(self.save_config)
        settings_layout.addWidget(filler_label)
        settings_layout.addWidget(self.filler_words_input)
        
        # Preview controls
        preview_layout = QHBoxLayout()
        self.preview_btn = QPushButton("预览剪辑效果")
        self.preview_btn.clicked.connect(self.preview_clips)
        self.preview_btn.setEnabled(False)
        self.stop_preview_btn = QPushButton("停止预览")
        self.stop_preview_btn.clicked.connect(self.stop_preview)
        self.stop_preview_btn.setEnabled(False)
        preview_layout.addWidget(self.preview_btn)
        preview_layout.addWidget(self.stop_preview_btn)
        settings_layout.addLayout(preview_layout)
        
        settings_box.setLayout(settings_layout)
        left_layout.addWidget(settings_box)
        
        # Preview variables
        self.preview_mode = False
        self.preview_timer = None
        self.preview_clips = []
        self.current_preview_index = 0

        splitter.addWidget(left_panel)

        # --- Right Side: Clip List ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Search and Select controls
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.search_input.textChanged.connect(self.filter_list)
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("全不选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.select_all_btn)
        search_layout.addWidget(self.deselect_all_btn)
        right_layout.addLayout(search_layout)

        # Clip table with pagination
        self.clip_table = QTableWidget()
        self.clip_table.setColumnCount(5)
        self.clip_table.setHorizontalHeaderLabels(["删除", "类型", "内容", "开始", "结束"])
        self.clip_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.clip_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.clip_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.clip_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.clip_table.cellClicked.connect(self.on_clip_selected)
        
        # Pagination controls
        pagination_layout = QHBoxLayout()
        self.prev_page_btn = QPushButton("上一页")
        self.prev_page_btn.clicked.connect(self.prev_page)
        self.next_page_btn = QPushButton("下一页")
        self.next_page_btn.clicked.connect(self.next_page)
        self.page_label = QLabel("第 1 页，共 1 页")
        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(10, 1000)
        self.page_size_spin.setValue(100)
        self.page_size_spin.setSuffix(" 条/页")
        self.page_size_spin.valueChanged.connect(self.update_pagination)
        
        pagination_layout.addWidget(self.prev_page_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_page_btn)
        pagination_layout.addWidget(QLabel("每页显示:"))
        pagination_layout.addWidget(self.page_size_spin)
        pagination_layout.addStretch()
        
        right_layout.addWidget(self.clip_table)
        right_layout.addLayout(pagination_layout)
        
        # Pagination variables
        self.current_page = 1
        self.page_size = 100
        self.total_pages = 1

        splitter.addWidget(right_panel)
        splitter.setSizes([600, 600]) # Initial size split
        main_layout.addWidget(splitter, 1)

        # Bottom Section: Progress and Export
        bottom_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("准备就绪")
        self.generate_video_btn = QPushButton("生成视频")
        self.generate_video_btn.clicked.connect(self.generate_video)
        self.generate_video_btn.setEnabled(False)

        bottom_layout.addWidget(self.status_label, 1)
        bottom_layout.addWidget(self.progress_bar, 1)
        bottom_layout.addWidget(self.generate_video_btn)
        main_layout.addLayout(bottom_layout)
        
        # Statistics Section
        stats_box = QGroupBox("统计分析")
        stats_layout = QVBoxLayout()
        
        self.stats_label = QLabel("暂无统计数据")
        self.stats_label.setStyleSheet("color: #666; font-style: italic;")
        stats_layout.addWidget(self.stats_label)
        
        stats_box.setLayout(stats_layout)
        main_layout.addWidget(stats_box)

        # VLC setup
        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == 'win32':
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == 'darwin':
            self.media_player.set_nsobject(self.video_frame.winId())

    def select_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "Video Files (*.mp4 *.mov *.avi *.mkv)"
        )
        if path:
            self.video_path = path
            self.video_path_label.setText(os.path.basename(path))
            self.start_analysis_btn.setEnabled(True)
            self.play_video()
            # 启用播放控制按钮
            self.play_pause_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            self.progress_slider.setEnabled(True)

    def play_video(self):
        if not self.video_path:
            return
        media = self.vlc_instance.media_new(self.video_path)
        self.media_player.set_media(media)
        self.media_player.play()
        # 等待媒体加载完成后暂停
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self.media_player.pause())

    def start_analysis(self):
        if not self.video_path:
            return
        
        self.start_analysis_btn.setEnabled(False)
        self.generate_video_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("正在分析视频...")
        self.clip_table.setRowCount(0) # Clear previous results

        # Get settings from UI
        try:
            silence_threshold = float(self.silence_threshold_input.text())
        except ValueError:
            QMessageBox.warning(self, "输入错误", "静音时长必须是有效的数字。")
            self.start_analysis_btn.setEnabled(True)
            return
            
        filler_words = [word.strip() for word in self.filler_words_input.text().split(',') if word.strip()]
        
        self.processor_thread = VideoProcessor(self.video_path, filler_words, silence_threshold)
        self.processor_thread.progress.connect(self.update_progress)
        self.processor_thread.status.connect(self.update_status)
        self.processor_thread.finished.connect(self.on_analysis_finished)
        self.processor_thread.error.connect(self.on_error)
        self.processor_thread.start()

    @Slot(int, str, str)
    def update_progress(self, value, text, eta):
        self.progress_bar.setValue(value)
        # 显示进度文本和预计剩余时间
        if eta and eta != "即将完成":
            self.status_label.setText(f"{text} | {eta}")
        else:
            self.status_label.setText(text)

    @Slot(str)
    def update_status(self, text):
        self.status_label.setText(text)

    @Slot(list)
    def on_analysis_finished(self, clips):
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"分析完成！找到 {len(clips)} 个待处理项。")
        self.start_analysis_btn.setEnabled(True)
        self.generate_video_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.clips = clips
        self.populate_clip_list()
        self.update_statistics()

    @Slot(str)
    def on_error(self, error_message):
        self.progress_bar.setVisible(False)
        self.status_label.setText("发生错误！")
        QMessageBox.critical(self, "处理错误", error_message)
        self.start_analysis_btn.setEnabled(True)

    def populate_clip_list(self):
        # 计算分页信息
        self.page_size = self.page_size_spin.value()
        self.total_pages = max(1, (len(self.clips) + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, self.total_pages)
        
        # 计算当前页的数据范围
        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.clips))
        current_page_clips = self.clips[start_idx:end_idx]
        
        # 清空表格并填充当前页数据
        self.clip_table.setRowCount(len(current_page_clips))
        for row, clip in enumerate(current_page_clips):
            # Checkbox item
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.clip_table.setCellWidget(row, 0, checkbox_widget)

            # Other items
            clip_type = "无用词" if clip.type == ClipType.FILLER else "静音"
            content = clip.content if clip.content else "---"
            start_time = f"{clip.start:.2f}"
            end_time = f"{clip.end:.2f}"

            self.clip_table.setItem(row, 1, QTableWidgetItem(clip_type))
            self.clip_table.setItem(row, 2, QTableWidgetItem(content))
            self.clip_table.setItem(row, 3, QTableWidgetItem(start_time))
            self.clip_table.setItem(row, 4, QTableWidgetItem(end_time))
        
        # 更新分页控件状态
        self.update_pagination_controls()
    
    def update_pagination_controls(self):
        """更新分页控件状态"""
        self.page_label.setText(f"第 {self.current_page} 页，共 {self.total_pages} 页")
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < self.total_pages)
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.populate_clip_list()
    
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.populate_clip_list()
    
    def update_pagination(self):
        """更新分页设置"""
        self.current_page = 1  # 重置到第一页
        self.populate_clip_list()
    
    @Slot(int, int)
    def on_clip_selected(self, row, column):
        # 计算实际clip索引（考虑分页）
        actual_idx = (self.current_page - 1) * self.page_size + row
        if actual_idx < len(self.clips):
            start_time_ms = self.clips[actual_idx].start * 1000
            self.media_player.set_time(int(start_time_ms))
            if not self.media_player.is_playing():
                self.media_player.play()
                self.play_pause_btn.setText("⏸ 暂停")

    def filter_list(self):
        search_text = self.search_input.text().lower()
        visible_count = 0
        for i in range(self.clip_table.rowCount()):
            content_item = self.clip_table.item(i, 2)
            if content_item and search_text in content_item.text().lower():
                self.clip_table.setRowHidden(i, False)
                visible_count += 1
            else:
                self.clip_table.setRowHidden(i, True)
        
        # 如果当前页没有可见结果，自动跳转到有结果的页面
        if visible_count == 0 and search_text:
            self.search_for_results(search_text)
    
    def search_for_results(self, search_text):
        """搜索包含结果的页面并跳转"""
        for page in range(1, self.total_pages + 1):
            start_idx = (page - 1) * self.page_size
            end_idx = min(start_idx + self.page_size, len(self.clips))
            
            for i in range(start_idx, end_idx):
                clip = self.clips[i]
                content = clip.content if clip.content else ""
                if search_text in content.lower():
                    self.current_page = page
                    self.populate_clip_list()
                    return

    def select_all(self):
        """选择当前页所有项"""
        for i in range(self.clip_table.rowCount()):
            if not self.clip_table.isRowHidden(i):
                self.clip_table.cellWidget(i, 0).findChild(QCheckBox).setChecked(True)
    
    def deselect_all(self):
        """取消选择当前页所有项"""
        for i in range(self.clip_table.rowCount()):
            if not self.clip_table.isRowHidden(i):
                self.clip_table.cellWidget(i, 0).findChild(QCheckBox).setChecked(False)
    
    def select_all_pages(self):
        """选择所有页面的所有项"""
        reply = QMessageBox.question(self, "确认", "确定要选择所有页面的所有项吗？", 
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 遍历所有页面，选择所有项
            for page in range(1, self.total_pages + 1):
                start_idx = (page - 1) * self.page_size
                end_idx = min(start_idx + self.page_size, len(self.clips))
                for i in range(start_idx, end_idx):
                    # 这里需要设置所有clip为选中状态
                    # 由于clip对象本身没有选中状态，我们需要在内存中维护一个选中状态列表
                    pass
            # 刷新当前页面显示
            self.populate_clip_list()

    def generate_video(self):
        if not self.video_path or not self.clips:
            return

        clips_to_remove = []
        for i in range(self.clip_table.rowCount()):
            checkbox = self.clip_table.cellWidget(i, 0).findChild(QCheckBox)
            if checkbox.isChecked():
                clips_to_remove.append(self.clips[i])
        
        if not clips_to_remove:
            QMessageBox.information(self, "提示", "没有选择任何要删除的片段。")
            return

        # Output path
        path, ext = os.path.splitext(self.video_path)
        output_path = f"{path}_final{ext}"

        # Disable buttons
        self.generate_video_btn.setEnabled(False)
        self.start_analysis_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.processor_thread = VideoProcessor(self.video_path)
        self.processor_thread.clips_to_remove = clips_to_remove
        self.processor_thread.output_path = output_path
        self.processor_thread.mode = 'export'
        
        self.processor_thread.progress.connect(self.update_progress)
        self.processor_thread.finished_export.connect(self.on_export_finished)
        self.processor_thread.error.connect(self.on_error)
        self.processor_thread.start()

    @Slot(str)
    def on_export_finished(self, output_path):
        self.progress_bar.setVisible(False)
        self.status_label.setText("视频生成成功！")
        self.generate_video_btn.setEnabled(True)
        self.start_analysis_btn.setEnabled(True)
        QMessageBox.information(self, "完成", f"精简后的视频已保存到:\n{output_path}")


    def check_cuda_status(self):
        """检查CUDA是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def preview_clips(self):
        """预览剪辑效果"""
        if not self.video_path or not self.clips:
            return
        
        # 获取选中的要删除的片段
        clips_to_remove = []
        for i in range(self.clip_table.rowCount()):
            checkbox = self.clip_table.cellWidget(i, 0).findChild(QCheckBox)
            if checkbox.isChecked():
                # 计算实际clip索引（考虑分页）
                actual_idx = (self.current_page - 1) * self.page_size + i
                if actual_idx < len(self.clips):
                    clips_to_remove.append(self.clips[actual_idx])
        
        if not clips_to_remove:
            QMessageBox.information(self, "提示", "请先选择要删除的片段进行预览。")
            return
        
        # 计算要保留的片段
        self.preview_clips = self.calculate_keep_clips(clips_to_remove)
        if not self.preview_clips:
            QMessageBox.warning(self, "警告", "没有可保留的视频片段。")
            return
        
        # 开始预览
        self.preview_mode = True
        self.current_preview_index = 0
        self.preview_btn.setEnabled(False)
        self.stop_preview_btn.setEnabled(True)
        self.status_label.setText("预览模式 - 正在播放剪辑后的效果...")
        
        # 播放第一个片段
        self.play_preview_clip()
    
    def calculate_keep_clips(self, clips_to_remove):
        """计算要保留的片段"""
        # 获取视频总时长
        media = self.vlc_instance.media_new(self.video_path)
        media.parse()
        duration = media.get_duration() / 1000.0  # 转换为秒
        
        # 按开始时间排序要删除的片段
        clips_to_remove.sort(key=lambda c: c.start)
        
        # 计算要保留的片段
        keep_clips = []
        last_end = 0.0
        
        for clip in clips_to_remove:
            if clip.start > last_end:
                keep_clips.append((last_end, clip.start))
            last_end = max(last_end, clip.end)
        
        # 添加最后一个片段
        if last_end < duration:
            keep_clips.append((last_end, duration))
        
        return keep_clips
    
    def play_preview_clip(self):
        """播放当前预览片段"""
        if not self.preview_mode or self.current_preview_index >= len(self.preview_clips):
            self.stop_preview()
            return
        
        start_time, end_time = self.preview_clips[self.current_preview_index]
        
        # 设置播放位置
        self.media_player.set_time(int(start_time * 1000))
        self.media_player.play()
        self.play_pause_btn.setText("⏸ 暂停")
        
        # 设置定时器在片段结束时停止
        if self.preview_timer:
            self.preview_timer.stop()
        
        from PySide6.QtCore import QTimer
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.on_preview_clip_end)
        # 计算片段持续时间（毫秒）
        duration_ms = int((end_time - start_time) * 1000)
        self.preview_timer.start(duration_ms)
        
        # 更新状态显示
        self.status_label.setText(f"预览片段 {self.current_preview_index + 1}/{len(self.preview_clips)}: {start_time:.2f}s - {end_time:.2f}s")
    
    def on_preview_clip_end(self):
        """预览片段结束时的处理"""
        self.current_preview_index += 1
        if self.current_preview_index < len(self.preview_clips):
            # 短暂暂停后播放下一个片段
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self.play_preview_clip)
        else:
            # 所有片段播放完毕
            self.stop_preview()
            QMessageBox.information(self, "预览完成", "剪辑效果预览已完成！")
    
    def stop_preview(self):
        """停止预览"""
        self.preview_mode = False
        if self.preview_timer:
            self.preview_timer.stop()
            self.preview_timer = None
        
        self.media_player.pause()
        self.play_pause_btn.setText("▶ 播放")
        self.preview_btn.setEnabled(True)
        self.stop_preview_btn.setEnabled(False)
        self.status_label.setText("预览已停止")
        self.current_preview_index = 0
        self.preview_clips = []

    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 加载无用词列表
                if 'filler_words' in config:
                    self.filler_words = config['filler_words']
                    
                # 加载静音阈值
                if 'silence_threshold' in config:
                    self.silence_threshold = config['silence_threshold']
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    def save_config(self):
        """保存配置文件"""
        try:
            # 从UI获取当前值
            try:
                self.silence_threshold = float(self.silence_threshold_input.text())
            except ValueError:
                self.silence_threshold = 0.8
                
            filler_words_text = self.filler_words_input.text()
            self.filler_words = [word.strip() for word in filler_words_text.split(',') if word.strip()]
            
            # 保存到配置文件
            config = {
                'filler_words': self.filler_words,
                'silence_threshold': self.silence_threshold
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")

    def update_statistics(self):
        """更新统计分析信息"""
        if not self.clips or not self.video_path:
            self.stats_label.setText("暂无统计数据")
            return
        
        try:
            # 获取视频总时长
            media = self.vlc_instance.media_new(self.video_path)
            media.parse()
            total_duration = media.get_duration() / 1000.0  # 转换为秒
            
            # 统计不同类型的片段
            filler_clips = [clip for clip in self.clips if clip.type == ClipType.FILLER]
            silence_clips = [clip for clip in self.clips if clip.type == ClipType.SILENCE]
            
            # 计算删除的总时长
            total_remove_duration = sum(clip.end - clip.start for clip in self.clips)
            filler_duration = sum(clip.end - clip.start for clip in filler_clips)
            silence_duration = sum(clip.end - clip.start for clip in silence_clips)
            
            # 计算保留的时长
            keep_duration = total_duration - total_remove_duration
            
            # 计算百分比
            remove_percentage = (total_remove_duration / total_duration * 100) if total_duration > 0 else 0
            keep_percentage = 100 - remove_percentage
            
            # 格式化时间显示
            def format_time(seconds):
                if seconds < 60:
                    return f"{seconds:.1f}秒"
                elif seconds < 3600:
                    minutes = int(seconds // 60)
                    secs = seconds % 60
                    return f"{minutes}分{secs:.1f}秒"
                else:
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = seconds % 60
                    return f"{hours}小时{minutes}分{secs:.1f}秒"
            
            # 构建统计信息文本
            stats_text = f"""<b>视频时长分析：</b><br/>
原始时长: {format_time(total_duration)}<br/>
删除时长: {format_time(total_remove_duration)} ({remove_percentage:.1f}%)<br/>
保留时长: {format_time(keep_duration)} ({keep_percentage:.1f}%)<br/><br/>
<b>删除片段统计：</b><br/>
无用词片段: {len(filler_clips)} 个，时长 {format_time(filler_duration)}<br/>
静音片段: {len(silence_clips)} 个，时长 {format_time(silence_duration)}<br/>
总计: {len(self.clips)} 个待处理片段"""
            
            self.stats_label.setText(stats_text)
            self.stats_label.setStyleSheet("")  # 移除斜体样式
            
        except Exception as e:
            self.stats_label.setText(f"统计计算失败: {e}")
            self.stats_label.setStyleSheet("color: red; font-style: italic;")

    def toggle_play_pause(self):
        """切换播放/暂停状态"""
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_pause_btn.setText("▶ 播放")
        else:
            self.media_player.play()
            self.play_pause_btn.setText("⏸ 暂停")
    
    def stop_video(self):
        """停止视频播放"""
        self.media_player.stop()
        self.play_pause_btn.setText("▶ 播放")
        # 重置到视频开头
        if self.video_path:
            self.media_player.set_media(self.vlc_instance.media_new(self.video_path))
    
    def update_time_display(self):
        """更新时间显示和进度条"""
        if not self.video_path or self.slider_pressed:
            return
        
        # 获取当前时间和总时长
        current_time = self.media_player.get_time() / 1000.0  # 转换为秒
        total_time = self.media_player.get_length() / 1000.0  # 转换为秒
        
        if total_time > 0:
            # 更新时间标签
            current_str = self.format_time_for_display(current_time)
            total_str = self.format_time_for_display(total_time)
            self.time_label.setText(f"{current_str} / {total_str}")
            
            # 更新进度条
            progress = (current_time / total_time) * 1000
            self.progress_slider.setValue(int(progress))
    
    def format_time_for_display(self, seconds):
        """格式化时间显示为 HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def on_slider_pressed(self):
        """进度条按下时的处理"""
        self.slider_pressed = True
    
    def on_slider_released(self):
        """进度条释放时的处理"""
        if self.video_path:
            # 获取总时长
            total_time = self.media_player.get_length() / 1000.0
            if total_time > 0:
                # 计算新的时间位置
                progress = self.progress_slider.value() / 1000.0
                new_time = progress * total_time
                # 设置播放位置
                self.media_player.set_time(int(new_time * 1000))
        self.slider_pressed = False

    def closeEvent(self, event):
        self.save_config()  # 关闭时保存配置
        self.media_player.stop()
        if self.preview_timer:
            self.preview_timer.stop()
        if hasattr(self, 'time_update_timer'):
            self.time_update_timer.stop()
        event.accept()