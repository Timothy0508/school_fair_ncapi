import json
import os
import asyncio
from typing import Optional, List
from datetime import datetime

import asyncpg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from google.cloud.sql.connector import Connector
from dotenv import load_dotenv

DATABASE_URL = "sqlite+aiosqlite:///./orders.db"  # 使用相對於專案的檔案路徑

class Item(BaseModel):
    """商品模型"""
    id: int  # 商品ID
    quantity: int  # 商品數量
    price: float  # 商品價格

class Order(BaseModel):
    """訂單模型"""
    items: list[Item]  # 訂單項目列表
    totalPrice: float  # 訂單總價
    orderTime: str

# SQLAlchemy 模型 (定義資料庫表格結構)
class OrderDB:
    __tablename__ = "orders"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True, autoincrement=True)
    order_time = sqlalchemy.Column(sqlalchemy.String)
    total_price = sqlalchemy.Column(sqlalchemy.Float)

    items = sqlalchemy.orm.relationship("OrderItemDB", back_populates="order")

class OrderItemDB:
    __tablename__ = "order_items"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True, autoincrement=True)
    order_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("orders.id"))
    item_id = sqlalchemy.Column(sqlalchemy.Integer)  # 商品ID
    quantity = sqlalchemy.Column(sqlalchemy.Integer)
    price = sqlalchemy.Column(sqlalchemy.Float)

    order = sqlalchemy.orm.relationship("OrderDB", back_populates="items")

app = FastAPI()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - you may want to restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine: AsyncEngine | None = None
async_session: sessionmaker[AsyncSession] | None = None

# 初始化資料庫連線
async def init_db():
    """
    Initializes the database connection using SQLite and SQLAlchemy.
    """
    global engine, async_session
    engine = create_async_engine(
        DATABASE_URL,  # 使用 SQLite 連線 URL
        echo=False,  # 可以設定為 True 來查看 SQL 查詢
    )
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    # 建立資料表
    async with engine.begin() as conn:
        await conn.run_sync(sqlalchemy.MetaData().create_all)

# FastAPI 相依性
async def get_db_session():
    """
    Yields a database session for each request.
    """
    if async_session is None:
        raise Exception("Database sessionmaker is not initialized.")
    async with async_session() as session:
        yield session

# 啟動事件處理器
@app.on_event("startup")
async def startup_event():
    """
    Initializes the database connection when the FastAPI application starts.
    """
    await init_db()

# API 路由
@app.post("/submit-order/")
async def submit_order(order: Order, db: AsyncSession = Depends(get_db_session)):
    """
    處理提交訂單的請求，並將訂單儲存到資料庫中。
    """
    try:
        # 創建 OrderDB 實例
        db_order = OrderDB(
            order_time=order.orderTime,
            total_price=order.totalPrice,
        )

        # 創建 OrderItemDB 實例列表
        for item in order.items:
            db_order_item = OrderItemDB(
                item_id=item.id,
                quantity=item.quantity,
                price=item.price,
            )
            db.add(db_order_item)  # Add each order item to the session

        db.add(db_order)  # Add the order
        await db.commit()  # Commit the transaction
        await db.refresh(db_order)  # Refresh the order to get the generated ID

        return {"message": "Order submitted successfully", "order_id": db_order.id}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit order: {str(e)}")

# 模擬叫號隊列
queue = []
# 號碼計數器
number_counter = 1
# 目前叫號號碼
current_number = None

@app.post("/queue")
async def enqueue():
    """櫃檯：將顧客加入叫號隊列，並分配號碼"""
    global number_counter
    number = number_counter
    queue.append(number)
    number_counter += 1
    return {"message": f"已將 {number} 號加入隊列"}

@app.post("/dequeue")
async def dequeue():
    """櫃檯：叫號，取出隊列中的下一個號碼"""
    global current_number
    if not queue:
        raise HTTPException(status_code=404, detail="目前沒有顧客在隊列中")
    current_number = queue.pop(0)
    return {"message": f"請 {current_number} 號前往櫃檯"}

@app.get("/current")
async def get_current():
    """客戶：取得目前叫號號碼"""
    if current_number is None:
        raise HTTPException(status_code=404, detail="目前沒有叫號號碼")
    return {"current_number": current_number}

@app.get("/queue/length")
async def get_queue_length():
    """取得目前叫號隊列長度"""
    return {"length": len(queue)}

@app.get("/queue")
async def get_queue():
    """取得目前叫號隊列"""
    return {"queue": queue}

@app.post("/reset")
async def reset_queue():
    """重置等待隊列"""
    global queue, number_counter, current_number
    queue = []
    number_counter = 1
    current_number = None
    return {"message": "以重置"}

@app.get("/get-menu")
async def get_menu():
    """取得菜單"""
    try:
        with open("data/menu.json", "r", encoding="utf-8") as f:
            menu = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="菜單檔案不存在")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="菜單檔案格式錯誤")
    return menu