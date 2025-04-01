from fastapi import FastAPI, HTTPException
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from rich.logging import RichHandler
import logging

FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

app = FastAPI()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - you may want to restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

