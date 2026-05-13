from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import shutil
from src.database import get_db, init_db, reset_db, DB_PATH
import aiosqlite

app = FastAPI(title="Dashboard Config API")

@app.on_event("startup")
async def startup():
    await init_db()

# Models
class WidgetBase(BaseModel):
    type: str
    title: Optional[str] = None
    config: dict
    position: Optional[int] = 0

class WidgetCreate(WidgetBase):
    pass

class Widget(WidgetBase):
    id: int
    dashboard_id: int

class DashboardBase(BaseModel):
    name: str
    description: Optional[str] = None

class DashboardCreate(DashboardBase):
    pass

class Dashboard(DashboardBase):
    id: int
    widgets: List[Widget] = []

# Endpoints
@app.post("/dashboards/", response_model=Dashboard)
async def create_dashboard(dashboard: DashboardCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO dashboards (name, description) VALUES (?, ?)",
            (dashboard.name, dashboard.description)
        )
        await db.commit()
        dashboard_id = cursor.lastrowid
        return {**dashboard.dict(), "id": dashboard_id, "widgets": []}

@app.get("/dashboards/", response_model=List[Dashboard])
async def list_dashboards():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM dashboards")
        rows = await cursor.fetchall()
        dashboards = []
        for row in rows:
            d = dict(row)
            w_cursor = await db.execute("SELECT * FROM widgets WHERE dashboard_id = ?", (d["id"],))
            w_rows = await w_cursor.fetchall()
            d["widgets"] = [dict(wr) for wr in w_rows]
            # Parse JSON config
            for w in d["widgets"]:
                w["config"] = json.loads(w["config"])
            dashboards.append(d)
        return dashboards

@app.post("/dashboards/{dashboard_id}/widgets/", response_model=Widget)
async def create_widget(dashboard_id: int, widget: WidgetCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO widgets (dashboard_id, type, title, config, position) VALUES (?, ?, ?, ?, ?)",
            (dashboard_id, widget.type, widget.title, json.dumps(widget.config), widget.position)
        )
        await db.commit()
        return {**widget.dict(), "id": cursor.lastrowid, "dashboard_id": dashboard_id}

@app.post("/reset-db")
async def api_reset_db():
    await reset_db()
    return {"message": "Database reset successfully"}

@app.get("/export-db")
async def export_db():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="Database file not found")
    return FileResponse(DB_PATH, filename="dashboard_config.db", media_type="application/x-sqlite3")

@app.post("/import-db")
async def import_db(file: UploadFile = File(...)):
    # Save current DB as backup
    if os.path.exists(DB_PATH):
        shutil.copy(DB_PATH, DB_PATH + ".bak")
    
    with open(DB_PATH, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {"message": "Database imported successfully"}
