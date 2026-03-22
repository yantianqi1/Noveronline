"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import logging
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .llm_json import normalize_json_object, parse_json_response

logger = logging.getLogger(__name__)

JSON_RETRY_PROMPT = (
    "你上一次的回复不是有效的 JSON。"
    "请只输出一个合法的 JSON 对象，不要包含任何额外文字、注释或 markdown 代码块。"
)


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        
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
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
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
