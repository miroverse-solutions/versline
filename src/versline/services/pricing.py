# src/versline/services/pricing.py

import time
import httpx
from loguru import logger
from typing import Optional, List, Dict
from pydantic import BaseModel

class Transaction(BaseModel):
    request_id: str
    cost_usd: float
    cost_irt: float

class CostReport(BaseModel):
    total_cost_usd: float
    total_cost_irt: float
    transactions: List[Transaction] = []
    found: int = 0
    error: Optional[str] = None

class TokenTracker:
    """Track token usage and costs."""
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.avalai_request_ids = []
    
    def add_usage(self, input_tokens: int, output_tokens: int, cost: float = 0.0):
        """Add token usage."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost
    
    def add_avalai_request(self, request_id: str):
        """Track AvalAI request ID for cost lookup."""
        if request_id:
            self.avalai_request_ids.append(request_id)

def get_http_client(proxy_url: Optional[str] = None) -> httpx.Client:
    """Create HTTP client with optional proxy support."""
    if proxy_url:
        return httpx.Client(proxy=proxy_url, timeout=30.0)
    return httpx.Client(timeout=30.0)

def lookup_avalai_cost(
    request_ids: List[str],
    api_key: str,
    max_retries: int = 3,
    wait_time: float = 5.0,
    proxy: Optional[str] = None
) -> CostReport:
    """Lookup exact cost for AvalAI requests."""
    if not request_ids:
        return CostReport(total_cost_usd=0.0, total_cost_irt=0.0)
    
    if not api_key:
        return CostReport(total_cost_usd=0.0, total_cost_irt=0.0, error="No API key")
    
    # Wait a bit for transactions to settle if needed (though API is usually fast)
    # The original code waited.
    if wait_time > 0:
        time.sleep(wait_time)
    
    http_client = get_http_client(proxy)
    
    for attempt in range(max_retries):
        try:
            response = http_client.post(
                "https://api.avalai.ir/user/v1/transactions/lookup",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"transaction_ids": request_ids},
            )
            
            if response.status_code == 200:
                data = response.json()
                
                total_usd = 0.0
                total_irt = 0.0
                transactions = []
                
                if data.get("summary", {}).get("found", 0) > 0:
                    for tx in data.get("transactions", []):
                        cost = tx.get("cost", {})
                        usd = float(cost.get("unit", 0))
                        irt = float(cost.get("paid_irt", 0)) + float(cost.get("paid_grant_irt", 0))
                        total_usd += usd
                        total_irt += irt
                        transactions.append(Transaction(
                            request_id=tx.get("id"),
                            cost_usd=usd,
                            cost_irt=irt,
                        ))
                
                return CostReport(
                    total_cost_usd=total_usd,
                    total_cost_irt=total_irt,
                    transactions=transactions,
                    found=data.get("summary", {}).get("found", 0)
                )
            else:
                logger.warning(f"AvalAI cost lookup failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.warning(f"AvalAI cost lookup error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return CostReport(total_cost_usd=0.0, total_cost_irt=0.0, error="Failed to lookup costs")
from rich.console import Console
from rich.table import Table

def print_cost_report(tracker: TokenTracker, api_key: Optional[str] = None):
    """Print cost estimation summary using Rich."""
    console = Console()
    table = Table(title="Cost Estimation Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Total Input Tokens", f"{tracker.total_input_tokens:,}")
    table.add_row("Total Output Tokens", f"{tracker.total_output_tokens:,}")
    
    # AvalAI Exact Lookup
    if tracker.avalai_request_ids and api_key:
        with console.status("[bold green]Fetching exact AvalAI costs..."):
            report = lookup_avalai_cost(tracker.avalai_request_ids, api_key)
            if not report.error:
                table.add_row("AvalAI Cost (Exact)", f"{report.total_cost_irt:,.0f} IRT")
                if report.total_cost_usd > 0:
                     table.add_row("AvalAI Cost (USD)", f"${report.total_cost_usd:.4f}")
            else:
                if report.error != "No API key":
                    table.add_row("AvalAI Cost Error", str(report.error))
    
    # Generic USD Cost (OpenRouter/OpenAI)
    if tracker.total_cost_usd > 0:
        table.add_row("Est. Cost (non-AvalAI)", f"${tracker.total_cost_usd:.4f}")

    console.print(table)