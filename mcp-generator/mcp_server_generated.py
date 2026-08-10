import httpx
from fastmcp import MCPServer, tool
import asyncio
import json

class ExchangeRateServer(MCPServer):
    """A FastMCP server for fetching exchange rates."""

    @tool(name="get_exchange_rates", description="Get Latest Rates")
    async def get_exchange_rates(self, base_currency: str) -> dict:
        """
        Fetch the latest exchange rates for a given base currency.

        Args:
            base_currency (str): The 3-letter code of the currency (e.g. USD, PKR, EUR).

        Returns:
            dict: A dictionary containing the exchange rates or an error message.
        """
        url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error occurred: {e.response.status_code}"}
        except httpx.RequestError as e:
            return {"error": f"An error occurred while requesting data: {str(e)}"}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

if __name__ == "__main__":
    server = ExchangeRateServer()
    asyncio.run(server.start())