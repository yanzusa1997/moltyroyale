import time
import random
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from loguru import logger
import os
import sys

from api_client import APIClient, MaintenanceError, APIError
from models import AgentState
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
        self.account_file = "account_data.json"
        
    def load_saved_account(self) -> bool:
        """Load saved account data if exists"""
        try:
            if os.path.exists(self.account_file):
                with open(self.account_file, 'r') as f:
                    data = json.load(f)
                    self.account_id = data.get('account_id')
                    self.api_key = data.get('api_key')
                    
                    if self.api_key:
                        self.api_client.api_key = self.api_key
                        self.api_client.session.headers.update({"X-API-Key": self.api_key})
                        logger.info(f"Loaded saved account: {self.account_id}")
                        return True
        except Exception as e:
            logger.warning(f"Failed to load saved account: {e}")
        
        return False
    
    def save_account_data(self, account_data: Dict[str, Any]):
        """Save account data to file"""
        try:
            data = {
                'account_id': account_data.get('accountId') or account_data.get('id'),
                'api_key': account_data.get('apiKey'),
                'name': account_data.get('name'),
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.account_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Account data saved to {self.account_file}")
            
            # Also save plain text for easy access
            with open('api_key.txt', 'w') as f:
                f.write(f"API Key: {data['api_key']}\n")
                f.write(f"Account ID: {data['account_id']}\n")
                if 'verificationCode' in account_data:
                    f.write(f"Verification Code: {account_data['verificationCode']}\n")
                    
        except Exception as e:
            logger.error(f"Failed to save account data: {e}")
    
    def setup(self):
        """Initial setup: create account and get API key"""
        try:
            # Try to load saved account first
            if self.load_saved_account():
                logger.info("Using saved account")
                return True
            
            # Create new account
            logger.info("Creating new account...")
            result = self.api_client.create_account(self.agent_name)
            
            logger.debug(f"Account creation result: {result}")
            
            # Check different response structures
            if isinstance(result, dict):
                # Try different possible response structures
                account_data = None
                
                if result.get('success') and 'data' in result:
                    account_data = result['data']
                elif 'data' in result:
                    account_data = result['data']
                elif 'accountId' in result or 'id' in result:
                    account_data = result
                
                if account_data:
                    self.account_id = account_data.get('accountId') or account_data.get('id')
                    self.api_key = account_data.get('apiKey')
                    
                    if self.api_key:
                        # Save account data
                        self.save_account_data(account_data)
                        
                        # Update API client with key
                        self.api_client.api_key = self.api_key
                        self.api_client.session.headers.update({"X-API-Key": self.api_key})
                        
                        logger.success(f"Account created! ID: {self.account_id}")
                        
                        # Try to get account info to verify
                        try:
                            info = self.api_client.get_account_info()
                            logger.info(f"Account verified: {info}")
                        except:
                            pass
                        
                        return True
                
                logger.error(f"Unexpected response structure: {result}")
                return False
            else:
                logger.error(f"Unexpected response type: {type(result)}")
                return False
                
        except MaintenanceError:
            self.in_maintenance = True
            logger.warning("Server under maintenance, cannot setup")
            return False
        except APIError as e:
            logger.error(f"API Error during setup: {e}")
            return False
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def find_or_create_game(self):
        """Find waiting game or create new one"""
        try:
            # Try to find waiting game
            games = self.api_client.get_waiting_games()
            
            logger.debug(f"Games response: {games}")
            
            if games and isinstance(games, dict):
                # Try different response structures
                games_list = None
                
                if games.get('success') and 'data' in games:
                    games_list = games['data']
                elif 'data' in games:
                    games_list = games['data']
                elif isinstance(games, list):
                    games_list = games
                
                if games_list and len(games_list) > 0:
                    # Join first available game
                    first_game = games_list[0]
                    self.game_id = first_game.get('id')
                    if self.game_id:
                        logger.info(f"Joined existing game: {self.game_id}")
                        return True
            
            # Create new game
            logger.info("No waiting games, creating new...")
            new_game = self.api_client.create_game()
            
            logger.debug(f"Create game response: {new_game}")
            
            if new_game and isinstance(new_game, dict):
                game_data = None
                
                if new_game.get('success') and 'data' in new_game:
                    game_data = new_game['data']
                elif 'data' in new_game:
                    game_data = new_game['data']
                elif 'id' in new_game:
                    game_data = new_game
                
                if game_data:
                    self.game_id = game_data.get('id')
                    if self.game_id:
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
            if not self.api_key:
                logger.error("No API key available")
                return False
            
            result = self.api_client.register_agent(self.game_id, f"{self.agent_name}_AI")
            
            logger.debug(f"Register response: {result}")
            
            if result and isinstance(result, dict):
                agent_data = None
                
                if result.get('success') and 'data' in result:
                    agent_data = result['data']
                elif 'data' in result:
                    agent_data = result['data']
                elif 'id' in result:
                    agent_data = result
                
                if agent_data:
                    self.agent_id = agent_data.get('id')
                    if self.agent_id:
                        logger.success(f"Agent registered! ID: {self.agent_id}")
                        logger.info(f"Initial stats: HP={agent_data.get('hp', '?')}, EP={agent_data.get('ep', '?')}")
                        return True
            
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
        
        if state and isinstance(state, dict):
            # Extract data from response
            state_data = None
            if state.get('success') and 'data' in state:
                state_data = state['data']
            elif 'data' in state:
                state_data = state['data']
            else:
                state_data = state
            
            if state_data:
                self.current_state = AgentState(**state_data)
                self.consecutive_errors = 0
                return state_data
            else:
                self.consecutive_errors += 1
                return None
        else:
            self.consecutive_errors += 1
            return None
    
    def decide_action(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Core AI decision making"""
        
        # Parse state into objects
        try:
            agent = AgentState(**state)
        except Exception as e:
            logger.error(f"Failed to parse agent state: {e}")
            return {"action": "rest"}  # Default action
        
        # Priority 1: Check if we're alive
        if not agent.isAlive:
            logger.error("Agent is dead!")
            return {"action": "rest"}
        
        # Priority 2: Check for death zone (simplified for now)
        # Since we don't have full region data, we'll be cautious
        
        # Priority 3: Check health
        if ItemManager.need_healing(agent):
            healing_item = ItemManager.get_best_healing_item([i.dict() for i in agent.inventory])
            if healing_item:
                logger.info(f"Using healing item")
                return {
                    "action": "useItem",
                    "target": healing_item['id']
                }
        
        # Priority 4: Check for threats in same region
        units_in_region = state.get('units', [])
        
        if units_in_region:
            # Filter out self
            other_units = [u for u in units_in_region if u.get('id') != agent.id]
            
            for unit in other_units:
                # Check if it's a monster (simplified)
                if unit.get('type') == 'monster' or unit.get('name') in ['Wolf', 'Bear', 'Bandit']:
                    if agent.ep >= 2:
                        logger.info(f"Attacking monster: {unit.get('name')}")
                        return {"action": "attack", "target": unit['id']}
        
        # Priority 5: Check for items
        items_in_region = state.get('items', [])
        
        if items_in_region and len(agent.inventory) < 10:
            # Pick up first item
            first_item = items_in_region[0]
            logger.info(f"Picking up item")
            return {"action": "pickup", "target": first_item['id']}
        
        # Priority 6: Explore or move
        if agent.ep >= 1:
            # Check if we should rest
            if agent.ep < 3:
                logger.info("Resting to recover EP")
                return {"action": "rest"}
            
            # Explore current region
            if random.random() < 0.5:
                logger.info("Exploring current region")
                return {"action": "explore"}
            
            # Move to random direction
            directions = ['north', 'northeast', 'southeast', 'south', 'southwest', 'northwest']
            direction = random.choice(directions)
            logger.info(f"Moving {direction}")
            return {"action": "move", "target": direction}
        
        # Default: rest
        logger.info("No action, resting")
        return {"action": "rest"}
    
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
        
        if result and isinstance(result, dict):
            # Check if action was successful
            if result.get('success') or 'data' in result:
                self.last_action_time = datetime.now(timezone.utc)
                logger.info(f"Action {action['action']} successful")
                return True
            else:
                logger.error(f"Action failed: {result}")
                return False
        else:
            logger.error(f"Action failed: invalid response")
            return False
    
    def check_maintenance_window(self) -> bool:
        """Check if we're in maintenance window (09:30-10:30 UTC)"""
        now = datetime.now(timezone.utc)
        maintenance_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        maintenance_end = now.replace(hour=10, minute=30, second=0, microsecond=0)
        
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
                    logger.warning(f"No state received, waiting... (error {self.consecutive_errors}/5)")
                    time.sleep(30)
                    continue
                
                # Check if game is running
                game_status = state.get('status', 'unknown')
                
                if game_status != 'running':
                    if game_status == 'finished':
                        logger.success(f"Game finished! Kills: {state.get('kills', 0)}")
                        break
                    
                    logger.info(f"Game status: {game_status}, waiting...")
                    time.sleep(30)
                    continue
                
                # Check if agent is alive
                if not state.get('isAlive', True):
                    logger.error("Agent died! Game over.")
                    break
                
                # Log current status
                logger.info(f"Status: HP={state.get('hp', '?')}/{state.get('maxHp', '?')}, "
                           f"EP={state.get('ep', '?')}/{state.get('maxEp', '?')}, "
                           f"Kills={state.get('kills', 0)}")
                
                # Decide and execute action
                action = self.decide_action(state)
                logger.info(f"Decision: {action}")
                self.execute_action(action)
                
                # Wait for next turn (60 seconds real time)
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
                import traceback
                traceback.print_exc()
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
            return False
        
        # Find or create game
        if not self.find_or_create_game():
            logger.error("Failed to get game")
            return False
        
        # Register agent
        if not self.register():
            logger.error("Failed to register")
            return False
        
        # Run main loop
        self.run_game_loop()
        
        logger.info("Agent execution completed")
        return True
