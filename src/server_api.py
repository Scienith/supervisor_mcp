"""
服务器端 API 客户端与工厂方法。

提供：
- APIClient
- AutoCloseAPIClient
- get_api_client
- API_BASE_URL 常量（供 server.py 打印使用）
"""
from __future__ import annotations

import os
import aiohttp
import asyncio
from typing import Dict, Any
from config import config


# API配置
API_BASE_URL = config.api_url
API_TOKEN = os.getenv("SUPERVISOR_API_TOKEN", "")


class APIClient:
    """API客户端"""

    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self._session = None

    async def _get_session(self):
        """获取或创建session"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,
                limit_per_host=5,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers=self.headers
            )
        return self._session

    async def request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送API请求"""
        url = f"{self.base_url}/{endpoint}"
        session = await self._get_session()

        try:
            async with session.request(method, url, **kwargs) as response:
                content_type = response.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    data = await response.json()

                    if response.status >= 400:
                        return {
                            "status": "error",
                            "message": data.get("error", f"HTTP {response.status}"),
                        }

                    return data
                else:
                    text = await response.text()

                    if response.status >= 400:
                        return {
                            "status": "error",
                            "message": f"HTTP {response.status}: {text}",
                        }

                    return text

        except asyncio.TimeoutError:
            return {"status": "error", "message": "Request timeout"}
        except aiohttp.ClientError as e:
            return {"status": "error", "message": f"API request failed: {str(e)}"}
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                return {"status": "error", "message": f"Event loop is closed"}
            return {"status": "error", "message": f"Runtime error: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    async def close(self):
        """关闭session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class AutoCloseAPIClient:
    """API客户端的自动关闭包装器，向后兼容非async-with用法"""

    def __init__(self, client):
        self._client = client
        self._used_without_context = False

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if name == "request":
            async def wrapped_request(*args, **kwargs):
                self._used_without_context = True
                try:
                    result = await attr(*args, **kwargs)
                    if self._used_without_context:
                        await self._client.close()
                    return result
                except Exception as e:
                    if self._used_without_context:
                        await self._client.close()
                    raise e

            return wrapped_request
        return attr

    async def __aenter__(self):
        self._used_without_context = False
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.close()


def get_api_client():
    """获取新的API客户端实例（每次调用都创建新实例，确保测试隔离）"""
    client = APIClient(API_BASE_URL, API_TOKEN)
    return AutoCloseAPIClient(client)

