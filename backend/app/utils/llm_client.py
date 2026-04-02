"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import logging
import re
import time
from contextlib import nullcontext
from typing import Generator, Optional, Dict, Any, List
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError

from ..config import Config
from .llm_json import normalize_json_object, parse_json_response
from .llm_transient import is_transient_llm_error
from .upstream_error_formatter import format_upstream_service_error

logger = logging.getLogger(__name__)

JSON_RETRY_PROMPT = (
    "你上一次的回复不是有效的 JSON。"
    "请只输出一个合法的 JSON 对象，不要包含任何额外文字、注释或 markdown 代码块。"
)
LLM_TRANSIENT_MAX_RETRIES = 2
LLM_RETRY_INITIAL_DELAY_SECONDS = 1.0
LLM_RETRY_MAX_DELAY_SECONDS = 4.0


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        channel_key: str = "",
        max_concurrency: int = 0,
        concurrency_service=None,
        module_key: str = "",
        activity_tracker=None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.channel_key = channel_key
        self.max_concurrency = int(max_concurrency or 0)
        self.concurrency_service = concurrency_service
        self.module_key = module_key
        self.activity_tracker = activity_tracker

        # 预解析模块中文标签，避免热路径 import
        if module_key and activity_tracker:
            from ..services.llm_module_registry import MODULE_BY_KEY
            defn = MODULE_BY_KEY.get(module_key)
            self._module_label = defn.label if defn else module_key
        else:
            self._module_label = module_key

        if not self.api_key or not self.base_url or not self.model:
            raise ValueError("LLM 客户端初始化缺少必要配置")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=Config.LLM_REQUEST_TIMEOUT_SECONDS,
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）

        Returns:
            模型响应文本
        """
        call_id = self._track_register("chat")
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if response_format:
                kwargs["response_format"] = response_format

            response = self._chat_with_retry(kwargs, call_id)
            return self._clean_content(response.choices[0].message.content)
        finally:
            self._track_unregister(call_id)
    
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[str, None, None]:
        """
        流式发送聊天请求，逐块 yield 文本内容。

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Yields:
            每个 chunk 的文本片段
        """
        call_id = self._track_register("chat_stream")
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        slot = self._slot()
        slot.__enter__()
        self._track_running(call_id, status="streaming")
        try:
            stream = self.client.chat.completions.create(**kwargs)
        except Exception:
            slot.__exit__(None, None, None)
            self._track_unregister(call_id)
            raise
        return self._stream_chunks(stream, slot, call_id)

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        payload = self.chat_json_value(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return normalize_json_object(payload, "LLM响应")

    def chat_json_value(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Any:
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return parse_json_response(response)
        except ValueError:
            logger.warning("LLM 首次返回的 JSON 无效，正在重试 (model=%s)", self.model)
            # 将首次的错误回复和纠正提示加入上下文，让 LLM 修正
            retry_messages = list(messages) + [
                {"role": "assistant", "content": response},
                {"role": "user", "content": JSON_RETRY_PROMPT},
            ]
            retry_response = self.chat(
                messages=retry_messages,
                temperature=max(temperature, 0.1),
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return parse_json_response(retry_response)

    def _slot(self):
        if not self.concurrency_service or not self.channel_key:
            return nullcontext()
        return self.concurrency_service.slot(self.channel_key)

    def _chat_with_retry(self, kwargs: Dict[str, Any], call_id: Optional[str]):
        delay = LLM_RETRY_INITIAL_DELAY_SECONDS
        for attempt in range(LLM_TRANSIENT_MAX_RETRIES + 1):
            try:
                return self._create_completion(kwargs, call_id)
            except Exception as exc:
                if not self._should_retry(exc, attempt):
                    if self._is_transient_error(exc):
                        raise RuntimeError(format_upstream_service_error(exc)) from exc
                    raise
                self._log_retry(exc, attempt + 1, delay)
                time.sleep(delay)
                delay = min(delay * 2, LLM_RETRY_MAX_DELAY_SECONDS)
        raise RuntimeError("LLM 请求重试流程意外结束")

    def _create_completion(self, kwargs: Dict[str, Any], call_id: Optional[str]):
        with self._slot():
            self._track_running(call_id)
            return self.client.chat.completions.create(**kwargs)

    def _should_retry(self, exc: Exception, attempt: int) -> bool:
        return attempt < LLM_TRANSIENT_MAX_RETRIES and self._is_transient_error(exc)

    def _is_transient_error(self, exc: Exception) -> bool:
        return is_transient_llm_error(exc)

    def _log_retry(self, exc: Exception, retry_number: int, delay: float) -> None:
        logger.warning(
            "LLM 请求失败，准备第 %s 次重试 (module=%s, model=%s, delay=%.1fs): %s",
            retry_number,
            self.module_key or "-",
            self.model,
            delay,
            exc,
        )

    def _clean_content(self, content: str) -> str:
        # 部分模型（如 MiniMax M2.5）会在 content 中包裹 think 内容。
        return re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

    def _stream_chunks(self, stream, slot, call_id=None) -> Generator[str, None, None]:
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        finally:
            slot.__exit__(None, None, None)
            self._track_unregister(call_id)

    # ── Activity tracking helpers ──

    def _track_register(self, call_type: str) -> Optional[str]:
        if not self.activity_tracker or not self.module_key:
            return None
        return self.activity_tracker.register(
            module_key=self.module_key,
            module_label=self._module_label,
            model=self.model,
            channel_key=self.channel_key,
            call_type=call_type,
            status="waiting",
        )

    def _track_running(self, call_id: Optional[str], status: str = "running") -> None:
        if call_id and self.activity_tracker:
            self.activity_tracker.update_status(call_id, status)

    def _track_unregister(self, call_id: Optional[str]) -> None:
        if call_id and self.activity_tracker:
            self.activity_tracker.unregister(call_id)
