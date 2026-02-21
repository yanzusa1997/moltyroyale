from models import AgentState, TerrainType, WeatherType
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

class TerrainPriority:
    """Strategic terrain evaluation"""
    
    TERRAIN_SCORES = {
        TerrainType.HILLS: 100,   # Best vision for PVP
        TerrainType.RUINS: 85,    # High item find rate
        TerrainType.PLAINS: 70,   # Good vision
        TerrainType.FOREST: 50,   # Stealth, but poor vision
        TerrainType.WATER: 20,    # Avoid if possible
    }
    
    @classmethod
    def get_score(cls, terrain: str) -> int:
        return cls.TERRAIN_SCORES.get(terrain, 40)

class CombatEvaluator:
    """Evaluate combat situations"""
    
    @staticmethod
    def should_attack(agent: AgentState, target: Dict[str, Any]) -> Tuple[bool, str]:
        """Decide whether to attack a target"""
        
        # Safety first
        if agent.hp < 40:
            return False, "HP too low"
        
        if agent.ep < 2:
            return False, "Not enough EP"
        
        # Target analysis
        target_hp = target.get('hp', 100)
        target_atk = target.get('atk', 10)
        target_def = target.get('def', 5)
        
        # Calculate advantage
        atk_advantage = agent.atk - target_def
        def_advantage = agent.def_ - target_atk
        
        # Strategic decisions
        if target_hp < 30:  # Weak target
            if atk_advantage > 5:
                return True, "Easy kill"
        
        elif atk_advantage > 15:  # Strong advantage
            if agent.hp > 60:
                return True, "Strong advantage"
        
        elif target_atk > agent.atk + 20:  # Too dangerous
            return False, "Target too strong"
        
        # Default: don't attack
        return False, "Not advantageous"
    
    @staticmethod
    def should_flee(agent: AgentState, nearby_threats: List[Dict]) -> bool:
        """Decide if we need to run"""
        
        if not nearby_threats:
            return False
        
        # Count threats
        strong_threats = sum(1 for t in nearby_threats 
                            if t.get('atk', 0) > agent.def_ + 15)
        
        # Flee conditions
        if agent.hp < 30:
            return True
        
        if strong_threats >= 2:
            return True
        
        if len(nearby_threats) >= 3:
            return True
        
        return False

class ItemManager:
    """Smart item management"""
    
    @staticmethod
    def get_best_weapon(inventory: List[Dict]) -> Optional[Dict]:
        """Find best weapon in inventory"""
        weapons = [item for item in inventory 
                  if item.get('category') == 'weapon']
        
        if not weapons:
            return None
        
        # Sort by damage (simplified)
        return max(weapons, key=lambda w: w.get('atkBonus', 0))
    
    @staticmethod
    def need_healing(agent: AgentState) -> bool:
        """Check if healing needed"""
        hp_percent = (agent.hp / agent.maxHp) * 100
        
        if hp_percent < 30:
            return True  # Critical
        elif hp_percent < 50 and agent.ep >= 1:
            return True  # Low but can heal
        return False
    
    @staticmethod
    def get_best_healing_item(inventory: List[Dict]) -> Optional[Dict]:
        """Find best healing item"""
        healing_items = [item for item in inventory 
                        if item.get('category') == 'recovery']
        
        if not healing_items:
            return None
        
        # Prefer items that restore more HP
        return max(healing_items, 
                  key=lambda i: i.get('hpRestore', 0))

class DeathZoneAvoider:
    """Avoid death zone"""
    
    @staticmethod
    def is_in_death_zone(region: Dict[str, Any]) -> bool:
        """Check if region is in death zone"""
        return region.get('isDeathZone', False)
    
    @staticmethod
    def find_safe_direction(current_region: Dict, adjacent_regions: List[Dict]) -> Optional[str]:
        """Find direction away from death zone"""
        
        # If in death zone, any direction is better
        if DeathZoneAvoider.is_in_death_zone(current_region):
            for adj in adjacent_regions:
                if adj and not DeathZoneAvoider.is_in_death_zone(adj):
                    return adj.get('direction')
        
        # Check if death zone is expanding toward us
        return None