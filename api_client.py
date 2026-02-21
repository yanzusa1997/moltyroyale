import requests
import time
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
import os

BASE_URL = "https://mort-royal-production.up.railway.app/api"

class APIError(Exception):
    pass

class MaintenanceError(APIError):
    pass

class APIClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MOLTY_API_KEY")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-API-Key": self.api_key})
    
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        if response.status_code == 503:
            raise MaintenanceError("Server under maintenance")
        elif response.status_code >= 400:
            error_msg = f"API Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise APIError(error_msg)
        
        return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def create_account(self, name: str) -> Dict[str, Any]:
        """Step 1: Create account and get API key"""
        logger.info(f"Creating account with name: {name}")
        response = self.session.post(
            f"{BASE_URL}/accounts",
            json={"name": name}
        )
        return self._handle_response(response)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def get_account_info(self) -> Dict[str, Any]:
        """Get current account info"""
        response = self.session.get(f"{BASE_URL}/accounts/me")
        return self._handle_response(response)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def get_waiting_games(self) -> Dict[str, Any]:
        """Get list of waiting games"""
        response = self.session.get(f"{BASE_URL}/games?status=waiting")
        return self._handle_response(response)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def create_game(self) -> Dict[str, Any]:
        """Create a new game"""
        response = self.session.post(f"{BASE_URL}/games")
        return self._handle_response(response)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def register_agent(self, game_id: str, agent_name: str) -> Dict[str, Any]:
        """Register agent in a game"""
        logger.info(f"Registering agent {agent_name} in game {game_id}")
        response = self.session.post(
            f"{BASE_URL}/games/{game_id}/agents/register",
            json={"name": agent_name}
        )
        return self._handle_response(response)
    
    def get_agent_state(self, game_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent state (no retry, called frequently)"""
        try:
            response = self.session.get(
                f"{BASE_URL}/games/{game_id}/agents/{agent_id}/state"
            )
            return self._handle_response(response)
        except Exception as e:
            logger.error(f"Failed to get agent state: {e}")
            return None
    
    def send_action(self, game_id: str, agent_id: str, action: str, target: Optional[str] = None, data: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Send action to game"""
        try:
            payload = {"action": action}
            if target:
                payload["target"] = target
            if data:
                payload.update(data)
            
            response = self.session.post(
                f"{BASE_URL}/games/{game_id}/agents/{agent_id}/action",
                json=payload
            )
            return self._handle_response(response)
        except Exception as e:
            logger.error(f"Failed to send action {action}: {e}")
            return None