from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os

# 轻量问答引擎：优先尝试调用大模型；缺省走规则兜底，保证离线可跑

SYSTEM_PROMPT = os.getenv("LLM_SYSTEM_PROMPT", (
	"你是专业的体检套餐顾问，请用通俗易懂的语言回答用户问题。\n\n"
	"回答要求：\n"
	"1. 内容要丰富详细，每个要点展开说明（为什么重要、有什么作用、如何理解）\n"
	"2. 适当补充医学背景知识，帮助用户理解，但用白话解释专业术语\n"
	"3. 给出具体的、可操作的建议，不要泛泛而谈\n"
	"4. 结构清晰，使用小标题分段：【结论】【对比】【补充建议】【项目解释】等\n"
	"5. 语言风格口语化、亲切，像医生面对面讲解\n\n"
	"格式要求：\n"
	"- 不要使用markdown格式符号（如**加粗**、*斜体*），直接用文字表达\n"
	"- 可以用数字序号(1. 2. 3.)、短横线(-)来列点，保持简洁\n"
	"- 少用emoji表情符号，只在必要时用简单的符号(如√ ×)\n"
	"- 表格可以用简单的文字列表代替，更易阅读\n\n"
	"严格要求：\n"
	"- 不编造上下文中未出现的价格、项目、数据\n"
	"- 不确定的信息明确说明'根据现有信息无法确定'\n"
	"- 不夸大项目效果，保持客观中立\n"
))

# ---- 工具：按小标题过滤段落 ----

def _filter_sections(text: str, allowed_titles: List[str]) -> str:
	"""过滤输出，只保留指定的小标题部分（支持emoji + 【】格式）"""
	if not text:
		return text
	lines = text.splitlines()
	keep: List[str] = []
	allow = False
	# 兼容新旧格式：【标题】或 emoji **标题**
	allowed_patterns = []
	for t in allowed_titles:
		allowed_patterns.append(f"【{t}】")
		allowed_patterns.append(f"**{t}**")
		# 还支持emoji开头的标题，例如 💡 核心结论
		if t in ["结论", "核心结论", "对比", "详细对比", "项目解释", "项目解读", "体检前注意", "注意事项"]:
			allowed_patterns.append(t)
	
	for ln in lines:
		stripped = ln.strip()
		# 检测是否是标题行
		is_title = False
		if any(stripped.startswith(p) or p in stripped for p in allowed_patterns):
			allow = True
			is_title = True
		# 如果遇到新的markdown标题或分隔线，可能是新章节
		elif stripped.startswith("#") or stripped.startswith("---") or (stripped.startswith("**") and stripped.endswith("**")):
			# 检查是否是允许的标题
			if not any(p in stripped for p in allowed_patterns):
				allow = False
			else:
				allow = True
				is_title = True
		
		if allow:
			keep.append(ln)
	
	return "\n".join(keep).strip() or text

# ---- 基础知识：常见体检项目解释（可扩展） ----
ITEM_EXPLAINS: Dict[str, str] = {
	"糖化血红蛋白": "反映近2-3个月平均血糖控制，糖尿病筛查与管理的重要指标。",
	"HbA1c": "反映近2-3个月平均血糖控制，糖尿病筛查与管理的重要指标。",
	"CA19-9": "消化道（胰腺/胆道等）相关肿瘤标志物，联合其他检查用于风险提示，不能单独诊断。",
	"CA-19-9": "消化道（胰腺/胆道等）相关肿瘤标志物，联合其他检查用于风险提示，不能单独诊断。",
	"CA-125": "卵巢等来源的肿瘤相关肿瘤标志物，常用于女性生殖系统肿瘤风险提示与随访，需结合影像与临床。",
	"CA125": "卵巢等来源的肿瘤相关肿瘤标志物，常用于女性生殖系统肿瘤风险提示与随访，需结合影像与临床。",
	"CA-15-3": "乳腺癌相关肿瘤标志物之一，主要用于乳腺癌患者随访与疗效监测，不用于单独筛查与诊断。",
	"CA153": "乳腺癌相关肿瘤标志物之一，主要用于乳腺癌患者随访与疗效监测，不用于单独筛查与诊断。",
	"TPSA": "前列腺特异性抗原（总），前列腺疾病筛查辅助指标，需结合FPSA及临床。",
	"FPSA": "前列腺特异性抗原（游离），与TPSA联合评估前列腺风险。",
	"甲胎蛋白": "AFP，肝细胞癌等相关肿瘤标志物，需结合影像与其他指标判读。",
	"癌胚抗原": "CEA，多种肿瘤相关非特异标志物，用于风险提示与随访，不作单独诊断。",
	"甲功三项": "甲状腺功能（如TSH/FT3/FT4），用于评估甲状腺功能亢进或减退。",
	"生化26项": "较全面的代谢/肝肾功能/电解质等检测，用于全身代谢与脏器功能评估。",
	"颈动脉超声": "评估颈动脉斑块与狭窄，提示脑卒中等心脑血管风险。",
	"乳腺超声": "无辐射检查乳腺结构与结节，对育龄女性友好。",
	"子宫及附件超声": "妇科超声，评估子宫与卵巢结构，发现囊肿/肌瘤等。",
	"前列腺超声": "评估前列腺体积与结构，辅助前列腺疾病筛查。",
	"骨密度": "评估骨质疏松风险，常用于中老年或绝经后女性。",
	"胸部CT": "低剂量辐射胸部断层成像，较胸片更敏感，用于肺部结节等筛查。",
	"胸片": "常规胸部平片，辐射更低，敏感性较CT低。",
	"心电图": "评估心律与心肌供血情况，筛查心脏节律与缺血问题。",
	"动态血压": "24小时动态血压监测，评估隐匿性高血压与昼夜节律。",
	"14-C呼气试验": "幽门螺杆菌检测的无创方法，阳性提示感染，需医生评估是否治疗。",
	"13-C呼气试验": "幽门螺杆菌检测的无创方法，阳性提示感染，需医生评估是否治疗。",
}

