"""文件解析工具。"""

from pathlib import Path
from typing import List, Optional

ENCODING_SAMPLE_SIZE = 1024 * 1024
TRUNCATED_DATA_REASON = "unexpected end of data"
COMMON_TEXT_ENCODINGS = ("utf-8-sig", "gb18030", "gbk", "big5")
CHARDET_CONFIDENCE_THRESHOLD = 0.6


def _decode_text_bytes(data: bytes, encoding: str) -> str:
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as exc:
        if exc.reason != TRUNCATED_DATA_REASON or exc.end != len(data):
            raise
        return data[:exc.start].decode(encoding)


def _append_candidate(candidates: List[str], encoding: Optional[str]) -> None:
    if not encoding:
        return
    normalized = encoding.lower()
    if normalized in candidates:
        return
    candidates.append(normalized)


def _detect_with_charset_normalizer(data: bytes) -> Optional[str]:
    from charset_normalizer import from_bytes

    best = from_bytes(data).best()
    if not best or not best.encoding:
        return None
    return best.encoding


def _detect_with_chardet(data: bytes) -> Optional[str]:
    import chardet

    detected = chardet.detect(data)
    encoding = detected.get("encoding")
    confidence = float(detected.get("confidence") or 0.0)
    if confidence < CHARDET_CONFIDENCE_THRESHOLD:
        return None
    return encoding


def _detect_text_encodings(data: bytes) -> List[str]:
    sample = data[:ENCODING_SAMPLE_SIZE]
    candidates: List[str] = []
    _append_candidate(candidates, _detect_with_charset_normalizer(sample))
    _append_candidate(candidates, _detect_with_chardet(sample))
    for encoding in COMMON_TEXT_ENCODINGS:
        _append_candidate(candidates, encoding)
    return candidates


def _read_text_with_detected_encoding(file_path: str) -> str:
    """读取文本文件；UTF-8 失败时显式检测编码。"""
    data = Path(file_path).read_bytes()
    try:
        return _decode_text_bytes(data, "utf-8")
    except UnicodeDecodeError as utf8_error:
        for encoding in _detect_text_encodings(data):
            if encoding == "utf-8":
                continue
            try:
                return _decode_text_bytes(data, encoding)
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError(
            "unknown",
            data,
            utf8_error.start,
            utf8_error.end,
            "无法识别文本编码",
        ) from utf8_error


class FileParser:
    """文件解析器"""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}
    
    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        从文件中提取文本
        
        Args:
            file_path: 文件路径
            
        Returns:
            提取的文本内容
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {suffix}")
        
        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)
        
        raise ValueError(f"无法处理的文件格式: {suffix}")
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """从PDF提取文本"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("需要安装PyMuPDF: pip install PyMuPDF")
        
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """从Markdown提取文本，支持显式编码检测"""
        return _read_text_with_detected_encoding(file_path)

    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """从TXT提取文本，支持显式编码检测"""
        return _read_text_with_detected_encoding(file_path)
    
    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        从多个文件提取文本并合并
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            合并后的文本
        """
        all_texts = []
        failures = []
        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== 文档 {i}: {filename} ===\n{text}")
            except Exception as e:
                failures.append(f"{file_path}: {e}")
        if failures:
            raise ValueError("文档提取失败: " + "；".join(failures))
        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str, 
    chunk_size: int = 500, 
    overlap: int = 50
) -> List[str]:
    """
    将文本分割成小块
    
    Args:
        text: 原始文本
        chunk_size: 每块的字符数
        overlap: 重叠字符数
        
    Returns:
        文本块列表
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # 尝试在句子边界处分割
        if end < len(text):
            # 查找最近的句子结束符
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # 下一个块从重叠位置开始
        start = end - overlap if end < len(text) else len(text)
    
    return chunks
