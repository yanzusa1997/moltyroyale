from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum

class TerrainType(str, Enum):
    PLAINS = "plains"
    FOREST = "forest"
    HILLS = "hills"
    RUINS = "ruins"
    WATER = "water"

class WeatherType(str, Enum):
    CLEAR = "clear"
    RAIN = "rain"
    FOG = "fog"
    STORM = "storm"

class ActionType(str, Enum):
    MOVE = "move"
    EXPLORE = "explore"
    ATTACK = "attack"
    USE_ITEM = "useItem"
    INTERACT = "interact"
    PICKUP = "pickup"
    EQUIP = "equip"
    REST = "rest"
    TALK = "talk"
    WHISPER = "whisper"
    BROADCAST = "broadcast"

class Item(BaseModel):
    id: str
    typeId: str
    category: str
    name: Optional[str] = None
    quantity: int = 1

class Unit(BaseModel):
    id: str
    type: str  # 'agent' or 'monster'
    name: Optional[str]
    hp: int
    maxHp: int
    position: str  # regionId

class AgentState(BaseModel):
    id: str
    name: str
    hp: int
    maxHp: int
    ep: int
    maxEp: int
    atk: int
    def_: int = 0  # 'def' is keyword
    vision: int
    regionId: str
    inventory: List[Item]
    equippedWeapon: Optional[Item]
    isAlive: bool
    kills: int
    recentMessages: List[Dict[str, Any]] = []
    
    class Config:
        fields = {'def_': 'def'}

class GameState(BaseModel):
    status: str  # waiting, running, finished
    currentTurn: int
    timeRemaining: Optional[int]
    regions: Dict[str, Any]  # Simplified
    units: List[Unit]
    items: List[Dict[str, Any]]