# ---- 体检前注意事项（通用+专项） ----
GENERAL_NOTES: List[str] = [
	"体检前8小时避免进食，体检当天早晨空腹，不饮茶咖啡与酒精。",
	"体检前1-3天清淡饮食，避免高脂高糖与剧烈运动，保证充足睡眠。",
	"例假期间不做妇科检查与尿检（可改期），怀孕或备孕请事先告知。",
	"随身携带身份证件，体检当日提前15分钟到达体检中心。",
]
SPECIAL_NOTES: Dict[str, List[str]] = {
	"胃镜": ["前晚22点后禁食水，遵医嘱停抗凝/降糖药，随行家属更安心。"],
	"结肠镜": ["前一日流食并按医嘱口服泻剂清肠，检查当日禁食。"],
	"胸部CT": ["避免佩戴金属饰品，配合屏气；有妊娠可能者先与医生沟通。"],
	"乳腺超声": ["尽量避开经期前后乳房胀痛期，放松配合检查。"],
	"TCT": ["采样前48小时避免性生活与阴道用药/冲洗，月经期不做。"],
	"HPV": ["采样前48小时避免性生活与阴道用药/冲洗，月经期不做。"],
	"动态血压": ["佩戴期间按日常作息，避免剧烈运动与水浸，记录用药与症状。"],
	"14-C呼气试验": ["检测前2周停用抗生素/抑酸剂，前1天避免酒精与辛辣。"],
	"13-C呼气试验": ["检测前2周停用抗生素/抑酸剂，前1天避免酒精与辛辣。"],
}


def _contains_any(text: str, keywords: List[str]) -> bool:
	lower = text.lower()
	return any(k.lower() in lower for k in keywords)


def _format_bullets(lines: List[str]) -> str:
	return "\n".join([f"- {line}" for line in lines])


def _norm(s: str) -> str:
	"""去除非字母数字，统一小写，用于鲁棒匹配（e.g. CA153/CA-15-3）。"""
	return "".join(ch.lower() for ch in s if ch.isalnum())


def _summarize_packages(pkgs: List[Dict[str, Any]], top_n: int = 3) -> Tuple[str, List[str]]:
	"""生成对比用的简要上下文与亮点要点列表。"""
	if not pkgs:
		return "", []
	pkgs = pkgs[:top_n]
	rows = []
	highlights: List[str] = []
	for p in pkgs:
		name = p.get("name")
		price = p.get("price")
		score = p.get("score")
		diff = p.get("diff_items") or []
		tags = p.get("tags") or []
		reason = p.get("reason") or ""
		rows.append(f"{name}｜¥{price}｜分数{score}｜亮点：{', '.join(diff) if diff else '-'}｜标签：{', '.join(tags) if tags else '-'}")
		if diff:
			highlights.extend(diff)
	ctx = "\n".join(rows)
	return ctx, list(dict.fromkeys(highlights))


def _explain_item_by_rules(question: str) -> Optional[str]:
	q_norm = _norm(question)
	for key, val in ITEM_EXPLAINS.items():
		if key.lower() in question.lower() or _norm(key) in q_norm:
			return f"【项目解释】{key}：{val}"
	return None


