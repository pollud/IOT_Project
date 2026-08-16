"""Analytics worker microservice exposing REST API endpoints for room stats, prop usage, environmental metrics, safety scoring, and maintenance diagnostics."""

import cherrypy
import sqlite3
import os
import json
import threading
import time
from datetime import datetime, timedelta

class AnalyticsRoute:
    """Database query and data aggregation backend engine for Analytics REST endpoints."""

    def __init__(self):
        """Initialize AnalyticsRoute with target SQLite database path from DB_PATH env var."""
        self.db_path = os.getenv("DB_PATH", "/app/data/events.db")
        
    def get_conn(self) -> sqlite3.Connection:
        """Create and return a new SQLite database connection.

        Returns:
            sqlite3.Connection: SQLite connection object.
        """
        return sqlite3.connect(self.db_path)
        
    def get_time_condition(self, period: str) -> str:
        """Generate SQL WHERE condition snippet for time filtering based on period string.

        Args:
            period (str): Time period filter ("1h", "24h", "7d", or "all").

        Returns:
            str: SQL WHERE clause condition snippet.
        """
        if period == "1h":
            return "timestamp >= datetime('now', '-1 hour')"
        elif period == "24h":
            return "timestamp >= datetime('now', '-24 hours')"
        elif period == "7d":
            return "timestamp >= datetime('now', '-7 days')"
        return "1=1"

    def stats_room(self, room_id: str, period: str = 'all') -> dict:
        """Calculate average solve time and total session count for a room over a given period.

        Args:
            room_id (str): Room identifier.
            period (str): Time period filter.

        Returns:
            dict: Room solve statistics dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        time_cond = self.get_time_condition(period)
        
        cursor.execute(f'''
            SELECT AVG(json_extract(payload, '$.duration')), COUNT(*)
            FROM events
            WHERE (topic LIKE 'session/%/ended' OR topic LIKE 'game/%/session/ended')
              AND json_extract(payload, '$.room_id') = ?
              AND {time_cond}
        ''', (room_id,))
        row = cursor.fetchone()
        
        avg_solve_time = row[0] if row[0] is not None else 0
        count = row[1] if row[1] is not None else 0
        conn.close()
        
        return {"room_id": room_id, "avg_solve_time": round(avg_solve_time, 2), "total_sessions": count}
        
    def stats_prop(self, prop_id: str) -> dict:
        """Query total interaction count for a specific puzzle prop.

        Args:
            prop_id (str): Prop identifier.

        Returns:
            dict: Prop interaction count dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*)
            FROM events 
            WHERE topic LIKE '%prop/%interaction'
              AND json_extract(payload, '$.prop_id') = ?
        ''', (prop_id,))
        row = cursor.fetchone()
        
        usage_count = row[0] if row[0] is not None else 0
        conn.close()
                
        return {"prop_id": prop_id, "usage_count": usage_count}
        
    def stats_environment(self, room_id: str, period: str = 'all') -> dict:
        """Compute environmental statistics (average, min, max temperature and humidity) for a room.

        Args:
            room_id (str): Room identifier.
            period (str): Time period filter.

        Returns:
            dict: Environmental telemetry stats dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        time_cond = self.get_time_condition(period)
        
        cursor.execute(f'''
            SELECT 
                AVG(json_extract(payload, '$.temperature')),
                MIN(json_extract(payload, '$.temperature')),
                MAX(json_extract(payload, '$.temperature')),
                AVG(json_extract(payload, '$.humidity')),
                MIN(json_extract(payload, '$.humidity')),
                MAX(json_extract(payload, '$.humidity'))
            FROM events 
            WHERE topic = ?
              AND {time_cond}
        ''', (f"room/{room_id}/environment",))
        row = cursor.fetchone()
        conn.close()
        
        return {
            "room_id": room_id,
            "temperature": {
                "avg": round(row[0], 2) if row[0] else 0,
                "min": round(row[1], 2) if row[1] else 0,
                "max": round(row[2], 2) if row[2] else 0
            },
            "humidity": {
                "avg": round(row[3], 2) if row[3] else 0,
                "min": round(row[4], 2) if row[4] else 0,
                "max": round(row[5], 2) if row[5] else 0
            }
        }
        
    def stats_history(self, room_id: str, period: str = 'all') -> dict:
        """Retrieve historical environmental time-series data points for chart plotting.

        Args:
            room_id (str): Room identifier.
            period (str): Time period filter.

        Returns:
            dict: Historical environmental series dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        time_cond = self.get_time_condition(period)
        
        cursor.execute(f'''
            SELECT 
                timestamp,
                json_extract(payload, '$.temperature'),
                json_extract(payload, '$.humidity')
            FROM events
            WHERE topic = ?
              AND {time_cond}
            ORDER BY timestamp ASC
        ''', (f"room/{room_id}/environment",))
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            if row[1] is not None and row[2] is not None:
                history.append({
                    "timestamp": row[0],
                    "temperature": row[1],
                    "humidity": row[2]
                })
        return {"room_id": room_id, "history": history}

    # --- ADVANCED DATA PROCESSING ENDPOINTS ---

    def stats_bottlenecks(self) -> dict:
        """Analyze puzzle completion times and identify chokepoint puzzles across all rooms.

        Returns:
            dict: Chokepoints analysis dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                json_extract(payload, '$.prop_id') as prop_id,
                COUNT(*) as trigger_count,
                MAX(timestamp) as last_triggered
            FROM events
            WHERE topic LIKE '%prop/%interaction'
            GROUP BY prop_id
            ORDER BY trigger_count DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        prop_stats = []
        for row in rows:
            prop_stats.append({
                "prop_id": row[0],
                "total_interactions": row[1],
                "last_triggered": row[2],
                "bottleneck_severity": "HIGH" if row[1] > 20 else ("MEDIUM" if row[1] > 10 else "LOW")
            })
            
        return {
            "analysis": "Puzzle Chokepoint & Bottleneck Analytics",
            "timestamp": time.time(),
            "props_analyzed": len(prop_stats),
            "chokepoints": prop_stats
        }

    def stats_safety(self) -> dict:
        """Compute Room Physical Strain & Safety Comfort Index (0-100%).

        Returns:
            dict: Safety comfort index and environmental metric summary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Query total safety alerts
        cursor.execute("SELECT COUNT(*) FROM events WHERE topic LIKE '%system/alerts%' OR topic LIKE '%safety%'")
        alert_count = cursor.fetchone()[0]
        
        # Query ambient environmental averages
        cursor.execute("SELECT AVG(json_extract(payload, '$.temperature')), AVG(json_extract(payload, '$.humidity')) FROM events WHERE topic LIKE '%environment%'")
        env_row = cursor.fetchone()
        conn.close()
        
        avg_temp = env_row[0] if env_row[0] else 22.0
        avg_hum = env_row[1] if env_row[1] else 45.0
        
        # Comfort index score: deduction for excessive temp/humidity or high safety alerts
        temp_deduction = max(0, (avg_temp - 24.0) * 5) if avg_temp > 24 else 0
        alert_deduction = min(40, alert_count * 5)
        safety_score = max(0, round(100 - temp_deduction - alert_deduction, 1))
        
        return {
            "analysis": "Physical Strain & Safety Index",
            "safety_score_pct": safety_score,
            "overall_status": "OPTIMAL" if safety_score >= 80 else ("WARNING" if safety_score >= 60 else "CRITICAL"),
            "metrics": {
                "ambient_temp_avg_c": round(avg_temp, 1),
                "ambient_humidity_avg_pct": round(avg_hum, 1),
                "total_safety_alerts": alert_count
            }
        }

    def stats_maintenance(self) -> dict:
        """Generate Hardware Diagnostics and Preventative Maintenance Alerts for props/sensors (e.g. low battery).

        Returns:
            dict: Hardware maintenance warnings list.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                json_extract(payload, '$.badge_id') as badge_id,
                MIN(json_extract(payload, '$.battery_level')) as lowest_battery
            FROM events
            WHERE topic LIKE '%battery%'
            GROUP BY badge_id
        ''')
        battery_rows = cursor.fetchall()
        conn.close()
        
        maintenance_list = []
        for b in battery_rows:
            badge_id, lowest_bat = b[0], b[1]
            if lowest_bat is not None and lowest_bat < 20.0:
                maintenance_list.append({
                    "component_id": badge_id,
                    "type": "battery",
                    "status": "REPLACE_BATTERY",
                    "current_level": lowest_bat
                })
                
        return {
            "analysis": "Hardware Diagnostics & Preventative Maintenance",
            "timestamp": time.time(),
            "alerts_count": len(maintenance_list),
            "maintenance_required": maintenance_list
        }

    def stats_game_center(self) -> dict:
        """Aggregate Center-wide Key Performance Indicators (KPIs) across all 10 theme rooms.

        Returns:
            dict: Game center KPI metrics dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*), AVG(json_extract(payload, '$.duration')) FROM events WHERE topic LIKE '%session/ended%'")
        row = cursor.fetchone()
        conn.close()
        
        total_sessions = row[0] if row[0] else 0
        avg_duration = row[1] if row[1] else 0
        
        zones = {
            "Sci-Fi Zone": ["room_cyberpunk", "room_matrix", "room_alien"],
            "Fantasy Zone": ["room_dungeon", "room_atlantis", "room_tomb"],
            "Horror Zone": ["room_haunted", "room_asylum", "room_sherlock"],
            "Arcade Arena": ["room_arcade"]
        }
        
        return {
            "center_name": "Mega IoT Escape Game Center",
            "timestamp": time.time(),
            "total_rooms": 10,
            "theme_zones": zones,
            "kpis": {
                "total_completed_games": total_sessions,
                "overall_avg_duration_sec": round(avg_duration, 1),
                "estimated_hourly_player_throughput": round((total_sessions * 4) / max(1, (avg_duration / 3600)), 1)
            }
        }

    def stats_heatmap(self, room_id: str) -> dict:
        """Construct spatial position coordinate heatmaps for player movement within a room.

        Args:
            room_id (str): Room identifier.

        Returns:
            dict: Heatmap coordinate matrix dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                ROUND(json_extract(payload, '$.x'), 1) as x_pos,
                ROUND(json_extract(payload, '$.y'), 1) as y_pos,
                COUNT(*) as count
            FROM events
            WHERE topic LIKE ? AND json_extract(payload, '$.x') IS NOT NULL
            GROUP BY x_pos, y_pos
            LIMIT 20
        ''', (f"%room/{room_id}/badge/%/position",))
        rows = cursor.fetchall()
        conn.close()
        
        coordinates = [{"x": r[0], "y": r[1], "frequency": r[2]} for r in rows]
        return {
            "room_id": room_id,
            "sample_points": len(coordinates),
            "heatmap_matrix": coordinates
        }

    def stats_reset(self) -> dict:
        """Purge all stored events from the database.

        Returns:
            dict: Success or error response dictionary.
        """
        conn = self.get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM events")
            conn.commit()
            return {"success": True, "message": "Database reset successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()
        
    def prune_old_data_loop(self):
        """Background thread loop executing every hour to prune events older than 7 days from SQLite database."""
        while True:
            try:
                conn = self.get_conn()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM events WHERE timestamp < datetime('now', '-7 days')")
                deleted = cursor.rowcount
                conn.commit()
                if deleted > 0:
                    print(f"Pruned {deleted} old events from database.")
            except Exception as e:
                print(f"Error during pruning: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()
            time.sleep(3600)

class Root:
    """CherryPy Root controller placeholder."""
    pass
    
class Stats:
    """REST Controller mapping /stats endpoints to AnalyticsRoute calculations."""

    def __init__(self):
        """Initialize Stats REST endpoint controller."""
        self.analytics = AnalyticsRoute()
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def room(self, room_id, period='all'):
        """GET /stats/room endpoint returning room solve duration stats."""
        return self.analytics.stats_room(room_id, period)
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def prop(self, prop_id):
        """GET /stats/prop endpoint returning prop usage stats."""
        return self.analytics.stats_prop(prop_id)
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def environment(self, room_id, period='all'):
        """GET /stats/environment endpoint returning room environmental stats."""
        return self.analytics.stats_environment(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def history(self, room_id, period='all'):
        """GET /stats/history endpoint returning environmental time-series data points."""
        return self.analytics.stats_history(room_id, period)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def bottlenecks(self):
        """GET /stats/bottlenecks endpoint returning puzzle chokepoints analytics."""
        return self.analytics.stats_bottlenecks()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def safety(self):
        """GET /stats/safety endpoint returning room safety comfort index."""
        return self.analytics.stats_safety()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def maintenance(self):
        """GET /stats/maintenance endpoint returning hardware diagnostic alerts."""
        return self.analytics.stats_maintenance()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def game_center(self):
        """GET /stats/game_center endpoint returning game center KPI summary."""
        return self.analytics.stats_game_center()

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def heatmap(self, room_id):
        """GET /stats/heatmap endpoint returning player movement coordinate heatmap data."""
        return self.analytics.stats_heatmap(room_id)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def reset(self):
        """POST/GET /stats/reset endpoint to purge stored events database."""
        return self.analytics.stats_reset()

if __name__ == "__main__":
    root = Root()
    root.stats = Stats()
    
    t = threading.Thread(target=root.stats.analytics.prune_old_data_loop, daemon=True)
    t.start()
    
    def cors_options():
        if cherrypy.request.method == 'OPTIONS':
            cherrypy.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
            cherrypy.response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return True
    cherrypy.tools.cors_options = cherrypy.Tool('before_handler', cors_options)

    conf = {
        '/': {
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Headers', 'Content-Type')
            ],
            'tools.cors_options.on': True
        },
        '/stats': {
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Headers', 'Content-Type')
            ],
            'tools.cors_options.on': True
        }
    }

    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8084,
    })
    cherrypy.quickstart(root, '/', conf)

