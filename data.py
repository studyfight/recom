# -*- coding: utf-8 -*-
"""
recom2 数据源：完全自包含。
- 仅从本地 packages.json 加载完整套餐结构
- 不再依赖 reco.*
"""
from __future__ import annotations
import os, json
from typing import Any, Dict, List

BASE_DIR = os.path.dirname(__file__)
PKG_JSON = os.path.join(BASE_DIR, 'packages.json')
KB_JSON = os.path.join(BASE_DIR, 'kb_packages.json')


def _serialize_package_obj(obj: Any) -> Dict[str, Any]:
    """将对象/字典序列化为统一结构（兼容历史导出格式）。"""
    if isinstance(obj, dict):
        code = obj.get('code')
        name = obj.get('name')
        price = obj.get('price')
        category = obj.get('category')
        summary = obj.get('summary_items')
        full_items = obj.get('full_items')
        if hasattr(category, 'value'):
            category = category.value
        return {
            "code": code,
            "name": name,
            "price": price,
            "category": category,
            "summary_items": summary,
            "full_items": full_items,
        }
    # dataclass/对象
    code = getattr(obj, 'code', None)
    name = getattr(obj, 'name', None)
    price = getattr(obj, 'price', None)
    category = getattr(obj, 'category', None)
    if hasattr(category, 'value'):
        category = category.value
    summary = getattr(obj, 'summary_items', None)
    full_items = getattr(obj, 'full_items', None)
    return {
        "code": code,
        "name": name,
        "price": price,
        "category": category,
        "summary_items": summary,
        "full_items": full_items,
    }


def load_packages() -> List[Dict[str, Any]]:
    """加载全部套餐（仅本地）。"""
    if os.path.exists(PKG_JSON):
        with open(PKG_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def load_kb() -> Dict[str, Any]:
    if not os.path.exists(KB_JSON):
        return {}
    with open(KB_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)