"""
LLM Service
Handles LLM integration with Ollama/OpenAI
"""

import requests
import logging
from typing import List, Dict, Any, Iterator
import json

from ..core.config import config

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM interactions"""
    
    def __init__(self):
        self.provider = config.llm_provider
        self.model = config.llm_model
        if self.provider == 'openai':
            self.base_url = config.openai_base_url
        else:
            self.base_url = config.ollama_base_url
        self.temperature = config.llm_temperature
        self.max_tokens = config.llm_max_tokens
        
        logger.info(f"LLM: {self.provider}/{self.model}")
    
    def generate_response(self, messages: List[Dict[str, str]], stream: bool = False) -> str:
        """
        Generate LLM response
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            stream: Whether to stream the response
            
        Returns:
            Generated response text
        """
        if self.provider == "ollama":
            return self._call_ollama(messages, stream)
        elif self.provider == "openai":
            return self._call_openai(messages, stream)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
    
    def _call_ollama(self, messages: List[Dict[str, str]], stream: bool) -> str:
        """Call Ollama API"""
        # Convert messages to prompt
        prompt = self._messages_to_prompt(messages)
        
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt + "\n\nAnswer concisely in 2-3 sentences. If you don't have information, say so.",
            "stream": stream,
            "options": {
                "temperature": self.temperature,
                "num_predict": min(self.max_tokens, 256),
                "stop": ["\nUser:", "[System Context]:", "System:", "</s>"]
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            if stream:
                # Handle streaming response
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        chunk = data.get('response', '')
                        full_response += chunk
                        if data.get('done', False):
                            break
                return full_response
            else:
                data = response.json()
                return data.get('response', '')
                
        except Exception as e:
            logger.error(f"Ollama API call failed: {e}")
            raise
    
    def _call_openai(self, messages: List[Dict[str, str]], stream: bool) -> str:
        """Call OpenAI-compatible API (OpenAI/xAI Grok)"""
        # Convert to chat messages format
        chat_messages = []
        # Add a concise system instruction
        chat_messages.append({"role": "system", "content": "Answer concisely in 2-3 sentences. If you don't have information to answer, say so."})
        for m in messages:
            role = m.get('role', 'user')
            content = m.get('content', '')
            if not content:
                continue
            # Map roles directly
            if role not in ("user", "assistant", "system"):
                role = "user"
            chat_messages.append({"role": role, "content": content})
        
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream
        }
        try:
            if stream:
                resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
                resp.raise_for_status()
                full = ""
                for raw in resp.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode('utf-8', errors='ignore')
                    if not line.startswith('data:'):
                        continue
                    data_str = line[len('data:'):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        obj = json.loads(data_str)
                        delta = obj.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        full += delta
                    except Exception:
                        continue
                return full
            else:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                return data.get('choices', [{}])[0].get('message', {}).get('content', "")
        except Exception as e:
            logger.error(f"OpenAI-compatible API call failed: {e}")
            raise
    
    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert message list to a single prompt string"""
        prompt_parts = []
        
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            if role == "system":
                prompt_parts.append(f"[System Context]: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        # Add final assistant prompt
        prompt_parts.append("Assistant:")
        
        return "\n\n".join(prompt_parts)
    
    def stream_response(self, messages: List[Dict[str, str]]) -> Iterator[str]:
        """
        Stream LLM response
        
        Args:
            messages: List of message dicts
            
        Yields:
            Response chunks
        """
        prompt = self._messages_to_prompt(messages)
        
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt + "\n\nAnswer concisely in 2-3 sentences. If you don't have information, say so.",
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": min(self.max_tokens, 256),
                "stop": ["\nUser:", "[System Context]:", "System:", "</s>"]
            }
        }
        
        try:
            response = requests.post(url, json=payload, stream=True, timeout=60)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get('response', '')
                    if chunk:
                        yield chunk
                    if data.get('done', False):
                        break
                        
        except Exception as e:
            logger.error(f"LLM streaming failed: {e}")
            yield f"[Error: {str(e)}]"


# Global LLM service
_llm_service: LLMService = None


def get_llm_service() -> LLMService:
    """Get or create the global LLM service"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