def _notes_from_context(highlights: List[str]) -> List[str]:
	notes = list(GENERAL_NOTES)
	for k, v in SPECIAL_NOTES.items():
		if any(k.lower() in h.lower() for h in highlights):
			notes.extend(v)
	return list(dict.fromkeys(notes))


def _has_llm() -> bool:
	return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_1") or os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"))


def _llm_only() -> bool:
	return str(os.getenv("LLM_ONLY", "")).lower() == "true"


def _debug_wrap(text: str, source: str) -> str:
	if str(os.getenv("LLM_DEBUG", "")).lower() == "true":
		return f"[{source}]\n" + text
	return text


def _try_llm(prompt: str) -> Optional[str]:
	"""尝试调用环境可用的大模型。优先：百炼原生（LangChain ChatTongyi -> dashscope）；
	失败再退回 OpenAI 兼容端点。
	支持的环境变量：
	- BAILIAN_API_KEY / DASHSCOPE_API_KEY
	- LLM_MODEL（或 OPENAI_MODEL 兼容）
	- LLM_BASE_URL / OPENAI_BASE_URL（仅用于兼容端点）
	"""
	model_name = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "qwen-plus")
	bailian_key = os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
	if bailian_key:
		# 1) 优先使用 LangChain ChatTongyi（多数环境已安装）
		try:
			from langchain_community.chat_models import ChatTongyi  # type: ignore
			from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore
			llm = ChatTongyi(model=model_name, api_key=bailian_key)
			resp = llm.invoke([SystemMessage(content="你是专业的体检套餐顾问。回答要详细丰富，每个要点展开说明，用通俗语言解释医学概念。"), HumanMessage(content=prompt)])
			text = getattr(resp, "content", None)
			if text:
				return text
		except Exception:
			pass
		# 2) 尝试阿里官方 dashscope SDK（若环境已安装）
		try:
			from dashscope import Generation  # type: ignore
			result = Generation.call(model=model_name, prompt=prompt, api_key=bailian_key)
			# 不同版本SDK字段不同，做尽量宽松的兼容
			if result is not None:
				if hasattr(result, "output_text") and result.output_text:
					return result.output_text  # type: ignore
				out = getattr(result, "output", None)
				if out:
					text = getattr(out, "text", None) or getattr(out, "choices", [{}])[0].get("message", {}).get("content")
					if text:
						return text
		except Exception:
			pass
	# 3) 回退到 OpenAI 兼容端点
	api_key = (
		os.getenv("OPENAI_API_KEY")
		or os.getenv("OPENAI_API_KEY_1")
		or bailian_key  # 允许用百炼key走兼容端点
	)
	if not api_key:
		return None
	base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if bailian_key else None)
	try:
		from openai import OpenAI  # type: ignore
		client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
		resp = client.chat.completions.create(
			model=model_name,
			messages=[
				{"role": "system", "content": "你是专业的体检套餐顾问。回答要详细丰富，每个要点展开说明，用通俗语言解释医学概念。"},
				{"role": "user", "content": prompt},
			],
			temperature=0.3,  # 稍微提高temperature让回答更丰富
		)
		return resp.choices[0].message.content  # type: ignore
	except Exception:
		return None


def build_prompt(question: str, context_text: str) -> str:
	guide = (
		"请基于套餐上下文详细回答问题：\n\n"
		"- 若问比较/推荐：严格按以下结构回答，不要添加其他部分\n"
		"  1. 【结论】首推分数最高的套餐，解释为什么它分数高（匹配了哪些需求/风险点）\n"
		"  2. 【对比】逐个对比各套餐：价格、核心项目、适合人群、分数，每个套餐2-3段话说明特点和优劣\n"
		"  3. 【补充建议】如果其他套餐有明显优势（性价比、特殊项目、适合特定症状），补充说明'如果您有XX情况，也可以考虑XX套餐'\n"
		"  禁止：不要添加【项目解释】【体检前注意】等其他部分（除非用户明确询问）\n\n"
		"- 若问某项目（单独询问某个检查项目）：给【项目解释】（是什么、检查什么、临床意义、适合谁），每点展开说明\n\n"
		"- 若问注意事项/准备（明确提到'注意'、'准备'、'空腹'等）：给【体检前注意】（通用3-5条 + 专项注意），说明原因和做法\n\n"
		"回答要充实详细，每个要点都要展开说明。用简洁的文字表达，不要使用过多markdown符号或emoji。\n"
	)
	return f"【系统提示】\n{SYSTEM_PROMPT}\n\n【上下文】\n{context_text}\n\n【问题】{question}\n\n{guide}"


