"""
FastAPI 德州扑克服务端（支持AI玩家）
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Dict
import json
import uuid
import asyncio
from pathlib import Path
from .poker_game import PokerGame
from .ai_player import AIPlayer, AIPlayerFactory

app = FastAPI(title="德州扑克")

BASE_DIR = Path(__file__).resolve().parent.parent

# 游戏实例
game = PokerGame(small_blind=10, big_blind=20)

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.ai_task = None

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.active_connections[player_id] = websocket

    def disconnect(self, player_id: str):
        if player_id in self.active_connections:
            del self.active_connections[player_id]

    async def send_personal_message(self, message: dict, player_id: str):
        if player_id in self.active_connections:
            try:
                await self.active_connections[player_id].send_json(message)
            except:
                self.disconnect(player_id)

    async def broadcast(self, message: dict, exclude_player: str = None):
        disconnected = []
        for player_id, connection in list(self.active_connections.items()):  # 使用list()复制字典键
            if player_id != exclude_player:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(player_id)

        for player_id in disconnected:
            self.disconnect(player_id)

    async def send_game_state(self):
        """向所有玩家发送游戏状态"""
        for player_id in self.active_connections.keys():
            state = game.get_game_state(player_id)
            await self.send_personal_message({
                "type": "game_state",
                "data": state
            }, player_id)

    async def process_ai_turn(self):
        """处理AI玩家回合"""
        if game.game_stage in ["waiting", "showdown"]:
            return
        
        current_player = game.players[game.current_player_index]
        
        # 检查是否是AI玩家
        if isinstance(current_player, AIPlayer) and not current_player.folded:
            # 模拟思考时间（随机1-3秒，更自然）
            import random
            think_time = random.uniform(1.0, 3.0)
            await asyncio.sleep(think_time)
            
            # AI决策
            action, amount = current_player.decide_action(
                current_bet=game.current_bet,
                pot=game.pot,
                community_cards=game.community_cards,
                game_stage=game.game_stage
            )
            
            # 执行行动
            if game.player_action(current_player.id, action, amount):
                # 广播AI行动
                await self.broadcast({
                    "type": "player_action",
                    "data": {
                        "player_id": current_player.id,
                        "player_name": current_player.name,
                        "action": action,
                        "amount": amount
                    }
                })
                
                # 更新游戏状态
                await self.send_game_state()
                
                # 如果游戏结束
                if game.game_stage == "showdown":
                    await self.broadcast({
                        "type": "round_end",
                        "data": game.get_game_state()
                    })
                else:
                    # 继续处理下一个AI玩家
                    await self.process_ai_turn()

    async def check_timeout_loop(self):
        """超时检查循环"""
        while True:
            await asyncio.sleep(1)  # 每秒检查一次

            # 检查超时
            timeout, action_type = game.check_timeout()

            if timeout:
                print(f"[超时检查] 发生超时，操作类型: {action_type}")
                # 广播游戏状态
                await self.send_game_state()

                # 如果游戏结束
                if game.game_stage == "showdown":
                    await self.broadcast({
                        "type": "round_end",
                        "data": game.get_game_state()
                    })
                elif action_type == 'ai_action':
                    # 如果当前玩家是AI，触发AI行动
                    print("[超时检查] 触发AI行动")
                    await self.process_ai_turn()


manager = ConnectionManager()


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    manager.ai_task = asyncio.create_task(manager.check_timeout_loop())
    print("✅ 超时检查循环已启动")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """返回游戏主页"""
    index_path = BASE_DIR / "web" / "index.html"
    return index_path.read_text(encoding="utf-8")


@app.get("/test_game.html", response_class=HTMLResponse)
async def get_test_page():
    """返回测试页面"""
    test_path = BASE_DIR / "tests" / "test_game.html"
    return test_path.read_text(encoding="utf-8")


@app.get("/api/game_history")
async def get_game_history(limit: int = 10):
    """获取游戏历史记录"""
    return {"history": game.get_game_history(limit)}


@app.websocket("/ws/{player_name}")
async def websocket_endpoint(websocket: WebSocket, player_name: str):
    """WebSocket连接端点"""
    player_id = str(uuid.uuid4())
    
    # 添加玩家到游戏
    if not game.add_player(player_id, player_name):
        await websocket.close(code=1008, reason="游戏已满或玩家名重复")
        return
    
    await manager.connect(websocket, player_id)
    
    # 发送玩家ID
    await manager.send_personal_message({
        "type": "player_id",
        "data": {"player_id": player_id}
    }, player_id)
    
    # 广播玩家加入消息
    await manager.broadcast({
        "type": "player_joined",
        "data": {"player_name": player_name}
    })
    
    # 发送当前游戏状态
    await manager.send_game_state()
    
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "add_ai":
                # 添加AI玩家
                ai_count = data.get("count", 1)
                added = 0
                
                for i in range(ai_count):
                    if len(game.players) >= 8:
                        break
                    
                    ai_id = f"ai_{uuid.uuid4()}"
                    ai_player = AIPlayerFactory.create_ai_player(
                        ai_id, 
                        len([p for p in game.players if isinstance(p, AIPlayer)])
                    )
                    
                    # 直接添加到游戏中
                    game.players.append(ai_player)
                    added += 1
                    
                    # 广播AI加入
                    await manager.broadcast({
                        "type": "player_joined",
                        "data": {"player_name": ai_player.name}
                    })
                
                await manager.send_personal_message({
                    "type": "info",
                    "data": {"message": f"已添加 {added} 个AI玩家"}
                }, player_id)
                
                await manager.send_game_state()
            
            elif message_type == "start_game":
                # 开始游戏
                if game.start_game():
                    await manager.broadcast({
                        "type": "game_started",
                        "data": {}
                    })
                    await manager.send_game_state()
                    
                    # 如果第一个玩家是AI，触发AI行动
                    await manager.process_ai_turn()
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "data": {"message": "至少需要2名玩家才能开始游戏"}
                    }, player_id)
            
            elif message_type == "action":
                # 玩家行动
                action = data.get("action")
                amount = data.get("amount", 0)
                
                if game.player_action(player_id, action, amount):
                    # 广播玩家行动
                    await manager.broadcast({
                        "type": "player_action",
                        "data": {
                            "player_id": player_id,
                            "action": action,
                            "amount": amount
                        }
                    })
                    
                    # 更新游戏状态
                    await manager.send_game_state()
                    
                    # 如果游戏结束
                    if game.game_stage == "showdown":
                        await manager.broadcast({
                            "type": "round_end",
                            "data": game.get_game_state()
                        })
                    else:
                        # 触发AI玩家行动
                        await manager.process_ai_turn()
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "data": {"message": "无效的操作"}
                    }, player_id)
            
            elif message_type == "get_state":
                # 获取游戏状态
                await manager.send_game_state()
            
            elif message_type == "end_game":
                # 结束游戏（仅房主可调用）
                if game.end_game(player_id):
                    await manager.broadcast({
                        "type": "game_ended",
                        "data": game.final_results
                    })
                    await manager.send_game_state()
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "data": {"message": "只有房主可以结束游戏"}
                    }, player_id)

            elif message_type == "set_timeout":
                # 设置超时时间（仅房主可调用）
                if player_id == game.room_owner_id:
                    timeout = data.get("timeout", 30)
                    if 10 <= timeout <= 120:
                        game.set_turn_timeout(timeout)
                        await manager.send_personal_message({
                            "type": "info",
                            "data": {"message": f"超时时间已设置为{timeout}秒"}
                        }, player_id)
                    else:
                        await manager.send_personal_message({
                            "type": "error",
                            "data": {"message": "超时时间必须在10-120秒之间"}
                        }, player_id)
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "data": {"message": "只有房主可以设置超时"}
                    }, player_id)
    
    except WebSocketDisconnect:
        manager.disconnect(player_id)
        game.remove_player(player_id)
        await manager.broadcast({
            "type": "player_left",
            "data": {"player_name": player_name}
        })
        await manager.send_game_state()


@app.get("/api/game_state")
async def get_game_state():
    """获取游戏状态（HTTP API）"""
    return game.get_game_state()


@app.post("/api/reset_game")
async def reset_game():
    """重置游戏"""
    global game
    game = PokerGame(small_blind=10, big_blind=20)
    await manager.send_game_state()
    return {"status": "success"}


@app.post("/api/add_ai")
async def add_ai_players(count: int = 1):
    """添加AI玩家"""
    added = 0
    for i in range(count):
        if len(game.players) >= 8:
            break
        
        ai_id = f"ai_{uuid.uuid4()}"
        ai_player = AIPlayerFactory.create_ai_player(
            ai_id, 
            len([p for p in game.players if isinstance(p, AIPlayer)])
        )
        game.players.append(ai_player)
        added += 1
    
    return {"status": "success", "added": added, "total_players": len(game.players)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
