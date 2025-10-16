# -*- coding: utf-8 -*-
"""
套餐推荐系统
"""

from .recommendation_agent import create_recommendation_agent, PackageRecommendationAgent

__version__ = "1.0.0"
__all__ = [
    "PackageRecommendationAgent",
    "create_recommendation_agent",
] 