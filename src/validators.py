"""
MCP数据验证器
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Literal
from datetime import datetime