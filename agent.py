import time
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from loguru import logger
import schedule

from api_client import APIClient, MaintenanceError
from models import AgentState, GameState, ActionType
from strategy import CombatEvaluator, ItemManager, DeathZoneAvoider, TerrainPriority

class MoltyAgent:
    def __init__(self, agent_name: str = "ProBot"):
        self.agent_name = agent_name
        self.api_client = APIClient()
        self.account_id = None
        self.api_key = None
        self.game_id = None
        self.agent_id = None
        self.current_state: Optional[AgentState] = None
        self.game_start_time = None
        self.last_action_time = None
        self.consecutive_errors = 0
        self.in_maintenance = False
        
    def setup(self):
        """Initial setup: create account and get API key"""
        try:
            # Step 1: Create account
            logger.info("Creating new account...")
            result = self.api_client.create_account(self.agent_name)
            
            if result.get('success'):
                account_data = result['data']
                self.account_id = account_data['accountId']
                self.api_key = account_data['apiKey']
                
                # Save API key to file (CRITICAL!)
                with open('api_key.txt', 'w') as f:
                    f.write(f"API Key: {self.api_key}\n")
                    f.write(f"Account ID: {self.account_id}\n")
                    f.write(f"Verification Code: {account_data['verificationCode']}\n")
                
                logger.success(f"Account created! API Key saved to api_key.txt")
                logger.info(f"Verification Code: {account_data['verificationCode']}")
                
                # Update API client with key
                self.api_client.api_key = self.api_key
                self.api_client.session.headers.update({"X-API-Key": self.api_key})
                
                return True
            else:
                logger.error("Failed to create account")
                return False
                
        except MaintenanceError:
            self.in_maintenance = True
            logger.warning("Server under maintenance, cannot setup")
            return False
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            return False
    
    def find_or_create_game(self):
        """Find waiting game or create new one"""
        try:
            # Try to find waiting game
            games = self.api_client.get_waiting_games()
            
            if games.get('success') and games.get('data'):
                # Join first available game
                self.game_id = games['data'][0]['id']
                logger.info(f"Joined existing game: {self.game_id}")
                return True
            
            # Create new game
            logger.info("No waiting games, creating new...")
            new_game = self.api_client.create_game()
            
            if new_game.get('success'):
                self.game_id = new_game['data']['id']
                logger.info(f"Created new game: {self.game_id}")
                return True
            
            return False
            
        except MaintenanceError:
            self.in_maintenance = True
            logger.warning("Server under maintenance")
            return False
        except Exception as e:
            logger.error(f"Failed to find/create game: {e}")
            return False
    
    def register(self):
        """Register agent in game"""
        try:
            result = self.api_client.register_agent(self.game_id, f"{self.agent_name}_AI")
            
            if result.get('success'):
                agent_data = result['data']
                self.agent_id = agent_data['id']
                logger.success(f"Agent registered! ID: {self.agent_id}")
                logger.info(f"Initial stats: HP={agent_data['hp']}, EP={agent_data['ep']}")
                return True
            else:
                logger.error(f"Registration failed: {result}")
                return False
                
        except MaintenanceError:
            self.in_maintenance = True
            logger.warning("Server under maintenance")
            return False
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return False
    
    def get_game_state(self) -> Optional[Dict[str, Any]]:
        """Get current game state"""
        if not self.game_id or not self.agent_id:
            return None
        
        state = self.api_client.get_agent_state(self.game_id, self.agent_id)
        
        if state and state.get('success'):
            self.current_state = AgentState(**state['data'])
            self.consecutive_errors = 0
            return state['data']
        else:
            self.consecutive_errors += 1
            return None
    
    def decide_action(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Core AI decision making"""
        
        # Parse state into objects
        agent = AgentState(**state)
        
        # Priority 1: Check for death zone
        current_region = state.get('regions', {}).get(agent.regionId, {})
        if DeathZoneAvoider.is_in_death_zone(current_region):
            logger.warning("IN DEATH ZONE! MUST MOVE!")
            # Find safe direction
            adjacent = state.get('adjacentRegions', [])
            safe_dir = DeathZoneAvoider.find_safe_direction(current_region, adjacent)
            if safe_dir:
                return {"action": ActionType.MOVE, "target": safe_dir}
        
        # Priority 2: Check health
        if ItemManager.need_healing(agent):
            healing_item = ItemManager.get_best_healing_item(agent.inventory)
            if healing_item:
                logger.info(f"Using healing item: {healing_item.get('name')}")
                return {
                    "action": ActionType.USE_ITEM,
                    "target": healing_item['id'],
                    "data": {"targetId": healing_item['id']}
                }
        
        # Priority 3: Check for threats in same region
        units_in_region = [u for u in state.get('units', []) 
                          if u.get('position') == agent.regionId 
                          and u.get('id') != agent.id]
        
        if units_in_region:
            # Evaluate each threat
            for unit in units_in_region:
                should_attack, reason = CombatEvaluator.should_attack(agent, unit)
                if should_attack:
                    logger.info(f"Attacking {unit.get('name')}: {reason}")
                    return {"action": ActionType.ATTACK, "target": unit['id']}
            
            # Check if we should flee
            if CombatEvaluator.should_flee(agent, units_in_region):
                logger.warning("Too many threats, fleeing!")
                # Move to random adjacent region
                adjacent = state.get('adjacentRegions', [])
                if adjacent:
                    safe_dir = random.choice([a['direction'] for a in adjacent if a])
                    return {"action": ActionType.MOVE, "target": safe_dir}
        
        # Priority 4: Check for items
        items_in_region = [i for i in state.get('items', []) 
                          if i.get('regionId') == agent.regionId]
        
        if items_in_region and len(agent.inventory) < 10:
            # Pick up best item
            valuable_items = sorted(items_in_region, 
                                   key=lambda i: i.get('value', 0), reverse=True)
            if valuable_items:
                logger.info(f"Picking up item: {valuable_items[0].get('name')}")
                return {"action": ActionType.PICKUP, "target": valuable_items[0]['id']}
        
        # Priority 5: Equip better weapon
        if agent.equippedWeapon is None:
            best_weapon = ItemManager.get_best_weapon(agent.inventory)
            if best_weapon:
                logger.info(f"Equipping weapon: {best_weapon.get('name')}")
                return {"action": ActionType.EQUIP, "target": best_weapon['id']}
        
        # Priority 6: Explore or move strategically
        if agent.ep >= 1:
            # Check if we should rest to recover EP
            if agent.ep < 3:  # Low EP
                logger.info("Resting to recover EP")
                return {"action": ActionType.REST}
            
            # Explore current region for items
            if random.random() < 0.3:  # 30% chance to explore
                logger.info("Exploring current region")
                return {"action": ActionType.EXPLORE}
            
            # Move to better region
            adjacent = state.get('adjacentRegions', [])
            if adjacent:
                # Score each adjacent region
                best_region = None
                best_score = -1
                
                for adj in adjacent:
                    if adj:  # Not None (blocked)
                        terrain = adj.get('terrain', 'plains')
                        score = TerrainPriority.get_score(terrain)
                        
                        # Bonus for unexplored
                        if adj.get('explored') == False:
                            score += 20
                        
                        if score > best_score:
                            best_score = score
                            best_region = adj['direction']
                
                if best_region:
                    logger.info(f"Moving to strategic region (score: {best_score})")
                    return {"action": ActionType.MOVE, "target": best_region}
        
        # Default: rest if nothing else to do
        logger.info("No strategic action, resting")
        return {"action": ActionType.REST}
    
    def execute_action(self, action: Dict[str, Any]):
        """Execute decided action"""
        if not self.game_id or not self.agent_id:
            return False
        
        result = self.api_client.send_action(
            self.game_id, 
            self.agent_id,
            action['action'],
            action.get('target'),
            action.get('data')
        )
        
        if result and result.get('success'):
            self.last_action_time = datetime.now()
            logger.info(f"Action {action['action']} successful")
            return True
        else:
            logger.error(f"Action failed: {result}")
            return False
    
    def check_maintenance_window(self) -> bool:
        """Check if we're in maintenance window (09:30-10:30 UTC)"""
        now = datetime.utcnow()
        maintenance_start = now.replace(hour=9, minute=30, second=0)
        maintenance_end = now.replace(hour=10, minute=30, second=0)
        
        if now >= maintenance_start and now <= maintenance_end:
            if not self.in_maintenance:
                logger.warning("Entering maintenance window, pausing all activities")
                self.in_maintenance = True
            return True
        else:
            if self.in_maintenance:
                logger.info("Maintenance window ended, resuming operations")
                self.in_maintenance = False
            return False
    
    def run_game_loop(self):
        """Main game loop"""
        logger.info("Starting game loop...")
        
        while True:
            try:
                # Check maintenance
                if self.check_maintenance_window():
                    logger.info("In maintenance, sleeping 5 minutes...")
                    time.sleep(300)  # Sleep 5 minutes
                    continue
                
                # Get current state
                state = self.get_game_state()
                if not state:
                    if self.consecutive_errors > 5:
                        logger.error("Too many consecutive errors, restarting...")
                        break
                    time.sleep(30)
                    continue
                
                # Check if game is running
                if state.get('status') != 'running':
                    if state.get('status') == 'finished':
                        logger.success(f"Game finished! Kills: {state.get('kills', 0)}")
                        break
                    
                    logger.info(f"Game status: {state.get('status')}, waiting...")
                    time.sleep(30)
                    continue
                
                # Check if agent is alive
                if not state.get('isAlive', True):
                    logger.error("Agent died! Game over.")
                    break
                
                # Log current status
                logger.info(f"Status: HP={state['hp']}/{state['maxHp']}, "
                           f"EP={state['ep']}/{state['maxEp']}, "
                           f"Kills={state.get('kills', 0)}")
                
                # Decide and execute action
                action = self.decide_action(state)
                self.execute_action(action)
                
                # Wait for next turn (60 seconds real time)
                # But if we used Rest, we can act again in 0 seconds?
                # Actually Rest is group 1 action, so still need 60s
                time.sleep(60)
                
            except MaintenanceError:
                self.in_maintenance = True
                logger.warning("Maintenance detected, waiting...")
                time.sleep(300)
            except KeyboardInterrupt:
                logger.info("Game loop stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in game loop: {e}")
                time.sleep(30)
    
    def run(self):
        """Main execution flow"""
        logger.info(f"Starting Molty Agent: {self.agent_name}")
        
        # Check maintenance first
        if self.check_maintenance_window():
            logger.info("Currently in maintenance window. Waiting...")
            while self.check_maintenance_window():
                time.sleep(60)
        
        # Setup
        if not self.setup():
            logger.error("Setup failed")
            return
        
        # Find or create game
        if not self.find_or_create_game():
            logger.error("Failed to get game")
            return
        
        # Register agent
        if not self.register():
            logger.error("Failed to register")
            return
        
        # Run main loop
        self.run_game_loop()
        
        logger.info("Agent execution completed")