def answer_question(last_result: Optional[Dict[str, Any]], question: str) -> str:
	"""对外主函数：基于last_result上下文回答。"""
	if not question or not question.strip():
		return "请先输入问题。"

	# 从推荐结果提取候选作为上下文
	recommended: List[Dict[str, Any]] = []
	candidates: List[Dict[str, Any]] = []
	if last_result:
		recommended = last_result.get("recommended") or []
		candidates = last_result.get("candidates") or recommended or []
	pkgs_for_ctx = recommended or candidates
	ctx_text, ctx_highlights = _summarize_packages(pkgs_for_ctx, top_n=3)

	q_lower = question.lower()

	# 1) 项目解释优先命中：若已配置LLM则优先用LLM，失败再回退本地规则；若 LLM_ONLY 则不回退
	if _contains_any(q_lower, ["是啥", "是什么", "检查什么", "查什么", "做什么", "意义", "用途"]) or any(_norm(k) in _norm(question) for k in ITEM_EXPLAINS.keys()):
		if _has_llm():
			ans = _try_llm(build_prompt(question, ctx_text))
			if ans:
				# 仅保留【项目解释】一节
				return _debug_wrap(_filter_sections(ans, ["项目解释"]), "LLM")
			if _llm_only():
				return "当前大模型未可用或响应为空，请检查 Key/模型名/网络。"
		# 规则回退
	item_explain = _explain_item_by_rules(question)
	if item_explain:
		# 仅当问题询问注意/空腹/准备时，才附加注意事项
		if _contains_any(q_lower, ["注意", "准备", "空腹", "须知", "禁食", "喝水", "药"]):
			notes = _notes_from_context(ctx_highlights)
			return _debug_wrap("\n".join([
				item_explain,
				"",
				"【体检前注意】",
				_format_bullets(notes),
			]), "规则")
		# 默认只返回项目解释
		return _debug_wrap(item_explain, "规则")

	# 2) 体检前注意
	if _contains_any(q_lower, ["注意", "准备", "空腹", "体检前", "须知", "禁食", "喝水", "药"]):
		# 若强制或偏好使用LLM，则先走LLM
		if _has_llm() and (_llm_only() or str(os.getenv("LLM_PREFER_NOTES", "")).lower() == "true"):
			llm_resp = _try_llm(build_prompt(question, ctx_text))
			if llm_resp:
				# 仅保留【体检前注意】一节
				return _debug_wrap(_filter_sections(llm_resp, ["体检前注意"]), "LLM")
			if _llm_only():
				return "当前大模型未可用或响应为空，请检查 Key/模型名/网络。"
		# 规则回退
		notes = _notes_from_context(ctx_highlights)
		return _debug_wrap("\n".join([
			"【体检前注意】",
			_format_bullets(notes),
		]), "规则")

	# 3) 套餐比较/为何选择
	if _contains_any(q_lower, ["比较", "区别", "选哪个", "推荐哪个", "更推荐哪个", "哪个更推荐", "哪个更合适", "哪个更好", "最推荐", "为什么选", "为何选择", "为什么推荐", "为啥推荐", "为啥选", "推荐原因", "推荐这几个", "怎么选", "如何选", "推荐理由", "哪个好", "差异", "更合适", "更好"]):
		if not pkgs_for_ctx:
			return "当前没有推荐结果可用于比较，请先生成上方推荐。"
		# 对比问题：优先使用LLM（比规则更丰富），除非明确禁用
		if _has_llm():
			llm_resp = _try_llm(build_prompt(question, ctx_text))
			if llm_resp:
				# 对比问题：不过滤，直接返回完整内容（LLM会按提示词输出【结论】【对比】）
				return _debug_wrap(llm_resp, "LLM")
			if _llm_only():
				return "当前大模型未可用或响应为空，请检查 Key/模型名/网络。"
		# 规则回退：给出结论+简要对比
		first = pkgs_for_ctx[0]
		lines = [
			"【结论】",
			f"更推荐『{first.get('name')}』，理由：{first.get('reason') or '综合得分更高'}",
			"",
			"【对比】",
			ctx_text
		]
		return _debug_wrap("\n".join(lines), "规则")

	# 4) 其它问题：若有LLM则尝试；LLM_ONLY 失败则直接提示
	if _has_llm():
		llm_resp = _try_llm(build_prompt(question, ctx_text))
		if llm_resp:
			return _debug_wrap(llm_resp, "LLM")
		if _llm_only():
			return "当前大模型未可用或响应为空，请检查 Key/模型名/网络。"

	# 5) 兜底
	return _debug_wrap("\n".join([
		"抱歉，基于现有信息无法准确回答。",
		"您可以具体到'某个项目'或'两种套餐的比较'。",
		"先提供通用体检前注意：",
		_format_bullets(GENERAL_NOTES),
	]), "规则") 