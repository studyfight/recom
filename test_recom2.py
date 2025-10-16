#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
recom1 集成与对接自测脚本（ASCII输出，避免乱码）
用法：python recom2/test_recom1.py

包含用例：
1) 本地算法直调（无需HTTP服务）
2) HTTP接口连通性与结构校验
3) 并发安全校验（多用户并发不串号）
4) 约束与排序校验（top_n、按score降序）
"""

import json
import os
import sys
from typing import List, Dict, Any

import requests

# 确保可以导入 recom2 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _print_title(text: str) -> None:
    print("\n" + "=" * 80)
    print(text)
    print("=" * 80)


def test_local_algorithm() -> None:
    """用本地方式直调算法，验证返回结构与排序。"""
    _print_title("[本地直调] 算法可用性与排序校验")

    from recom2.recommendation_agent import create_recommendation_agent

    user_input: Dict[str, Any] = {
        "age": 40,
        "gender": "male",
        "budget": 2000,
        "purpose": "慢病管理",
        "health_concerns": ["糖尿病", "高血压"],
        "family_history": ["糖尿病"],
        "lifestyle_factors": ["吸烟", "饮酒"],
    }

    agent = create_recommendation_agent()
    recs: List[Dict[str, Any]] = agent.recommend_packages(user_input, top_n=3)

    assert isinstance(recs, list) and len(recs) > 0, "本地直调：无推荐结果"
    # 校验降序
    scores = [r.get("score", 0) for r in recs]
    assert scores == sorted(scores, reverse=True), "本地直调：score 未按降序排序"

    print("样例输出(前3):")
    for i, r in enumerate(recs, 1):
        name = r.get("package_name")
        score = r.get("score")
        price = (r.get("package_info") or {}).get("price")
        print(f"  {i}. {name} | score={score:.2f} | price={price}")
    print("[PASS] 本地直调：结构与排序校验通过")


def test_http_api() -> None:
    """调用 HTTP 接口，验证连通性与结构。"""
    _print_title("[HTTP] 连通性与结构校验")

    url = "http://localhost:8000/api/v1/agents/package-recommendations"
    data = {
        "user_id": "test_user_001",
        "age": 40,
        "gender": "male",
        "budget": 2000,
        "purpose": "慢病管理",
        "health_concerns": ["糖尿病", "高血压"],
        "top_n": 3,
    }

    try:
        resp = requests.post(url, json=data, timeout=10)
    except requests.exceptions.ConnectionError:
        print("[SKIP] 服务未启动。请先运行：uvicorn recom2.web:app --reload")
        return

    assert resp.status_code == 200, f"HTTP返回码异常: {resp.status_code}"
    payload = resp.json()

    # 顶层字段
    assert isinstance(payload.get("trace_id"), str), "缺少trace_id"
    assert payload.get("status") == "success", "status != success"
    assert isinstance(payload.get("timestamp"), str), "缺少timestamp"
    assert isinstance(payload.get("data"), dict), "缺少data对象"

    data_obj = payload["data"]
    assert data_obj.get("user_id") == data["user_id"], "user_id回响不一致"
    recs = data_obj.get("recommended") or []
    assert isinstance(recs, list) and len(recs) > 0, "recommended 为空"

    # top_n 与排序
    assert len(recs) <= data.get("top_n", 3), "返回数量超过top_n"
    scores = [r.get("score", 0) for r in recs]
    assert scores == sorted(scores, reverse=True), "score 未按降序排序"

    print(f"响应条数: {len(recs)} | 排序校验通过 | 回响校验通过")
    print("[PASS] HTTP 连通性与结构校验通过")


def test_http_validation() -> None:
    """基础校验：缺少必填字段时应返回 422。"""
    _print_title("[HTTP] 参数校验(缺少user_id)")
    url = "http://localhost:8000/api/v1/agents/package-recommendations"
    bad = {"age": 30}
    try:
        resp = requests.post(url, json=bad, timeout=10)
    except requests.exceptions.ConnectionError:
        print("[SKIP] 服务未启动。")
        return
    assert resp.status_code == 422, f"预期422，实际{resp.status_code}"
    print("[PASS] 缺少user_id时返回422")


def test_concurrency() -> None:
    """并发安全校验：多用户并发，回响一致且有结果。"""
    _print_title("[HTTP] 并发安全校验")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    url = "http://localhost:8000/api/v1/agents/package-recommendations"
    payloads = [
        {
            "user_id": "userA",
            "age": 40,
            "gender": "male",
            "budget": 2000,
            "purpose": "慢病管理",
            "health_concerns": ["糖尿病", "高血压"],
            "family_history": ["糖尿病"],
            "lifestyle_factors": ["吸烟"],
        },
        {
            "user_id": "userB",
            "age": 25,
            "gender": "female",
            "budget": 1500,
            "purpose": "常规体检",
            "health_concerns": ["胃痛"],
            "family_history": [],
            "lifestyle_factors": ["久坐", "熬夜"],
        },
        {
            "user_id": "userC",
            "age": 60,
            "gender": "male",
            "budget": 3000,
            "purpose": "肿瘤筛查",
            "health_concerns": ["肺癌"],
            "family_history": ["肺癌"],
            "lifestyle_factors": ["吸烟"],
        },
    ]

    def _call(p: Dict[str, Any]) -> Dict[str, Any]:
        try:
            r = requests.post(url, json=p, timeout=10)
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            d = j.get("data") or {}
            return {
                "req_user_id": p["user_id"],
                "status": r.status_code,
                "resp_user_id": d.get("user_id"),
                "n_rec": len(d.get("recommended") or []),
            }
        except Exception as e:
            return {"req_user_id": p.get("user_id"), "status": 0, "error": str(e)}

    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(_call, p) for p in payloads]
            results = [f.result() for f in as_completed(futs)]
    except requests.exceptions.ConnectionError:
        print("[SKIP] 服务未启动。")
        return

    ok = all(
        r.get("status") == 200 and r.get("req_user_id") == r.get("resp_user_id") and r.get("n_rec", 0) > 0
        for r in results
    )

    print("并发结果:")
    for r in results:
        print(r)
    assert ok, "并发校验失败：存在串号或无结果"
    print("[PASS] 并发安全校验通过")


def main() -> None:
    print("\nrecom1 自测开始")
    # 1) 本地算法直调（无需HTTP服务）
    test_local_algorithm()
    # 2) HTTP接口连通性与结构
    test_http_api()
    # 3) HTTP参数校验
    test_http_validation()
    # 4) 并发安全
    test_concurrency()
    print("\n自测完成：全部通过")


if __name__ == "__main__":
    main()

