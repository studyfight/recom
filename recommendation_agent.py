# -*- coding: utf-8 -*-
"""
套餐推荐Agent
根据用户个人信息进行个性化套餐推荐，并提供问答功能
"""

import json
from typing import Dict, List, Any, Optional
from .data import load_packages
import os

def _load_json_or_default(path: str, default: Any) -> Any:
	try:
		if os.path.exists(path):
			import json as _json
			with open(path, 'r', encoding='utf-8') as f:
				return _json.load(f)
	except Exception:
		pass
	return default

PACKAGES_DATA = load_packages()
EXAMINATION_DETAILS: Dict[str, Any] = {}

class PackageRecommendationAgent:
	def __init__(self):
		self.packages: List[Dict[str, Any]] = PACKAGES_DATA or []
		self.examination_details = EXAMINATION_DETAILS
		self.last_user_profile: Optional[Dict[str, Any]] = None
		# 先定义关键词映射，供派生标签使用
		# 优先从 JSON 读取，失败则用内置默认
		default_keyword_to_tags = {
			# 糖尿病/代谢
			"糖化血红蛋白": ["糖尿病筛查", "慢性病管理"],
			"空腹血糖": ["糖尿病筛查", "慢性病管理"],
			"胰岛素": ["糖尿病筛查", "慢性病管理"],
			"C肽": ["糖尿病筛查", "慢性病管理"],
			"尿微量白蛋白": ["糖尿病并发症筛查", "慢性病管理"],
			# 高血压/心血管
			"动态血压": ["高血压筛查", "心血管检查", "慢性病管理"],
			"高血压三项": ["高血压筛查", "慢性病管理"],
			"心电图": ["心血管检查"],
			"颈动脉": ["心血管检查"],
			# 肿瘤
			"甲胎蛋白": ["肿瘤筛查"],
			"癌胚抗原": ["肿瘤筛查"],
			"CA-": ["肿瘤筛查"],
			"肿瘤标志物": ["肿瘤筛查"],
			# 妇科/乳腺/前列腺
			"HPV": ["妇科检查"],
			"TCT": ["妇科检查"],
			"乳腺": ["乳腺检查"],
			"子宫": ["妇科检查"],
			"卵巢": ["妇科检查"],
			"前列腺": ["前列腺检查"],
			# 影像
			"CT": ["影像学检查"],
			"MRI": ["影像学检查"],
		}
		self.keyword_to_tags = _load_json_or_default(
			os.path.join(os.path.dirname(__file__), 'config', 'keyword_to_tags.json'),
			default_keyword_to_tags
		)
		# 基于 full_items 的解析开关
		self.use_full_items_enhance: bool = True
		# 寻系列（肿瘤筛查）“整合型风险标签”与触发规则（任意一条命中即触发）
		default_risk_rules: Dict[str, Dict[str, Any]] = {
			"CANCER_STOMACH": {
				"label": "胃癌相关风险",
				"triggers": {
					"family_history": ["胃癌"],
					"medical_history": ["胃溃疡", "胃息肉", "慢性萎缩性胃炎", "恶性贫血", "残胃", "肥厚性胃炎", "幽门螺杆菌", "Hp"],
					"lifestyle_factors": ["高盐", "腌制", "吸烟", "重度饮酒"],
					"region": ["胃癌高发区"]
				}
			},
			"CANCER_LIVER": {
				"label": "肝癌相关风险",
				"triggers": {
					"family_history": ["肝癌"],
					"medical_history": ["乙肝", "乙型肝炎", "慢性肝炎", "肝硬化", "HBV"],
					"lifestyle_factors": ["长期饮酒", "重度饮酒"]
				}
			},
			"CANCER_COLON": {
				"label": "结直肠癌相关风险",
				"triggers": {
					"family_history": ["结直肠癌", "直肠癌", "结肠癌"],
					"medical_history": ["慢性结肠炎", "肠息肉", "腺瘤", "炎症性肠病", "便血", "粘液便", "腹泻", "腹痛", "排便习惯改变"],
					"age_hint": ["40岁及以上", "≥40"]
				}
			},
			"CANCER_ESOPHAGUS": {
				"label": "食管癌相关风险",
				"triggers": {
					"family_history": ["食管癌"],
					"region": ["食管癌高发"],
					"medical_history": ["Barrett", "癌前病变", "鳞癌"],
					"lifestyle_factors": ["重度吸烟", "重度饮酒", "热烫饮食", "进食过快", "室内空气污染", "牙齿缺失"],
					"symptoms": ["吞咽困难", "哽噎感"]
				}
			},
			"CANCER_BREAST": {
				"label": "乳腺癌相关风险",
				"triggers": {
					"family_history": ["乳腺癌"],
					"medical_history": ["乳腺导管不典型增生", "小叶不典型增生", "小叶原位癌"],
					"treatment_history": ["胸部放疗"]
				}
			},
			"CANCER_FEMALE_REPRODUCTIVE": {
				"label": "生殖肿瘤相关风险",
				"triggers": {
					"family_history": ["宫颈癌", "卵巢癌", "子宫内膜癌"],
					"medical_history": ["多囊卵巢", "无排卵", "月经异常", "不孕", "高血压", "糖尿病", "肥胖", "初潮早", "绝经晚"]
				}
			},
			"CANCER_LUNG": {
				"label": "肺癌相关风险",
				"triggers": {
					"family_history": ["肺癌"],
					"lifestyle_factors": ["吸烟", "抽烟", "被动吸烟"],
					"occupational_exposure": ["石棉", "氡", "铍", "铬", "镉", "镍", "硅", "煤烟", "煤尘"]
					# 如需按包年/年限判断，可在用户输入中增加结构化字段后扩展
				}
			}
		}
		self.risk_rules = _load_json_or_default(
			os.path.join(os.path.dirname(__file__), 'config', 'risk_rules.json'),
			default_risk_rules
		)
		# 再基于套餐构建内部KB
		self.knowledge_base: Dict[str, Dict[str, Any]] = self._build_kb_from_packages(self.packages)
		# 非“寻系列”标签规则（属性/功能/亮点）基于名称/类别的启发式映射
		default_meta_tag_rules = {
			"暖系列套餐": {
				"attributes": ["全人群通用"],
				"function_by_name": {
					"温暖": "基础健康筛查",
					"曼暖": "基础健康+肿瘤初筛",
					"煦暖": "深度健康+肿瘤筛查",
					"晴暖": "全面健康评估"
				},
				"highlights_by_name": {
					"温暖": ["含胸部CT", "基础脏器超声"],
					"曼暖": ["AFP/CEA肿瘤指标"],
					"煦暖": ["甲状腺超声", "幽门螺杆菌检测"],
					"晴暖": ["颈动脉超声", "甲功三项"]
				}
			},
			"爱系列套餐": {
				"attributes_by_name": {
					"相爱婚前": ["未婚人群"],
					"宠爱宝贝": ["18岁以下儿童/青少年"],
					"臻爱亲情": ["中老年优先"],
					"挚爱无忧": ["全人群(高端需求)"],
					"博爱尊享": ["全人群(高端尊享)"]
				},
				"function_by_name": {
					"相爱婚前": "婚前专项体检",
					"宠爱宝贝": "儿童青少年健康体检",
					"臻爱亲情": "中老年健康评估",
					"挚爱无忧": "高端全面健康筛查",
					"博爱尊享": "尊享深度健康筛查"
				},
				"highlights_by_name": {
					"相爱婚前": ["ABO血型", "输血前8项", "甲功"],
					"宠爱宝贝": ["骨龄检测", "25羟维生素D"],
					"臻爱亲情": ["骨密度", "动脉硬化检测"],
					"挚爱无忧": ["心脏彩超", "双能骨密度"],
					"博爱尊享": ["无痛胃肠镜", "头颅核磁", "专属服务"]
				}
			},
			"和系列套餐": {
				"function_by_name": {
					"糖尿病": "糖尿病专项筛查",
					"高血压": "高血压专项筛查",
					"冠心病": "冠心病专项筛查",
					"脑血管": "脑血管专项筛查",
					"骨质疏松": "骨质疏松专项筛查",
					"体重管理": "体重管理健康评估"
				},
				"attributes_by_name": {
					"骨质疏松": ["中老年/骨质疏松高危"],
					"体重管理": ["体重异常/减脂人群"]
				},
				"highlights_by_name": {
					"糖尿病": ["糖化血红蛋白", "胰岛素"],
					"高血压": ["24小时动态血压"],
					"冠心病": ["冠脉相关检查/心电监测"],
					"脑血管": ["头颅核磁", "颈动脉超声"],
					"骨质疏松": ["骨密度"],
					"体重管理": ["人体成分分析", "胰岛素检测"]
				}
			},
			"入职体检套餐": {
				"attributes": ["职场入职人群"],
				"function_by_name": {
					"普通入职": "基础/进阶入职体检",
					"公务员": "公务员标准入职体检"
				},
				"highlights_by_name": {
					"普通入职": ["符合企业入职标准"],
					"公务员": ["含梅毒/HIV检测", "符合公考标准"]
				}
			}
		}
		self.meta_tag_rules = _load_json_or_default(
			os.path.join(os.path.dirname(__file__), 'config', 'meta_tag_rules.json'),
			default_meta_tag_rules
		)

	def _build_kb_from_packages(self, pkgs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
		kb: Dict[str, Dict[str, Any]] = {}
		for p in pkgs:
			name = p.get("name") or p.get("code")
			if not name:
				continue
			# key_features 优先用 summary_items；没有则从每个分类取前1-2个项目名
			summary = p.get("summary_items") or []
			features: List[str] = []
			if summary:
				features = list(summary)
			else:
				full = p.get("full_items") or []
				for block in full:
					items = (block or {}).get("items") or []
					for it in items[:2]:
						nm = str((it or {}).get("name", "")).strip()
						if nm:
							features.append(nm)
			# 由关键词映射派生标签
			derived: List[str] = []
			for f in features:
				for kw, tags in self.keyword_to_tags.items():
					if kw in str(f):
						for t in tags:
							if t not in derived:
								derived.append(t)
			# 基于 full_items 的解析：约束与亮点（可开关）
			constraints_parsed: Dict[str, Any] = {}
			highlights_parsed: List[str] = []
			if self.use_full_items_enhance:
				# 解析规则也支持 JSON 配置
				rules_path = os.path.join(os.path.dirname(__file__), 'config', 'full_items_rules.json')
				default_full_rules = {
					"married_only_keywords": ["(限已婚)", "限已婚"],
					"female_specific_keywords": ["妇科", "子宫", "卵巢", "乳腺", "HPV", "TCT", "阴道"],
					"male_specific_keywords": ["前列腺", "PSA"],
					"child_preferred_keywords": ["骨龄", "儿童", "青少年"],
					"highlights_map": {
						"颈动脉": "颈动脉超声",
						"骨密度": "骨密度",
						"动态血压": "24小时动态血压",
						"胃镜": "胃镜",
						"结肠镜": "结肠镜",
						"胃肠镜": "胃肠镜",
						"心动图": "心脏超声",
						"心脏彩超": "心脏彩超",
						"HPV": "HPV",
						"TCT": "TCT"
					}
				}
				full_rules = _load_json_or_default(rules_path, default_full_rules)
				full_items = p.get("full_items") or []
				all_names: List[str] = []
				for block in full_items:
					for it in (block or {}).get("items", []) or []:
						nm = str((it or {}).get("name", "")).strip()
						if nm:
							all_names.append(nm)
				# 约束解析
				text = " ".join(all_names)
				if any(k in text for k in full_rules.get("married_only_keywords", [])):
					constraints_parsed["married_only"] = True
				female_kws = full_rules.get("female_specific_keywords", [])
				male_kws = full_rules.get("male_specific_keywords", [])
				if any(k in text for k in female_kws):
					constraints_parsed["contains_female_specific"] = True
				if any(k in text for k in male_kws):
					constraints_parsed["contains_male_specific"] = True
				# 儿童偏好
				if any(k in text for k in full_rules.get("child_preferred_keywords", [])):
					constraints_parsed["child_preferred"] = True
				# 亮点解析（常见关键项目）
				hl_map = full_rules.get("highlights_map", {})
				for raw in all_names:
					for kw, label in hl_map.items():
						if kw in raw and label not in highlights_parsed:
							highlights_parsed.append(label)
			# 健康关注=派生标签的汇总；描述自动生成
			health_focus = list(derived)
			if not health_focus:
				health_focus = ["常规体检"]
			desc = "包含" + "、".join(features[:4]) if features else ""
			if health_focus:
				desc = (desc + "；适合" + "、".join(health_focus[:2])).strip("；")
			info = {
				"code": p.get("code"),
				"name": name,
				"price": p.get("price"),
				"category": p.get("category"),
				"key_features": features,
				"tags": list(derived),
				"health_focus": health_focus,
				"description": desc
			}
			if self.use_full_items_enhance:
				if constraints_parsed:
					info["constraints_parsed"] = constraints_parsed
				if highlights_parsed:
					info["highlights_parsed"] = highlights_parsed
			kb[name] = info
		return kb

	def _search_packages_by_keyword(self, q: str) -> List[Dict[str, Any]]:
		q = (q or '').strip()
		if not q:
			return []
		results: List[Dict[str, Any]] = []
		for name, info in self.knowledge_base.items():
			blob = ' '.join([
				name,
				' '.join(info.get('tags', []) or []),
				' '.join(info.get('key_features', []) or []),
				info.get('description', '')
			])
			if q in blob:
				results.append({"package": name, "info": info})
		return results

	def _derive_tags_from_features(self, package_info: Dict[str, Any]) -> List[str]:
		feats = list(package_info.get("key_features", []) or [])
		# 兼容可能存在的 summary 列表
		feats += list(package_info.get("summary_items", []) or [])
		derived: set[str] = set()
		for f in feats:
			text = str(f)
			for kw, tags in self.keyword_to_tags.items():
				if kw in text:
					derived.update(tags)
		# 基于系列/名称的属性/功能/亮点标签
		series = str(package_info.get("category", ""))
		name = str(package_info.get("name", ""))
		rules = self.meta_tag_rules.get(series)
		if rules:
			# attributes 固定或按名称
			for attr in rules.get("attributes", []) or []:
				derived.add(attr)
			for key, arr in (rules.get("attributes_by_name", {}) or {}).items():
				if key and key in name:
					for a in arr:
						derived.add(a)
			# function 标签
			for key, func in (rules.get("function_by_name", {}) or {}).items():
				if key and key in name and func:
					derived.add(func)
			# highlights 标签（名称规则）
			for key, arr in (rules.get("highlights_by_name", {}) or {}).items():
				if key and key in name:
					for h in arr:
						derived.add(h)
		# highlights（full_items 解析结果）
		if self.use_full_items_enhance:
			for h in (package_info.get("highlights_parsed") or []):
				derived.add(str(h))
		return sorted(derived)

	def _effective_tags(self, package_info: Dict[str, Any]) -> List[str]:
		base_tags = list(package_info.get("tags", []) or [])
		health_focus = list(package_info.get("health_focus", []) or [])
		derived = self._derive_tags_from_features(package_info)
		return sorted({*base_tags, *health_focus, *derived})

	def _classify_series(self, package_name: str, package_info: Dict[str, Any]) -> str:
		"""基于名称与有效标签粗分系列：job/chronic/cancer/marriage/regular"""
		name = str(package_name)
		tags = self._effective_tags(package_info)
		text = name + " " + " ".join(tags)
		if ("入职" in text) or any("入职体检" in t for t in tags):
			return "job"
		if any(k in text for k in ["糖尿病", "高血压", "冠心病", "脑血管", "骨质疏松", "体重管理", "慢性病"]):
			return "chronic"
		if ("婚前" in text):
			return "marriage"
		if any(k in text for k in ["筛查", "肿瘤", "癌"]):
			return "cancer"
		return "regular"

	def _purpose_target_series(self, purpose: str) -> List[str]:
		if purpose == "入职体检":
			return ["job"]
		if purpose == "慢病管理":
			return ["chronic"]
		if purpose == "婚前体检":
			return ["marriage"]
		if purpose == "肿瘤筛查":
			return ["cancer"]
		# 常规体检
		return ["regular", "chronic"]  # 常规兼容基础/慢病

	def _purpose_weights(self, purpose: str) -> Dict[str, float]:
		"""根据目的动态调整各维度权重。返回字典 keys: age, gender, budget, health, purpose"""
		# 默认权重
		w = {"age": 0.2, "gender": 0.2, "budget": 0.2, "health": 0.25, "purpose": 0.15}
		if purpose == "入职体检":
			w = {"age": 0.1, "gender": 0.1, "budget": 0.2, "health": 0.1, "purpose": 0.5}
		elif purpose == "慢病管理":
			w = {"age": 0.15, "gender": 0.1, "budget": 0.2, "health": 0.25, "purpose": 0.3}
		elif purpose == "肿瘤筛查":
			w = {"age": 0.15, "gender": 0.1, "budget": 0.15, "health": 0.3, "purpose": 0.3}
		elif purpose == "婚前体检":
			w = {"age": 0.15, "gender": 0.15, "budget": 0.2, "health": 0.2, "purpose": 0.3}
		return w

	def analyze_user_profile(self, user_info: Dict[str, Any]) -> Dict[str, Any]:
		"""分析用户画像，提取关键特征"""
		profile = {
			"age": user_info.get("age", 0),
			"gender": user_info.get("gender", "male"),
			"budget": user_info.get("budget", 0),
			"health_concerns": user_info.get("health_concerns", []),
			"family_history": user_info.get("family_history", []),
			"lifestyle_factors": user_info.get("lifestyle_factors", []),
			"occupation": user_info.get("occupation", ""),
			"purpose": user_info.get("purpose", "常规体检"),
			# 扩展：供高危规则使用（可选字段，缺省为空）
			"region": user_info.get("region", ""),
			"symptoms": user_info.get("symptoms", []),
			"medical_history": user_info.get("medical_history", []),
			"treatment_history": user_info.get("treatment_history", []),
			"occupational_exposure": user_info.get("occupational_exposure", []),
			"smoking_pack_years": user_info.get("smoking_pack_years"),
			"passive_smoke_years": user_info.get("passive_smoke_years"),
		}
		# 年龄段保留，但在理由里不引用
		if profile["age"] < 18:
			profile["age_group"] = "青少年"
		elif 18 <= profile["age"] < 30:
			profile["age_group"] = "青年"
		elif 30 <= profile["age"] < 50:
			profile["age_group"] = "中年"
		elif 50 <= profile["age"] < 65:
			profile["age_group"] = "中老年"
		else:
			profile["age_group"] = "老年"
		# 预算分级
		if profile["budget"] < 500:
			profile["budget_level"] = "经济型"
		elif 500 <= profile["budget"] < 1500:
			profile["budget_level"] = "标准型"
		elif 1500 <= profile["budget"] < 3000:
			profile["budget_level"] = "高端型"
		else:
			profile["budget_level"] = "豪华型"
		return profile

	def filter_features_by_gender(self, features: List[str], gender: str) -> List[str]:
		"""按性别过滤检查项目（启发式规则）。"""
		if not features:
			return []
		if gender not in ("male", "female"):
			return features
		
		female_keywords = ["（女", "女）", "乳腺", "妇科", "宫颈", "HPV", "TCT", "子宫", "卵巢", "盆腔"]
		male_keywords = ["（男", "男）", "前列腺", "PSA"]
		
		filtered: List[str] = []
		for item in features:
			text = str(item)
			has_female = any(k in text for k in female_keywords)
			has_male = any(k in text for k in male_keywords)
			
			if gender == "male":
				# 男性：剔除明显女性项目
				if has_female and not has_male:
					continue
				filtered.append(item)
			else:
				# 女性：剔除明显男性项目
				if has_male and not has_female:
					continue
				filtered.append(item)
		return filtered
	
	def calculate_package_score(self, package_name: str, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""计算套餐与用户的匹配度得分（动态权重）"""
		purpose = user_profile.get("purpose", "常规体检")
		weights = self._purpose_weights(purpose)
		score = 0.0
		age_score = self._calculate_age_score(package_info, user_profile)
		score += age_score * weights["age"]
		# 性别得分：若套餐推断性别与用户不符则强降分
		inferred = self._infer_gender(package_info)
		gender_score = 1.0 if (not inferred or inferred == user_profile.get("gender")) else 0.0
		score += gender_score * weights["gender"]
		budget_score = self._calculate_budget_score(package_info, user_profile)
		score += budget_score * weights["budget"]
		health_score = self._calculate_health_score(package_info, user_profile)
		score += health_score * weights["health"]
		purpose_score = self._calculate_purpose_score(package_name, package_info, user_profile)
		score += purpose_score * weights["purpose"]
		# 目标系列加分（软优先）
		series = self._classify_series(package_name, package_info)
		if series in self._purpose_target_series(purpose):
			score += 0.3
		# 明确关注点加分（如糖尿病）
		score += self._concern_specific_bonus(package_name, package_info, user_profile)
		# 命中“寻系列”高危整合标签时加分
		score += self._risk_rule_bonus(package_info, user_profile)
		# 未满足约束的惩罚分（软）
		score += self._constraint_malus(package_info, user_profile)
		return min(score, 5.0)

	def _calculate_age_score(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""计算年龄匹配得分"""
		age = user_profile["age"]
		age_range = package_info.get("age_range", "")
		
		if not age_range or age == 0:
			return 0.5  # 中等得分
		
		# 解析年龄范围
		if "岁以下" in age_range:
			max_age = int(age_range.replace("岁以下", ""))
			return 1.0 if age < max_age else 0.0
		elif "岁以上" in age_range:
			min_age = int(age_range.replace("岁以上", ""))
			return 1.0 if age >= min_age else 0.3
		elif "-" in age_range and "岁" in age_range:
			parts = age_range.replace("岁", "").split("-")
			if len(parts) == 2:
				min_age, max_age = int(parts[0]), int(parts[1])
				if min_age <= age <= max_age:
					return 1.0
				elif abs(age - min_age) <= 5 or abs(age - max_age) <= 5:
					return 0.7  # 接近目标年龄范围
				else:
					return 0.2
		
		return 0.5
	
	def _calculate_gender_score(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""计算性别匹配得分"""
		gender = user_profile["gender"]
		package_gender = package_info.get("gender", "")
		
		if not package_gender:
			return 1.0  # 无性别限制
		
		return 1.0 if gender == package_gender else 0.0
	
	def _calculate_budget_score(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""计算预算匹配得分"""
		budget = user_profile["budget"]
		if budget == 0:
			return 0.5  # 未提供预算信息
		
		price = package_info.get("price", 0)
		if isinstance(price, dict):
			current_price = price.get(user_profile["gender"], price.get("male", 0))
		else:
			current_price = price
		
		if current_price == 0:
			return 0.5
		
		if current_price <= budget:
			# 价格在预算内，根据性价比计算得分
			ratio = current_price / budget
			if ratio >= 0.8:
				return 1.0  # 充分利用预算
			elif ratio >= 0.5:
				return 0.9  # 较好利用预算
			else:
				return 0.7  # 节省预算
		else:
			# 价格超出预算
			over_ratio = (current_price - budget) / budget
			if over_ratio <= 0.2:
				return 0.3  # 稍微超出预算
			else:
				return 0.0  # 严重超出预算
	
	def _calculate_health_score(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""计算健康关注点匹配得分（增强：关键词+派生标签）"""
		health_concerns = [str(x) for x in user_profile.get("health_concerns", []) or []]
		family_history = [str(x) for x in user_profile.get("family_history", []) or []]
		lifestyle_factors = [str(x) for x in user_profile.get("lifestyle_factors", []) or []]
		if not health_concerns and not family_history and not lifestyle_factors:
			return 0.5
		eff_tags = self._effective_tags(package_info)
		feats_text = ",".join([str(x) for x in (package_info.get('key_features') or [])])
		def match_any(words: List[str]) -> int:
			cnt = 0
			for w in words:
				if not w:
					continue
				if any(w in t for t in eff_tags) or (w in feats_text):
					cnt += 1
			return cnt
		total = len(health_concerns) + len(family_history) + len(lifestyle_factors)
		if total == 0:
			return 0.5
		matches = match_any(health_concerns) + match_any(family_history) + match_any(lifestyle_factors)
		return min(1.0, max(0.2, matches / total))

	def _calculate_purpose_score(self, package_name: str, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""计算目的匹配得分（增强：入职排除/常规优先）"""
		purpose = user_profile.get("purpose", "常规体检")
		name = str(package_name)
		eff_tags = self._effective_tags(package_info)
		if purpose == "入职体检":
			# 入职专属优先
			return 1.0 if ("入职" in name) else 0.2
		# 非入职时，排除/强降分入职套餐
		if "入职" in name:
			return 0.0
		mapping = {
			"常规体检": ["基础体检", "全面体检", "常规筛查"],
			"婚前体检": ["婚前体检"],
			"肿瘤筛查": ["肿瘤筛查"],
			"慢病管理": ["慢性病管理", "糖尿病筛查", "高血压筛查"],
			"高端体检": ["高端体检", "VIP服务"],
		}
		tags = mapping.get(purpose, [])
		return 1.0 if any(any(tag in t for t in eff_tags) for tag in tags) else 0.5

	# ===== 新增：高危规则匹配与加分 =====
	def _normalize_profile_fields(self, user_profile: Dict[str, Any]) -> Dict[str, List[str]]:
		"""将画像中的相关字段统一为字符串列表以便匹配。"""
		def to_list(val: Any) -> List[str]:
			if val is None:
				return []
			if isinstance(val, list):
				return [str(x) for x in val if x]
			return [str(val)]
		return {
			"family_history": to_list(user_profile.get("family_history")),
			"lifestyle_factors": to_list(user_profile.get("lifestyle_factors")),
			"region": to_list(user_profile.get("region")),
			"symptoms": to_list(user_profile.get("symptoms")),
			"medical_history": to_list(user_profile.get("medical_history")),
			"treatment_history": to_list(user_profile.get("treatment_history")),
			"occupational_exposure": to_list(user_profile.get("occupational_exposure")),
		}

	def _match_risk_for_code(self, package_code: Optional[str], user_profile: Dict[str, Any]) -> Optional[str]:
		"""若用户画像命中某个筛查套餐的高危规则，则返回对应整合标签，否则返回 None。"""
		if not package_code:
			return None
		rule = self.risk_rules.get(str(package_code))
		if not rule:
			return None
		fields = self._normalize_profile_fields(user_profile)
		triggers: Dict[str, List[str]] = rule.get("triggers", {})
		for field_name, keywords in triggers.items():
			values = fields.get(field_name, [])
			if not values or not keywords:
				continue
			# 任意关键词命中即触发
			for v in values:
				for kw in keywords:
					if kw and (kw in str(v)):
						return rule.get("label")
		return None

	def _risk_rule_bonus(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""命中高危整合标签时给予额外加分。"""
		code = package_info.get("code")
		label = self._match_risk_for_code(code, user_profile)
		return 0.5 if label else 0.0

	def _constraint_malus(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""未满足约束时的降分（软惩罚，仍可推荐但排序靠后）。"""
		check = self._check_constraints(package_info, user_profile)
		if not check.get("violated"):
			return 0.0
		# 每个违反点 -0.4，上限 -0.8
		n = len(check.get("messages") or ["violation"]) or 1
		return max(-0.8, -0.4 * n)

	def recommend_packages(self, user_info: Dict[str, Any], top_n: int = 3) -> List[Dict[str, Any]]:
		"""推荐套餐"""
		user_profile = self.analyze_user_profile(user_info)
		self.last_user_profile = user_profile
		package_scores: List[Dict[str, Any]] = []
		target_series = self._purpose_target_series(user_profile.get("purpose", "常规体检"))
		for package_name, package_info in self.knowledge_base.items():
			# 常规体检：排除入职
			if user_profile.get("purpose") == "常规体检" and ("入职" in str(package_name)):
				continue
			# 严格性别过滤：只计算与用户性别一致的套餐
			inferred = self._infer_gender(package_info)
			if inferred and inferred != user_profile.get("gender"):
				continue
			series = self._classify_series(package_name, package_info)
			score = self.calculate_package_score(package_name, package_info, user_profile)
			filtered_features = self.filter_features_by_gender(
				package_info.get('key_features', []), user_profile['gender']
			)
			gender = user_profile.get('gender')
			display_info = dict(package_info)
			display_name = package_name
			price = package_info.get('price')
			if isinstance(price, dict) and gender in ('male','female'):
				display_info['price'] = price.get(gender)
				if '(' not in display_name:
					display_name = f"{package_name}({'男士' if gender=='male' else '女士'})"
			reason = self._compose_reason(package_name, package_info, user_profile, filtered_features)
			package_scores.append({
				"package_name": display_name,
				"package_info": display_info,
				"score": score + (0.3 if series in target_series else 0.0),
				"filtered_key_features": filtered_features,
				"recommendation_reason": reason
			})
		package_scores.sort(key=lambda x: x["score"], reverse=True)
		return package_scores[:top_n]
	
	def answer_question(self, question: str, context: Optional[str] = None) -> str:
		"""回答用户问题"""
		question_lower = question.lower()
		
		# 问题分类
		if any(keyword in question_lower for keyword in ["为什么", "为什么推荐", "推荐理由"]):
			return self._answer_why_recommend(question, context)
		elif any(keyword in question_lower for keyword in ["什么是", "项目", "检查"]):
			return self._answer_what_is(question)
		elif any(keyword in question_lower for keyword in ["价格", "多少钱", "费用"]):
			return self._answer_price(question)
		elif any(keyword in question_lower for keyword in ["适合", "推荐", "选择"]):
			return self._answer_suitable(question)
		else:
			return self._general_answer(question)
	
	def _answer_why_recommend(self, question: str, context: str) -> str:
		"""回答为什么推荐某个套餐的问题"""
		if not context:
			return "请提供具体的套餐名称，我可以为您解释推荐理由。"
		
		# 收集上下文或问题中出现的套餐名称（按出现顺序输出）
		matched_names: List[str] = []
		blob = f"{context} {question}"
		for package_name in self.knowledge_base.keys():
			if package_name in blob:
				matched_names.append(package_name)
		
		if not matched_names:
			return "请提供具体的套餐名称，我可以为您详细解释推荐理由。"
		
		explanations: List[str] = []
		for idx, package_name in enumerate(matched_names, 1):
			package_info = self.knowledge_base[package_name]
			
			# 使用过滤后的项目（若有用户上下文）
			key_features = package_info.get('key_features', [])
			if self.last_user_profile:
				key_features = self.filter_features_by_gender(key_features, self.last_user_profile.get('gender', 'male'))
			
			reasons = []
			title = f"**{package_name}**的推荐理由：" if len(matched_names) == 1 else f"{idx}. **{package_name}**的推荐理由："
			reasons.append(title)
			reasons.append(f"- 适用人群/说明：{package_info.get('description', '')}")
			reasons.append(f"- 核心检查项目：{', '.join(key_features[:6])}{'...' if len(key_features) > 6 else ''}")
			if package_info.get('health_focus'):
				reasons.append(f"- 健康关注点：{', '.join(package_info.get('health_focus', []))}")
			
			if 'price' in package_info:
				price = package_info['price']
				if isinstance(price, dict):
					reasons.append(f"- 价格：男 {price.get('male', 0)} 元 / 女 {price.get('female', 0)} 元")
				else:
					reasons.append(f"- 价格：{price} 元")
			
			explanations.append("\n".join(reasons))
		
		return "\n\n".join(explanations)
	
	def _answer_what_is(self, question: str) -> str:
		"""回答检查项目相关问题"""
		for exam_name, exam_info in self.examination_details.items():
			if exam_name.lower() in question.lower() or any(keyword in question.lower() for keyword in exam_name.lower().split()):
				response = f"**{exam_name}**：\n"
				response += f"- **用途**：{exam_info.get('purpose', '未知')}\n"
				if 'normal_range' in exam_info:
					response += f"- **正常范围**：{exam_info['normal_range']}\n"
				if 'clinical_significance' in exam_info:
					response += f"- **临床意义**：{exam_info['clinical_significance']}"
				return response
		
		# 如果没有找到具体的检查项目，提供通用回答
		return "请提供具体的检查项目名称，我可以为您详细介绍该项目的用途和临床意义。"
	
	def _answer_price(self, question: str) -> str:
		"""回答价格相关问题"""
		for package_name in self.knowledge_base.keys():
			if package_name in question:
				package_info = self.knowledge_base[package_name]
				price = package_info.get('price', 0)
				
				if isinstance(price, dict):
					return f"{package_name}的价格：男性 {price.get('male', 0)} 元，女性 {price.get('female', 0)} 元"
				else:
					return f"{package_name}的价格：{price} 元"
		
		# 提供价格区间信息
		return """我院体检套餐价格区间如下：
- 经济型套餐：150-700元（如入职体检、基础套餐）
- 标准型套餐：700-1500元（如综合体检套餐）
- 高端型套餐：1500-3000元（如全面体检套餐）
- 豪华型套餐：3000元以上（如VIP体检套餐）

请告诉我您感兴趣的具体套餐，我可以提供详细价格信息。"""
	
	def _answer_suitable(self, question: str) -> str:
		"""回答适合性相关问题"""
		return """为了给您推荐最合适的体检套餐，请提供以下信息：

1. **基本信息**：年龄、性别
2. **预算范围**：您的体检预算
3. **健康关注点**：如肿瘤筛查、心血管健康等
4. **体检目的**：如常规体检、入职体检、婚前体检等
5. **家族史**：如有肿瘤、心血管疾病等家族史
6. **生活习惯**：如吸烟、饮酒等

有了这些信息，我可以为您推荐3-5个最适合的体检套餐。"""
	
	def _general_answer(self, question: str) -> str:
		"""通用回答"""
		# 尝试关键词搜索
		results = self._search_packages_by_keyword(question)
		if results:
			response = "根据您的问题，我找到了以下相关套餐：\n\n"
			for i, result in enumerate(results[:3], 1):
				package_name = result["package"]
				package_info = result["info"]
				price = package_info.get('price', 0)
				if isinstance(price, dict):
					price_str = f"男{price.get('male', 0)}元/女{price.get('female', 0)}元"
				else:
					price_str = f"{price}元"
				
				# 使用过滤后的核心项目摘要
				features = package_info.get('key_features', [])
				if self.last_user_profile:
					features = self.filter_features_by_gender(features, self.last_user_profile.get('gender', 'male'))
				
				response += f"{i}. **{package_name}**（{price_str}）\n"
				response += f"   核心项目：{', '.join(features[:3])}{'...' if len(features) > 3 else ''}\n"
				response += f"   {package_info.get('description', '')}\n\n"
			
			return response
		
		return """我是体检套餐推荐助手，可以帮您：

1. �� **个性化套餐推荐** - 根据您的年龄、性别、预算等推荐合适套餐
2. 🔍 **检查项目解释** - 解释各种检查项目的用途和意义
3. 💰 **价格咨询** - 提供各套餐的价格信息
4. ❓ **答疑解惑** - 回答体检相关问题

请告诉我您的具体需求，我会为您提供专业的建议！"""

	def _compose_reason(self, package_name: str, package_info: dict, user_profile: dict, filtered_features: list[str]) -> str:
		"""当知识库未提供理由时，自动拼装一句推荐理由。"""
		parts: list[str] = []
		gender = user_profile.get("gender") or "male"
		budget = user_profile.get("budget") or 0
		purpose = user_profile.get("purpose") or "常规体检"
		price = package_info.get("price")
		cur_price = None
		if isinstance(price, dict):
			cur_price = price.get(gender) or price.get("male") or price.get("female")
		else:
			cur_price = price
		if budget and isinstance(cur_price, (int, float)) and cur_price:
			if cur_price <= budget:
				parts.append(f"价格在预算内(¥{cur_price:.0f}/预算¥{budget:.0f})")
			else:
				parts.append(f"略超预算(¥{cur_price:.0f}/预算¥{budget:.0f})")
		# 核心项目
		feats = [f for f in (filtered_features or package_info.get('key_features') or []) if f]
		if feats:
			parts.append("包含" + "、".join(feats[:3]))
		# 标签/高危/亮点
		focuses = self._effective_tags(package_info)
		if focuses:
			parts.append("标签命中：" + "、".join(focuses[:3]))
		label = self._match_risk_for_code(package_info.get("code"), user_profile)
		if label:
			parts.append(f"高危匹配：{label}")
		if self.use_full_items_enhance and package_info.get("highlights_parsed"):
			parts.append("亮点：" + "、".join(package_info.get("highlights_parsed")[:3]))
		# 约束提示
		check = self._check_constraints(package_info, user_profile)
		if check.get("messages"):
			parts.extend(check.get("messages"))
		# 目的
		if purpose:
			parts.append(f"适合{purpose}")
		return "；".join(parts) or "基础体检需求匹配，项目覆盖全面"

	def _infer_declared_gender_from_name(self, name: str) -> Optional[str]:
		if not name:
			return None
		if "女士" in name or "(女" in name or "女)" in name:
			return "female"
		if "男士" in name or "(男" in name or "男)" in name:
			return "male"
		return None

	def _infer_gender(self, package_info: Dict[str, Any]) -> Optional[str]:
		name = str(package_info.get("name", ""))
		decl = self._infer_declared_gender_from_name(name)
		if decl:
			return decl
		# 由项目关键词推断
		feats = " ".join([str(x) for x in (package_info.get("key_features") or [])])
		female_kws = ["子宫", "卵巢", "乳腺", "妇科", "HPV", "TCT"]
		male_kws = ["前列腺", "PSA"]
		if any(k in feats for k in female_kws):
			return "female"
		if any(k in feats for k in male_kws):
			return "male"
		return None

	def _concern_specific_bonus(self, package_name: str, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> float:
		"""对明确关注点（如糖尿病/高血压）命名命中时给额外加分。"""
		bonus = 0.0
		health_concerns = [str(x) for x in user_profile.get("health_concerns", []) or []]
		name = str(package_name)
		eff_tags = self._effective_tags(package_info)
		for c in health_concerns:
			if not c:
				continue
			if c in name:
				bonus += 0.5
			elif any(c in t for t in eff_tags):
				bonus += 0.35
		return min(bonus, 1.0)

	def _check_constraints(self, package_info: Dict[str, Any], user_profile: Dict[str, Any]) -> Dict[str, Any]:
		"""返回 {violated: bool, messages: [..]}，用于降分/提示。"""
		messages: List[str] = []
		violated = False
		name = str(package_info.get("name", ""))
		age = int(user_profile.get("age") or 0)
		marital_status = str(user_profile.get("marital_status") or "")  # 可选："已婚"/"未婚"
		gender = str(user_profile.get("gender") or "male")
		category = str(package_info.get("category") or "")
		# 婚前/已婚限制（名称与 full_items 解析）
		if "婚前" in name:
			if marital_status and marital_status != "未婚":
				violated = True
				messages.append("此套餐建议未婚人群进行")
		if self.use_full_items_enhance:
			parsed = package_info.get("constraints_parsed") or {}
			if parsed.get("married_only") and marital_status and marital_status != "已婚":
				violated = True
				messages.append("含限已婚项目，未婚不建议选择")
			# 专属项目提示
			if parsed.get("contains_female_specific") and gender == "male":
				messages.append("包含女性专属项目")
			if parsed.get("contains_male_specific") and gender == "female":
				messages.append("包含男性专属项目")
			if parsed.get("child_preferred") and age and age >= 18:
				violated = True
				messages.append("此套餐/部分项目更适合18岁以下人群")
		# 年龄建议（启发式）：
		if category == "寻系列套餐":
			# 乳腺/生殖有女性年龄建议
			if "乳腺" in name and gender == "female" and age and age < 40:
				messages.append("乳腺癌筛查建议40岁及以上优先")
			if "女性生殖" in name and gender == "female" and age and age < 25:
				messages.append("女性生殖肿瘤筛查建议25岁及以上优先")
		# 儿童套餐
		if "宠爱宝贝" in name and age and age >= 18:
			violated = True
			messages.append("此套餐面向18岁以下儿童/青少年")
		return {"violated": violated, "messages": messages}

def create_recommendation_agent():
	"""创建推荐agent实例"""
	return PackageRecommendationAgent()

def list_ui_packages() -> list:
    """对接版不再依赖 reco，返回空（UI已移除）。"""
    return []