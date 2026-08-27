"""
format_detector.py — 统一文件格式检测器

职责：
  1. 检测输入文件的格式（FIFA PDF/CSV、StatsBomb CSV、Catapult CSV）
  2. 验证数据完整性
  3. 路由到对应的加载器
  4. 返回统一的 (df, info) 结构

设计原则：
  - 一次性读文件（避免 data_loader 中重复检测）
  - 中心化管理所有格式逻辑
  - 易于扩展新格式（Wyscout、InStat、SofaScore）
"""

import os
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from enum import Enum
import pandas as pd


class FormatType(Enum):
    """支持的数据格式"""
    FIFA_PDF = "fifa_pdf"
    FIFA_CSV_MULTI = "fifa_csv_multi"  # 12 个 CSV 文件目录
    FIFA_CSV_SINGLE = "fifa_csv_single"  # 单个FIFA导出 CSV
    STATSBOMB_CSV = "statsbomb_csv"
    CATAPULT_CSV = "catapult_csv"
    CUSTOM_CSV = "custom_csv"
    UNKNOWN = "unknown"


class DetectionResult:
    """格式检测结果"""

    def __init__(
        self,
        format_type: FormatType,
        confidence: float,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.format_type = format_type
        self.confidence = confidence  # 0.0-1.0
        self.file_path = file_path
        self.metadata = metadata or {}

    def is_confident(self, threshold: float = 0.8) -> bool:
        """是否超过置信度阈值"""
        return self.confidence >= threshold

    def __repr__(self):
        return f"<DetectionResult {self.format_type.value} ({self.confidence:.2%})>"


class FormatDetector:
    """统一格式检测器"""

    def __init__(self):
        self.format_priority = [
            FormatType.FIFA_PDF,
            FormatType.FIFA_CSV_MULTI,
            FormatType.STATSBOMB_CSV,
            FormatType.FIFA_CSV_SINGLE,
            FormatType.CATAPULT_CSV,
            FormatType.CUSTOM_CSV,
        ]

    def detect(self, file_path: str) -> DetectionResult:
        """检测文件格式"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_ext = Path(file_path).suffix.lower()

        # PDF 检测
        if file_ext == ".pdf":
            return self._detect_pdf(file_path)

        # CSV 检测（可能是单文件或目录）
        if file_ext == ".csv":
            return self._detect_csv(file_path)

        # 目录检测（FIFA 多文件目录）
        if os.path.isdir(file_path):
            return self._detect_fifa_directory(file_path)

        return DetectionResult(FormatType.UNKNOWN, 0.0, file_path)

    def _detect_pdf(self, file_path: str) -> DetectionResult:
        """检测 PDF 是否为 FIFA 报告"""
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) > 0:
                    first_page_text = pdf.pages[0].extract_text()
                    if first_page_text and ("FIFA" in first_page_text or "match" in first_page_text.lower()):
                        return DetectionResult(
                            FormatType.FIFA_PDF, 0.95, file_path, {"pages": len(pdf.pages)}
                        )
            return DetectionResult(FormatType.UNKNOWN, 0.3, file_path)
        except Exception as e:
            return DetectionResult(FormatType.UNKNOWN, 0.0, file_path, {"error": str(e)})

    def _detect_csv(self, file_path: str) -> DetectionResult:
        """检测 CSV 格式（StatsBomb/Catapult/FIFA 单文件）"""
        try:
            df = pd.read_csv(file_path, nrows=5)
            cols = set(df.columns)

            # StatsBomb 特征（严格匹配）
            if {"type", "team", "location", "possession_team"}.issubset(cols):
                return DetectionResult(FormatType.STATSBOMB_CSV, 0.98, file_path, {"rows": len(df)})

            # FIFA 单文件特征（含 player, shot, goal 等）
            if {"Player", "Team", "Position", "Goals"}.issubset(cols) or {
                "Shot",
                "Goal",
                "Pass",
            }.issubset(cols):
                return DetectionResult(FormatType.FIFA_CSV_SINGLE, 0.90, file_path, {"rows": len(df)})

            # Catapult 特征（包含中文字段或英文 GPS/加速度字段）
            cols_str = " ".join(cols)
            catapult_keywords = {"距离", "高强度", "速度", "加速", "距离"}
            if any(kw in cols_str for kw in catapult_keywords) or {"RHIE", "Distance", "Velocity"}.intersection(cols):
                return DetectionResult(FormatType.CATAPULT_CSV, 0.85, file_path, {"rows": len(df)})

            # 兜底：自定义 CSV
            return DetectionResult(FormatType.CUSTOM_CSV, 0.6, file_path, {"columns": list(cols)[:5]})

        except Exception as e:
            return DetectionResult(FormatType.UNKNOWN, 0.0, file_path, {"error": str(e)})

    def _detect_fifa_directory(self, dir_path: str) -> DetectionResult:
        """检测目录是否为 FIFA 多文件格式（12 个 CSV）"""
        expected_files = [
            "01_match_info",
            "03_key_stats",
            "05_attempts_at_goal",
            "10_out_of_possession",
        ]
        found_count = 0

        for csv_file in os.listdir(dir_path):
            if csv_file.endswith(".csv"):
                for expected in expected_files:
                    if expected in csv_file:
                        found_count += 1
                        break

        confidence = min(found_count / len(expected_files), 1.0)

        if confidence >= 0.5:
            return DetectionResult(
                FormatType.FIFA_CSV_MULTI,
                confidence,
                dir_path,
                {"matched_files": found_count, "total_files": len(os.listdir(dir_path))},
            )

        return DetectionResult(FormatType.UNKNOWN, 0.0, dir_path)

    def load(self, detection_result: DetectionResult) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """根据检测结果加载数据"""
        format_type = detection_result.format_type

        if format_type == FormatType.FIFA_PDF:
            from fifa_pdf_parser import parse_fifa_pdf

            return parse_fifa_pdf(detection_result.file_path)

        elif format_type == FormatType.STATSBOMB_CSV:
            from data_loader import load_statsbomb_csv

            return load_statsbomb_csv(detection_result.file_path)

        elif format_type == FormatType.FIFA_CSV_MULTI:
            from fifa_adapter import load_fifa_from_csv

            return load_fifa_from_csv(detection_result.file_path)

        elif format_type == FormatType.FIFA_CSV_SINGLE:
            from fifa_adapter import convert_fifa_single_file

            return convert_fifa_single_file(detection_result.file_path)

        elif format_type == FormatType.CATAPULT_CSV:
            from data_loader import load_catapult_csv

            return load_catapult_csv(detection_result.file_path)

        elif format_type == FormatType.CUSTOM_CSV:
            from data_loader import load_custom_csv

            return load_custom_csv(detection_result.file_path)

        else:
            raise ValueError(f"不支持的格式: {format_type}")

    def detect_and_load(self, file_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """一站式：检测 + 加载"""
        detection = self.detect(file_path)
        if not detection.is_confident(threshold=0.6):
            raise ValueError(
                f"无法识别文件格式: {file_path}\n"
                f"检测结果: {detection.format_type.value} ({detection.confidence:.2%})"
            )
        return self.load(detection)


# 全局检测器实例
_detector = FormatDetector()


def detect_format(file_path: str) -> DetectionResult:
    """快速检测格式"""
    return _detector.detect(file_path)


def load_data(file_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """一站式加载数据"""
    return _detector.detect_and_load(file_path)
