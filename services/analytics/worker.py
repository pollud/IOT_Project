import cherrypy
import sqlite3
import os
import json

class AnalyticsRoute:
    def __init__(self):
        self.db_path = os.getenv("DB_PATH", "/app/data/events.db")
        
    def get_conn(self):
        return sqlite3.connect(self.db_path)
        
    def stats_room(self, room_id):
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT payload FROM events WHERE topic LIKE '%session/ended'")
        rows = cursor.fetchall()
        
        total_time = 0
        count = 0
        for r in rows:
            try:
                data = json.loads(r[0])
                if data.get("room_id") == room_id:
                    total_time += data.get("duration", 0)
                    count += 1
            except Exception:
                pass
                
        avg_solve_time = total_time / count if count > 0 else 0
        
        return {"room_id": room_id, "avg_solve_time": avg_solve_time, "total_sessions": count}
        
    def stats_prop(self, prop_id):
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT payload FROM events WHERE topic LIKE '%prop/%interaction'")
        rows = cursor.fetchall()
        
        usage_count = 0
        for r in rows:
            try:
                data = json.loads(r[0])
                if data.get("prop_id") == prop_id:
                    usage_count += 1
            except Exception:
                pass
                
        return {"prop_id": prop_id, "usage_count": usage_count}

class Root:
    pass
    
class Stats:
    def __init__(self):
        self.analytics = AnalyticsRoute()
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def room(self, room_id):
        return self.analytics.stats_room(room_id)
        
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def prop(self, prop_id):
        return self.analytics.stats_prop(prop_id)

if __name__ == "__main__":
    root = Root()
    root.stats = Stats()
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8084,
    })
    cherrypy.quickstart(root)
