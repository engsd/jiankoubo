import os
import time
from enum import Enum, auto
from dataclasses import dataclass
from PySide6.QtCore import QThread, Signal
import moviepy.editor as mp
from faster_whisper import WhisperModel

class WhisperModelManager:
    """Whisper模型单例管理器"""
    _instance = None
    _model = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_model(self, model_size="small"):
        """获取Whisper模型实例，如果未加载则进行加载"""
        if self._model is None:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            print(f"正在加载Whisper模型 (设备: {device}, 计算类型: {compute_type})...")
            self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
            print("Whisper模型加载完成")
        return self._model
    
    def clear_model(self):
        """清理模型实例，释放内存"""
        if self._model is not None:
            del self._model
            self._model = None
            import gc
            gc.collect()
            print("Whisper模型已清理")

class ClipType(Enum):
    FILLER = auto()
    SILENCE = auto()

@dataclass
class Clip:
    type: ClipType
    start: float
    end: float
    content: str = ""

class VideoProcessor(QThread):
    progress = Signal(int, str, str)  # 添加预计剩余时间参数
    status = Signal(str)
    finished = Signal(list)
    finished_export = Signal(str)
    error = Signal(str)

    def __init__(self, video_path, filler_words=None, silence_threshold=0.5, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.filler_words = filler_words if filler_words is not None else []
        self.silence_threshold = silence_threshold
        self.mode = 'analyze' # Can be 'analyze' or 'export'
        self.clips_to_remove = []
        self.output_path = ""
        self.start_time = None
        self.total_steps = 0
        self.current_step = 0

    def run(self):
        try:
            if self.mode == 'analyze':
                self.analyze()
            elif self.mode == 'export':
                self.export()
        except Exception as e:
            self.error.emit(f"发生未预料的错误: {e}")

    def analyze(self):
        audio_path = None
        video_clip = None
        try:
            self.start_time = time.time()
            self.total_steps = 100
            self.current_step = 0
            
            # 1. Audio Extraction
            self.current_step = 10
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "正在提取音频...", eta)
            video_clip = mp.VideoFileClip(self.video_path)
            audio_path = "temp_audio.wav"
            video_clip.audio.write_audiofile(audio_path)

            # 2. Transcription
            self.current_step = 30
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "正在进行语音转录 (这可能需要一些时间)...", eta)
            # 使用单例模型管理器，避免重复加载
            model_manager = WhisperModelManager()
            model = model_manager.get_model("small")
            segments, _ = model.transcribe(audio_path, word_timestamps=True)

            clips_found = []
            last_word_end = 0.0
            total_segments = len(list(segments))
            segments_processed = 0
            
            # 重新获取segments（因为前面的迭代已经消耗了生成器）
            segments, _ = model.transcribe(audio_path, word_timestamps=True)

            # 3. Filler and Silence Identification
            for segment in segments:
                segments_processed += 1
                progress_in_step = int(40 * (segments_processed / total_segments)) if total_segments > 0 else 0
                self.current_step = 30 + progress_in_step
                eta = self.calculate_eta(self.current_step)
                self.progress.emit(self.current_step, f"正在识别无用词和静音片段... ({segments_processed}/{total_segments})", eta)
                
                for word in segment.words:
                    # Check for silences
                    silence_duration = word.start - last_word_end
                    if silence_duration > self.silence_threshold:
                        clips_found.append(Clip(ClipType.SILENCE, last_word_end, word.start))
                    
                    # Check for filler words
                    if word.word.strip() in self.filler_words:
                        clips_found.append(Clip(ClipType.FILLER, word.start, word.end, word.word.strip()))
                    
                    last_word_end = word.end

            self.current_step = 100
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "分析完成！", eta)
            self.finished.emit(clips_found)

        except Exception as e:
            self.error.emit(f"分析失败: {e}")
        finally:
            # 清理临时文件
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as cleanup_error:
                    print(f"清理临时文件失败: {cleanup_error}")
            
            # 关闭视频剪辑对象
            if video_clip:
                try:
                    video_clip.close()
                except Exception as close_error:
                    print(f"关闭视频剪辑失败: {close_error}")

    def calculate_eta(self, current_progress):
        """计算预计剩余时间"""
        if self.start_time is None or current_progress <= 0:
            return "计算中..."
        
        elapsed_time = time.time() - self.start_time
        if current_progress >= 100:
            return "即将完成"
        
        progress_ratio = current_progress / 100.0
        if progress_ratio <= 0:
            return "计算中..."
        
        estimated_total_time = elapsed_time / progress_ratio
        remaining_time = estimated_total_time - elapsed_time
        
        if remaining_time < 60:
            return f"预计剩余 {int(remaining_time)} 秒"
        elif remaining_time < 3600:
            minutes = int(remaining_time / 60)
            seconds = int(remaining_time % 60)
            return f"预计剩余 {minutes} 分 {seconds} 秒"
        else:
            hours = int(remaining_time / 3600)
            minutes = int((remaining_time % 3600) / 60)
            return f"预计剩余 {hours} 小时 {minutes} 分钟"
    
    def export(self):
        try:
            self.start_time = time.time()
            self.total_steps = 100
            self.current_step = 0
            
            self.current_step = 5
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "正在准备剪辑...", eta)
            
            # 优先使用FFmpeg直接处理，性能更好
            if self._try_ffmpeg_export():
                self.current_step = 100
                eta = self.calculate_eta(self.current_step)
                self.progress.emit(self.current_step, "导出完成！", eta)
                self.finished_export.emit(self.output_path)
                return
            
            # 如果FFmpeg失败，回退到MoviePy处理
            self.status.emit("FFmpeg处理失败，使用备用方法...")
            self._moviepy_export()
            
        except Exception as e:
            self.error.emit(f"导出视频失败: {e}")
    
    def _try_ffmpeg_export(self):
        """尝试使用FFmpeg直接导出视频，性能更好"""
        try:
            import subprocess
            import os
            
            # Sort clips by start time
            self.clips_to_remove.sort(key=lambda c: c.start)
            
            # 构建FFmpeg的select filter表达式
            select_expr = self._build_ffmpeg_select_expression()
            if not select_expr:
                return False
            
            self.current_step = 20
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "正在使用FFmpeg处理视频...", eta)
            
            # 构建FFmpeg命令 - 使用更高质量的编码参数以保持画质
            cmd = [
                'ffmpeg',
                '-i', self.video_path,
                '-filter_complex', select_expr,
                '-map', '[v]',
                '-map', '[a]',
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-preset', 'slower',  # 使用slower预设获得最佳画质
                '-crf', '16',  # 接近无损的CRF值（16-17之间，数值越小质量越高）
                '-pix_fmt', 'yuv420p',  # 确保兼容性
                '-b:v', '20000k',  # 设置更高的视频比特率以获得最佳画质
                '-x264opts', 'aq-mode=2:aq-strength=1.0',  # 自适应量化优化
                '-y',  # 覆盖输出文件
                self.output_path
            ]
            
            # 检查是否支持硬件加速
            hardware_encoder = self._check_hardware_acceleration()
            if hardware_encoder:
                self.status.emit(f"使用硬件加速编码: {hardware_encoder}...")
                # 重新构建命令，确保正确设置编码器 - 根据硬件编码器调整参数
                if hardware_encoder == 'h264_nvenc':
                    # NVENC编码器不支持slower预设，使用medium预设
                    hardware_cmd = [
                        'ffmpeg',
                        '-i', self.video_path,
                        '-filter_complex', select_expr,
                        '-map', '[v]',
                        '-map', '[a]',
                        '-c:v', hardware_encoder,
                        '-c:a', 'aac',
                        '-preset', 'medium',  # NVENC支持medium预设
                        '-crf', '16',  # 接近无损的CRF值
                        '-pix_fmt', 'yuv420p',  # 确保兼容性
                        '-b:v', '20000k',  # 设置更高的视频比特率
                        '-y',  # 覆盖输出文件
                        self.output_path
                    ]
                else:
                    # 其他硬件编码器使用高质量设置
                    hardware_cmd = [
                        'ffmpeg',
                        '-i', self.video_path,
                        '-filter_complex', select_expr,
                        '-map', '[v]',
                        '-map', '[a]',
                        '-c:v', hardware_encoder,
                        '-c:a', 'aac',
                        '-preset', 'slow',  # 使用slow预设获得高质量
                        '-crf', '16',  # 接近无损的CRF值
                        '-pix_fmt', 'yuv420p',  # 确保兼容性
                        '-b:v', '20000k',  # 设置更高的视频比特率
                        '-y',  # 覆盖输出文件
                        self.output_path
                    ]
                cmd = hardware_cmd
            
            # 执行FFmpeg命令，修复编码问题
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.current_step = 90
                eta = self.calculate_eta(self.current_step)
                self.progress.emit(self.current_step, "FFmpeg处理完成！", eta)
                return True
            else:
                print(f"FFmpeg错误: {stderr}")
                return False
                
        except Exception as e:
            print(f"FFmpeg处理异常: {e}")
            return False
    
    def _build_ffmpeg_select_expression(self):
        """构建FFmpeg的select filter表达式"""
        try:
            # 获取视频时长
            import subprocess
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', 
                '-of', 'csv=p=0', self.video_path
            ], capture_output=True, text=True, encoding='utf-8', errors='ignore')
            
            if result.returncode != 0:
                return None
                
            duration = float(result.stdout.strip())
            
            # Sort clips by start time
            self.clips_to_remove.sort(key=lambda c: c.start)
            
            # 计算要保留的时间段
            keep_times = []
            last_end = 0.0
            
            for clip in self.clips_to_remove:
                if clip.start > last_end:
                    keep_times.append((last_end, clip.start))
                last_end = max(last_end, clip.end)
            
            if last_end < duration:
                keep_times.append((last_end, duration))
            
            if not keep_times:
                return None
            
            # 构建select表达式
            conditions = []
            for start, end in keep_times:
                conditions.append(f'between(t,{start},{end})')
            
            select_condition = '+'.join(conditions)
            
            # 构建完整的filter complex
            filter_complex = (
                f"[0:v]select='{select_condition}',setpts=N/FRAME_RATE/TB[v];"
                f"[0:a]aselect='{select_condition}',asetpts=N/SR/TB[a]"
            )
            
            return filter_complex
            
        except Exception as e:
            print(f"构建FFmpeg表达式失败: {e}")
            return None
    
    def _check_hardware_acceleration(self):
        """检查是否支持硬件加速"""
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
            encoders = result.stdout
            
            # 检查可用的硬件加速编码器
            if 'h264_nvenc' in encoders:
                print("检测到NVIDIA NVENC硬件加速")
                return 'h264_nvenc'
            elif 'h264_amf' in encoders:
                print("检测到AMD AMF硬件加速")
                return 'h264_amf'
            elif 'h264_qsv' in encoders:
                print("检测到Intel QSV硬件加速")
                return 'h264_qsv'
            else:
                print("未检测到硬件加速编码器")
                return None
        except Exception as e:
            print(f"检查硬件加速时出错: {e}")
            return None
    
    def _moviepy_export(self):
        """使用MoviePy导出视频（备用方法）"""
        try:
            # 尝试使用GPU加速的视频处理
            import torch
            if torch.cuda.is_available():
                self.status.emit("检测到CUDA，使用GPU加速视频处理...")
                import os
                os.environ['FFMPEG_BINARY'] = 'ffmpeg'
            
            original_video = mp.VideoFileClip(self.video_path)
            duration = original_video.duration

            # Sort clips by start time
            self.clips_to_remove.sort(key=lambda c: c.start)

            # Calculate clips to KEEP
            clips_to_keep_times = []
            last_end = 0.0
            for clip in self.clips_to_remove:
                if clip.start > last_end:
                    clips_to_keep_times.append((last_end, clip.start))
                last_end = clip.end
            
            if last_end < duration:
                clips_to_keep_times.append((last_end, duration))

            if not clips_to_keep_times:
                self.error.emit("没有可保留的视频片段，请检查您的选择。")
                return

            # 优化：减少内存使用，直接拼接而不创建中间片段
            self.current_step = 30
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "正在优化视频处理流程...", eta)
            
            # 使用更高效的方式处理视频片段
            final_clips = []
            total_clips = len(clips_to_keep_times)
            
            for i, (start, end) in enumerate(clips_to_keep_times):
                progress_val = int(30 + (i / total_clips) * 60)  # 30-90%
                self.current_step = progress_val
                eta = self.calculate_eta(self.current_step)
                self.progress.emit(self.current_step, f"正在处理片段 {i+1}/{total_clips}...", eta)
                
                # 直接创建子片段，避免不必要的处理
                sub_clip = original_video.subclip(start, end)
                final_clips.append(sub_clip)
                
                # 及时释放内存
                if i % 5 == 0:  # 每处理5个片段清理一次内存
                    import gc
                    gc.collect()
            
            self.current_step = 95
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "正在拼接视频...", eta)
            
            # 使用更高效的编码参数
            final_video = mp.concatenate_videoclips(final_clips)
            final_video.write_videofile(
                self.output_path, 
                codec="libx264", 
                audio_codec="aac",
                preset="slower",  # 使用slower预设获得最佳画质
                threads=4,  # 使用多线程编码
                bitrate="20000k"  # 设置最高的比特率以获得最佳画质
            )

            self.current_step = 100
            eta = self.calculate_eta(self.current_step)
            self.progress.emit(self.current_step, "导出完成！", eta)
            original_video.close()
            
            # 清理内存
            import gc
            gc.collect()
            
        except Exception as e:
            raise e