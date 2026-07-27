"""
Lead Category Definitions
=========================
Central config for interest-based lead collection.

Each LeadCategory defines:
  keywords             — product/topic terms used to expand search queries
  intent_phrases       — phrases that signal buying intent when found in text
  source_types         — which collectors to activate (web/social/news/directories/github)
  minimum_quality_score— minimum score the quality engine must award before saving

Usage
-----
    from config.lead_categories import get_category, list_categories

    cat = get_category('laptops')
    print(cat.keywords)   # ['laptop', 'gaming laptop', ...]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class LeadCategory:
    category_name: str
    keywords: List[str]
    intent_phrases: List[str]
    source_types: List[str]          # subset of: web, social, news, directories, github
    minimum_quality_score: float = 35.0


CATEGORIES: Dict[str, LeadCategory] = {

    'electrical_appliances': LeadCategory(
        category_name='Electrical Appliances',
        keywords=[
            'washing machine', 'fridge', 'refrigerator', 'air conditioner',
            'microwave', 'dishwasher', 'home appliances', 'electric oven',
            'vacuum cleaner', 'water heater',
        ],
        intent_phrases=[
            'looking for', 'need', 'recommend', 'best', 'where to buy',
            'supplier', 'repair', 'buy', 'price', 'quote',
        ],
        source_types=['web', 'directories', 'news'],
        minimum_quality_score=40.0,
    ),

    'electronics': LeadCategory(
        category_name='Electronics',
        keywords=[
            'electronics', 'consumer electronics', 'gadgets', 'smart devices',
            'headphones', 'speakers', 'cameras', 'televisions', 'LED TV',
            'projector', 'smart TV',
        ],
        intent_phrases=[
            'looking for', 'buy', 'recommend', 'best', 'compare',
            'supplier', 'wholesale', 'distributor',
        ],
        source_types=['web', 'directories', 'social'],
        minimum_quality_score=35.0,
    ),

    'laptops': LeadCategory(
        category_name='Laptops',
        keywords=[
            'laptop', 'gaming laptop', 'business laptop', 'MacBook',
            'Dell laptop', 'Lenovo laptop', 'HP laptop', 'notebook computer',
            'ultrabook', 'laptop accessories',
        ],
        intent_phrases=[
            'need laptop', 'looking for laptop', 'recommend laptop',
            'buy laptop', 'best laptop', 'laptop supplier', 'laptop dealer',
            'bulk laptops', 'laptop wholesale',
        ],
        source_types=['web', 'directories', 'social', 'news'],
        minimum_quality_score=35.0,
    ),

    'phones': LeadCategory(
        category_name='Phones',
        keywords=[
            'smartphone', 'mobile phone', 'iPhone', 'Samsung Galaxy',
            'Android phone', 'phone accessories', 'mobile accessories',
            'refurbished phone', 'phone wholesale',
        ],
        intent_phrases=[
            'looking for', 'buy', 'recommend', 'upgrade', 'phone supplier',
            'mobile dealer', 'best phone', 'where to buy', 'bulk order',
        ],
        source_types=['web', 'directories', 'social'],
        minimum_quality_score=35.0,
    ),

    'clothes': LeadCategory(
        category_name='Clothes',
        keywords=[
            'fashion', 'clothes', 'clothing', 'shoes', 'bags', 'boutique',
            'apparel', 'garments', 'fashion accessories', 'sportswear',
            'wholesale clothing', 'fabric',
        ],
        intent_phrases=[
            'looking for', 'supplier', 'wholesale', 'buy', 'recommend',
            'clothing manufacturer', 'fabric supplier', 'fashion designer',
            'bulk order', 'private label',
        ],
        source_types=['web', 'directories', 'social'],
        minimum_quality_score=35.0,
    ),

    'furniture': LeadCategory(
        category_name='Furniture',
        keywords=[
            'furniture', 'office furniture', 'home furniture', 'sofa',
            'bedroom furniture', 'wooden furniture', 'modular furniture',
            'furniture manufacturer', 'interior furniture',
        ],
        intent_phrases=[
            'looking for', 'need', 'recommend', 'buy', 'supplier',
            'furniture manufacturer', 'custom furniture', 'wholesale',
            'bulk furniture', 'furnishing project',
        ],
        source_types=['web', 'directories', 'news'],
        minimum_quality_score=40.0,
    ),

    'beauty': LeadCategory(
        category_name='Beauty Products',
        keywords=[
            'beauty products', 'cosmetics', 'skincare', 'makeup', 'perfume',
            'hair care', 'salon products', 'beauty supplier', 'organic beauty',
            'nail products', 'beauty wholesale',
        ],
        intent_phrases=[
            'looking for', 'recommend', 'supplier', 'wholesale', 'buy',
            'distributor', 'natural products', 'best products', 'bulk order',
        ],
        source_types=['web', 'directories', 'social'],
        minimum_quality_score=35.0,
    ),

    'real_estate': LeadCategory(
        category_name='Real Estate',
        keywords=[
            'real estate', 'property', 'apartment', 'villa', 'commercial property',
            'office space', 'land for sale', 'real estate agent', 'property investment',
            'residential property', 'real estate developer',
        ],
        intent_phrases=[
            'looking for', 'buy', 'invest', 'rent', 'property for sale',
            'seeking', 'interested in', 'need office', 'find apartment',
            'property inquiry', 'real estate lead',
        ],
        source_types=['web', 'directories', 'news'],
        minimum_quality_score=45.0,
    ),

    'cars': LeadCategory(
        category_name='Cars',
        keywords=[
            'car', 'automobile', 'SUV', 'sedan', 'electric vehicle', 'EV',
            'used car', 'car dealer', 'auto parts', 'car accessories',
            'car showroom', 'fleet vehicles',
        ],
        intent_phrases=[
            'looking for', 'buy', 'sell', 'test drive', 'best car',
            'car price', 'auto dealer', 'car supplier', 'fleet purchase',
            'vehicle inquiry',
        ],
        source_types=['web', 'directories', 'news'],
        minimum_quality_score=45.0,
    ),

    'restaurants': LeadCategory(
        category_name='Restaurants',
        keywords=[
            'restaurant', 'cafe', 'catering', 'food supplier', 'kitchen equipment',
            'restaurant supplier', 'food service', 'hospitality', 'bakery',
            'food ingredients', 'restaurant equipment',
        ],
        intent_phrases=[
            'looking for', 'supplier', 'recommend', 'food ingredients',
            'catering service', 'opening restaurant', 'need chef',
            'kitchen supply', 'food distributor',
        ],
        source_types=['web', 'directories', 'social'],
        minimum_quality_score=40.0,
    ),

    'software': LeadCategory(
        category_name='Software',
        keywords=[
            'software', 'SaaS', 'ERP', 'CRM', 'accounting software',
            'project management software', 'HR software', 'cloud software',
            'business software', 'enterprise software',
        ],
        intent_phrases=[
            'looking for', 'need', 'recommend', 'buy', 'alternative to',
            'software vendor', 'evaluate', 'trial', 'pricing', 'demo request',
            'switch from',
        ],
        source_types=['web', 'social', 'github', 'news'],
        minimum_quality_score=35.0,
    ),

    'marketing': LeadCategory(
        category_name='Marketing Services',
        keywords=[
            'digital marketing', 'SEO', 'social media marketing', 'PPC',
            'content marketing', 'email marketing', 'advertising agency',
            'marketing consultant', 'brand strategy', 'lead generation',
        ],
        intent_phrases=[
            'looking for', 'need', 'hire', 'recommend', 'marketing agency',
            'grow my business', 'increase sales', 'lead generation',
            'marketing budget', 'ROI improvement',
        ],
        source_types=['web', 'social', 'directories', 'news'],
        minimum_quality_score=35.0,
    ),

    'education': LeadCategory(
        category_name='Education',
        keywords=[
            'online course', 'training', 'e-learning', 'tutoring', 'bootcamp',
            'certification', 'professional development', 'corporate training',
            'learning management', 'skills training',
        ],
        intent_phrases=[
            'looking for', 'enroll', 'learn', 'need training', 'study',
            'recommend course', 'certification program', 'upskill',
            'team training', 'corporate learning',
        ],
        source_types=['web', 'social', 'directories'],
        minimum_quality_score=35.0,
    ),

    'healthcare': LeadCategory(
        category_name='Healthcare Services',
        keywords=[
            'medical equipment', 'healthcare services', 'clinic', 'hospital supply',
            'pharmaceutical', 'medical devices', 'health products', 'telemedicine',
            'medical supplier', 'diagnostic equipment',
        ],
        intent_phrases=[
            'looking for', 'need', 'supplier', 'medical supply', 'quote',
            'healthcare provider', 'equipment dealer', 'bulk medical',
            'procurement', 'hospital tender',
        ],
        source_types=['web', 'directories', 'news'],
        minimum_quality_score=45.0,
    ),

    'home_services': LeadCategory(
        category_name='Home Services',
        keywords=[
            'home renovation', 'interior design', 'plumbing', 'electrical work',
            'cleaning service', 'pest control', 'HVAC', 'roofing', 'landscaping',
            'home contractor', 'maintenance services',
        ],
        intent_phrases=[
            'looking for', 'need', 'recommend', 'hire', 'quote',
            'home contractor', 'service provider', 'fix my',
            'renovation project', 'maintenance needed',
        ],
        source_types=['web', 'directories', 'social'],
        minimum_quality_score=40.0,
    ),

    'business_services': LeadCategory(
        category_name='Business Services',
        keywords=[
            'accounting services', 'legal services', 'HR services', 'logistics',
            'supply chain', 'outsourcing', 'consulting', 'IT services',
            'payroll services', 'business consulting',
        ],
        intent_phrases=[
            'looking for', 'need', 'hire', 'outsource', 'recommend',
            'service provider', 'consultant', 'quote request',
            'proposal needed', 'RFP',
        ],
        source_types=['web', 'directories', 'news'],
        minimum_quality_score=40.0,
    ),

}


def get_category(name: str) -> Optional[LeadCategory]:
    """Return a LeadCategory by slug or display name (case-insensitive).

    Examples:
        get_category('laptops')              # by slug
        get_category('Electrical Appliances')# by display name
    """
    key = name.lower().strip().replace(' ', '_').replace('-', '_')
    cat = CATEGORIES.get(key)
    if cat:
        return cat
    # Fall back to display name match
    name_lower = name.lower().strip()
    for cat in CATEGORIES.values():
        if cat.category_name.lower() == name_lower:
            return cat
    return None


def list_categories() -> List[str]:
    """Return sorted list of category slugs."""
    return sorted(CATEGORIES.keys())


def list_category_names() -> List[str]:
    """Return sorted list of human-readable category display names."""
    return sorted(cat.category_name for cat in CATEGORIES.values())
