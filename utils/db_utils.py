# utils/db_utils.py
import os
import aiomysql
from typing import List, Dict
from datetime import datetime

class PlayerDatabaseConnection:
    def __init__(self):
        self.host = os.getenv("PLAYER_DB_HOST", "localhost")
        self.port = int(os.getenv("PLAYER_DB_PORT", 3306))
        self.user = os.getenv("PLAYER_DB_USER", "root")
        self.password = os.getenv("PLAYER_DB_PASSWORD", "")
        self.database = os.getenv("PLAYER_DB_NAME", "game_database")
        self.pool = None
        print(f"DEBUG: Player DB config: Host={self.host}, Port={self.port}, DB={self.database}")

    async def initialize(self):
        """Initialize the player database connection pool."""
        try:
            self.pool = await aiomysql.create_pool(
                host=self.host, port=self.port, user=self.user,
                password=self.password, db=self.database,
                charset="utf8mb4", autocommit=True,
                minsize=1, maxsize=5,
                connect_timeout=10 # Added connection timeout
            )
            print("✅ Player database connection pool established.")
        except Exception as e:
            print(f"❌ Player database connection failed: {e}")
            self.pool = None

    async def close(self):
        """Close the player database connection pool."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            print("✅ Player database connection pool closed.")
        self.pool = None

    async def find_players(self, search_term: str) -> List[Dict]:
        """Find players by name (partial match) - READ ONLY."""
        if not self.pool:
            print("⚠️ Player database not initialized or connection failed. Cannot search players.")
            return []
        query = """
            SELECT Name, Level, LastPlayed, BohemiaUID
            FROM PlayerProfiles
            WHERE LOWER(Name) LIKE LOWER(%s)
            ORDER BY LastPlayed DESC
            LIMIT 15
        """
        try:
            async with self.pool.acquire() as connection:
                async with connection.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(query, (f"%{search_term}%",))
                    rows = await cursor.fetchall()
            
            players = []
            for row in rows:
                hours_since = 'Unknown'
                if row.get("LastPlayed"): # Check if LastPlayed exists and is not None
                    try:
                        time_diff = datetime.utcnow() - row["LastPlayed"]
                        hours_since = f"{int(time_diff.total_seconds() / 3600)}H"
                    except TypeError: # Handle cases where LastPlayed might not be a datetime object
                        hours_since = "Invalid Date"
                else:
                    hours_since = "Never"
                    
                players.append({
                    "Name": row.get("Name", "N/A"),
                    "Level": row.get("Level", 0),
                    "Last Played": hours_since,
                    "BohemiaUID": str(row.get("BohemiaUID", "N/A")),
                })
            return players
        except aiomysql.MySQLError as e: # Catch specific MySQL errors
            print(f"❌ Player database SQL error in find_players: {e}")
            return []
        except Exception as e:
            print(f"❌ Unexpected error in find_players: {e}")
            return []