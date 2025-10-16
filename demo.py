# -*- coding: utf-8 -*-
"""
recom 演示脚本：输入/输出全路径展示
- 个性化推荐（含“吸烟”高危触发与 full_items 亮点展示）
运行：python recom/demo_package_recommendation.py
"""

from typing import Dict, Any, List
from .recommendation_agent import create_recommendation_agent

SEPARATOR = "=" * 88


def _print_rec(idx: int, rec: Dict[str, Any], user_gender: str) -> None:
	info = rec.get("package_info", {})
	name = rec.get("package_name") or info.get("name")
	price = info.get("price")
	if isinstance(price, dict):
		cur_price = price.get(user_gender)
	else:
		cur_price = price
	print(f"\n🏆 推荐 {idx}: {name}")
	print(f"   匹配度: {(rec.get('score') or 0):.2f} | 价格: {cur_price} 元")
	print(f"   标签: {', '.join(info.get('tags') or [])[:120]}")
	feats = info.get('key_features') or []
	if feats:
		print(f"   核心项目: {', '.join(feats[:6])}")
	reason = rec.get("recommendation_reason") or ""
	print(f"   推荐理由: {reason}")


def demo_recommendation_cases() -> None:
	print(SEPARATOR)
	print("🎯 个性化推荐演示")
	print(SEPARATOR)
	agent = create_recommendation_agent()

	cases: List[Dict[str, Any]] = [
		{
			"title": "常规体检：25岁女性，预算800",
			"user": {
				"age": 25,
				"gender": "female",
				"budget": 800,
				"purpose": "常规体检",
				"health_concerns": [],
				"family_history": [],
				"lifestyle_factors": []
			}
		},
		{
			"title": "肿瘤筛查：45岁男性，吸烟（应触发肺癌相关风险）",
			"user": {
				"age": 45,
				"gender": "male",
				"budget": 2000,
				"purpose": "肿瘤筛查",
				"health_concerns": ["肿瘤", "肺癌"],
				"family_history": [],
				"lifestyle_factors": ["吸烟"]
			}
		},
		{
			"title": "高端体检：60岁女性，关注骨质疏松",
			"user": {
				"age": 60,
				"gender": "female",
				"budget": 5000,
				"purpose": "高端体检",
				"health_concerns": ["骨质疏松"],
				"family_history": [],
				"lifestyle_factors": []
			}
		}
	]

	for case in cases:
		print(f"\n【用例】{case['title']}")
		print(f"输入: {case['user']}")
		recs = agent.recommend_packages(case["user"], top_n=3)
		for i, rec in enumerate(recs, 1):
			_print_rec(i, rec, case["user"].get("gender") or "male")


def main() -> None:
	print("🏥 recom 套餐推荐演示")
	demo_recommendation_cases()
	print("\n✅ 演示结束")


if __name__ == "__main__":
	main() 